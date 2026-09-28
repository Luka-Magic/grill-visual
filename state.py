#!/usr/bin/env python3
"""grill-visual 統合ページのための状態算出(純粋関数。標準ライブラリのみ)。

~/.agent/diagrams/ を読み、題材ごとに「待ち / 回答済み / 完了 / エラー」を導く。
判定はファイルだけから行う(サーバーにメモリ状態を持たない):

  waiting  … status:"open" のラウンドがあり、answers/<topic>-round-<N>.json が無い
  answered … open ラウンドはあるが回答ファイルが既にある(AI が次ラウンドを書いていない)
  done     … open ラウンドが無い(info のまとめタブで終わっている)
  error    … JSON が読めない・必須キーが無い(AI の書き換え途中なども含む)
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

DATA_DIR = "grill-data"
ANSWERS_DIR = "answers"
ARCHIVE_FILE = ".grill-dashboard.json"   # 統合ページの設定(archived / kind_prefixes)
TIME_FMT = "%Y-%m-%dT%H:%M:%S"
TOPIC_MAX_LEN = 80
DEFAULT_ROOT = Path.home() / ".agent" / "diagrams"

State = Literal["waiting", "answered", "done", "error"]
STATES: tuple[State, ...] = ("waiting", "answered", "done", "error")
ISSUE_IN_TITLE_RE = re.compile(r"(?<![\w#])#(\d{1,6})\b")
# topic 中の番号は先頭 0 を認めない("rules-04-github" の 04 や "tr-03-media-detail" の T03 は issue ではない)
ISSUE_IN_TOPIC_RE = re.compile(r"^(?:[a-z][a-z0-9]*-)?([1-9]\d{0,5})-")
PROJECT_IN_TOPIC_RE = re.compile(r"^([a-z][a-z0-9]*)-[1-9]\d{0,5}-")


@dataclass(frozen=True)
class TopicState:
    topic: str
    title: str
    kind: str | None      # 質問票を出すスキルが宣言する自由な種類名(無ければ None = 未分類)
    project: str | None
    issue: int | None
    state: State
    open_round: int | None
    round_count: int
    updated_at: str
    version: str          # データ JSON の mtime(ns)。統合ページが「内容が変わったか」を見るのに使う
    html_exists: bool
    archived: bool
    error: str | None = None


@dataclass(frozen=True)
class Snapshot:
    topics: tuple[TopicState, ...]
    generated_at: str


# ---------------------------------------------------------------- 共通ユーティリティ

def resolve_root() -> Path:
    """配信ルート。GRILL_ROOT(テスト用)があればそれ、無ければ ~/.agent/diagrams。"""
    return Path(os.environ.get("GRILL_ROOT") or DEFAULT_ROOT)


def sanitize_topic(raw: object) -> str:
    """回答ファイル名に使う topic。server.py の /submit と同じ規則。"""
    text = "" if raw is None else str(raw)
    cleaned = "".join(c for c in text if c.isalnum() or c in "-_")[:TOPIC_MAX_LEN]
    return cleaned or "untitled"


def write_json_atomic(path: Path, doc: dict) -> None:
    """tmp に書いてから rename する(読み手が途中の内容を見ない)。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _fmt(ts: float) -> str:
    return time.strftime(TIME_FMT, time.localtime(ts))


# ---------------------------------------------------------------- 設定(アーカイブ・種類の接頭辞)

def load_config(root: Path) -> dict:
    """統合ページの設定ファイル。無い・壊れている場合は空。"""
    try:
        doc = json.loads((root / ARCHIVE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def _str_map(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): str(v) for k, v in value.items() if isinstance(v, (str, int, float))}


def load_archive(root: Path) -> dict[str, str]:
    """{topic: アーカイブした時刻}。"""
    return _str_map(load_config(root).get("archived"))


def load_kind_prefixes(root: Path) -> dict[str, str]:
    """{topic の接頭辞: kind}。JSON に kind が無い題材(過去の分など)に環境側で種類を与える。"""
    return {k: v for k, v in _str_map(load_config(root).get("kind_prefixes")).items() if k}


def set_archived(root: Path, topic: str, archived: bool) -> dict[str, str]:
    """アーカイブ状態を書き換えて、新しい {topic: 時刻} を返す(他の設定は保つ)。"""
    config = load_config(root)
    current = _str_map(config.get("archived"))
    if archived:
        updated = {**current, topic: _fmt(time.time())}
    else:
        updated = {k: v for k, v in current.items() if k != topic}
    write_json_atomic(root / ARCHIVE_FILE, {**config, "archived": updated})
    return updated


# ---------------------------------------------------------------- 推定ルール

def detect_kind(topic: str, data: dict, prefixes: dict[str, str]) -> str | None:
    """明示の kind → 設定の接頭辞(長いものを優先)→ None。grill-visual 自身は種類の意味を知らない。"""
    explicit = data.get("kind")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    for prefix in sorted(prefixes, key=len, reverse=True):
        if topic.startswith(prefix):
            return prefixes[prefix]
    return None


def _as_issue(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def detect_issue(topic: str, title: str, data: dict) -> int | None:
    explicit = _as_issue(data.get("issue"))
    if explicit is not None:
        return explicit
    m = ISSUE_IN_TITLE_RE.search(title) or ISSUE_IN_TOPIC_RE.match(topic)
    return int(m.group(1)) if m else None


def detect_project(topic: str, data: dict, prefixes: dict[str, str]) -> str | None:
    explicit = data.get("project")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    if any(topic.startswith(p) for p in prefixes):  # 種類の接頭辞はプロジェクト名ではない
        return None
    m = PROJECT_IN_TOPIC_RE.match(topic)
    return m.group(1) if m else None


def inherit_project(topics: tuple[TopicState, ...]) -> tuple[TopicState, ...]:
    """project 不明の題材に、同じ issue 番号の題材の project が 1 種類だけならそれを借りる。"""
    by_issue: dict[int, set[str]] = {}
    for t in topics:
        if t.issue is not None and t.project:
            by_issue.setdefault(t.issue, set()).add(t.project)

    def fix(t: TopicState) -> TopicState:
        if t.project or t.issue is None:
            return t
        candidates = by_issue.get(t.issue, set())
        if len(candidates) != 1:
            return t
        return TopicState(**{**asdict(t), "project": next(iter(candidates))})

    return tuple(fix(t) for t in topics)


# ---------------------------------------------------------------- 状態

def _answer_path(root: Path, topic: str, rnd: int) -> Path:
    return root / ANSWERS_DIR / f"{sanitize_topic(topic)}-round-{rnd}.json"


def derive_state(topic: str, rounds: list, root: Path) -> tuple[State, int | None]:
    """render.py と同じく、open ラウンドのうち最後のものを現行ラウンドとみなす。"""
    opens = [r for r in rounds if isinstance(r, dict) and r.get("status") == "open"]
    if not opens:
        return "done", None
    n = int(opens[-1]["round"])
    return ("answered" if _answer_path(root, topic, n).exists() else "waiting"), n


def _updated_at(data_path: Path, root: Path, topic: str, open_round: int | None) -> str:
    stamps = [data_path.stat().st_mtime]
    if open_round is not None:
        ans = _answer_path(root, topic, open_round)
        if ans.exists():
            stamps.append(ans.stat().st_mtime)
    return _fmt(max(stamps))


def _error_state(path: Path, archived: dict[str, str], message: str) -> TopicState:
    try:
        st = path.stat()
        updated_at, version = _fmt(st.st_mtime), str(st.st_mtime_ns)
    except OSError:  # 読めなかった直後に消された(片付け中など)
        updated_at, version = "", "0"
    return TopicState(
        topic=path.stem, title=path.name, kind=None, project=None, issue=None,
        state="error", open_round=None, round_count=0, updated_at=updated_at, version=version,
        html_exists=(path.parent.parent / f"grill-{path.stem}.html").exists(),
        archived=path.stem in archived, error=message,
    )


def topic_state(path: Path, root: Path, archived: dict[str, str], prefixes: dict[str, str]) -> TopicState:
    """grill-data/<topic>.json 1 件を読む。壊れていても error 項目として返す(一覧から消さない)。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError("top level is not an object")
        topic = str(data.get("topic") or path.stem)
        if sanitize_topic(topic) != topic:
            raise ValueError(f"topic に使えない文字がある: {topic!r}")
        rounds = data["rounds"]
        if not isinstance(rounds, list):
            raise TypeError("rounds is not a list")
        st, open_round = derive_state(topic, rounds, root)
        title = str(data.get("title") or topic)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return _error_state(path, archived, f"{type(exc).__name__}: {exc}")
    return TopicState(
        topic=topic, title=title, kind=detect_kind(topic, data, prefixes),
        project=detect_project(topic, data, prefixes), issue=detect_issue(topic, title, data),
        state=st, open_round=open_round, round_count=len(rounds),
        updated_at=_updated_at(path, root, topic, open_round),
        version=str(path.stat().st_mtime_ns),
        html_exists=(root / f"grill-{topic}.html").exists(),
        archived=topic in archived,
    )


def scan(root: Path) -> Snapshot:
    config = load_config(root)
    archived = _str_map(config.get("archived"))
    prefixes = {k: v for k, v in _str_map(config.get("kind_prefixes")).items() if k}
    data_dir = root / DATA_DIR
    paths = sorted(data_dir.glob("*.json")) if data_dir.is_dir() else []
    topics = tuple(topic_state(p, root, archived, prefixes) for p in paths)
    return Snapshot(topics=inherit_project(topics), generated_at=_fmt(time.time()))


def snapshot_to_dict(snap: Snapshot) -> dict:
    counts = {s: 0 for s in STATES}
    for t in snap.topics:
        counts[t.state] += 1
    return {
        "generated_at": snap.generated_at,
        "counts": counts,
        "topics": [asdict(t) for t in snap.topics],
    }
