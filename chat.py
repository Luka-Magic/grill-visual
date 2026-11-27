#!/usr/bin/env python3
"""質問票の各問のチャット。1 題材 = 1 ファイル(chat/<topic>.jsonl)、1 行 = 1 発言。

ブラウザは server.py の /api/chat で書き込み・読み出しをする。AI 側はこの CLI を使う:

    python3 chat.py watch <topic> <round> [--interval 秒]
        監視を始めた後のユーザーの発言を 1 行ずつ印字する(Monitor で受け取る)。
        回答ファイル answers/<topic>-round-<round>.json が現れたら「回答が届いた」と印字して終わる。
    python3 chat.py reply <topic> <Q番号> <本文>
        AI の返事を書き込む。ブラウザは数秒以内にその問いの会話欄に表示する。

発言: {"id": 連番, "q": "Q3", "from": "user"|"ai", "text": str, "at": "YYYY-MM-DDTHH:MM:SS"}
"""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import state

CHAT_DIR = "chat"
MAX_TEXT = 2000
SENDERS = ("user", "ai")
QUESTION_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def chat_path(root: Path, topic: str) -> Path:
    if not topic or state.sanitize_topic(topic) != topic:
        raise ValueError("invalid topic")
    return root / CHAT_DIR / f"{topic}.jsonl"


def read(root: Path, topic: str) -> list[dict]:
    """その題材の全発言。壊れた行は飛ばす。"""
    path = chat_path(root, topic)
    if not path.exists():
        return []
    msgs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            doc = json.loads(line)
        except ValueError:
            continue
        if isinstance(doc, dict) and doc.get("from") in SENDERS:
            msgs.append(doc)
    return msgs


def append(root: Path, topic: str, q: str, sender: str, text: str) -> dict:
    """発言を 1 行追記して、その発言を返す。id はファイル内の連番(ロックの中で決める)。"""
    path = chat_path(root, topic)
    if not isinstance(q, str) or not QUESTION_RE.match(q):
        raise ValueError("invalid question id")
    if sender not in SENDERS:
        raise ValueError("invalid sender")
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
        raise ValueError(f"text must be 1..{MAX_TEXT} chars")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            count = sum(1 for line in f if line.strip())
            msg = {"id": count + 1, "q": q, "from": sender, "text": text.strip(),
                   "at": time.strftime(state.TIME_FMT)}
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            f.flush()
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
    return msg


def watch(root: Path, topic: str, rnd: int, interval: float) -> None:
    answer = root / state.ANSWERS_DIR / f"{topic}-round-{rnd}.json"
    seen = len(read(root, topic))
    print(f"監視中: {topic} ラウンド {rnd}(チャットと回答)", flush=True)
    while True:
        msgs = read(root, topic)
        for m in msgs[seen:]:
            if m["from"] == "user":
                print(f"[chat {m['q']}] {m['text']}", flush=True)
        seen = len(msgs)
        if answer.exists():
            print(f"回答が届いた: {answer}", flush=True)
            return
        time.sleep(interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("watch")
    w.add_argument("topic")
    w.add_argument("round", type=int)
    w.add_argument("--interval", type=float, default=1.0)
    r = sub.add_parser("reply")
    r.add_argument("topic")
    r.add_argument("q")
    r.add_argument("text")
    args = parser.parse_args(argv)
    root = state.resolve_root()
    try:
        if args.cmd == "watch":
            watch(root, args.topic, args.round, args.interval)
        else:
            msg = append(root, args.topic, args.q, "ai", args.text)
            print(f"返事を書いた: {args.topic} {msg['q']} #{msg['id']}")
    except ValueError as exc:
        print(f"エラー: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
