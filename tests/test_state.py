"""state.py の単体テスト。"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import state
from conftest import answered_round, info_round, open_round, write_answer, write_html, write_topic

pytestmark = pytest.mark.unit


def by_topic(snap: state.Snapshot) -> dict[str, state.TopicState]:
    return {t.topic: t for t in snap.topics}


# ---------------------------------------------------------------- 状態の導出

def test_waiting_when_open_round_has_no_answer(root: Path):
    write_topic(root, "a", [answered_round(1), open_round(2)])
    write_answer(root, "a", 1)
    t = by_topic(state.scan(root))["a"]
    assert t.state == "waiting"
    assert t.open_round == 2
    assert t.round_count == 2


def test_answered_when_open_round_has_answer_file(root: Path):
    write_topic(root, "a", [open_round(1)])
    write_answer(root, "a", 1)
    assert by_topic(state.scan(root))["a"].state == "answered"


def test_done_when_no_open_round(root: Path):
    write_topic(root, "a", [answered_round(1), info_round(2)])
    t = by_topic(state.scan(root))["a"]
    assert t.state == "done"
    assert t.open_round is None


def test_info_only_round_is_done(root: Path):
    write_topic(root, "a", [info_round(1)])
    assert by_topic(state.scan(root))["a"].state == "done"


def test_open_round_in_middle_of_unordered_rounds(root: Path):
    write_topic(root, "a", [answered_round(1), open_round(3), answered_round(2), info_round(99)])
    t = by_topic(state.scan(root))["a"]
    assert t.state == "waiting"
    assert t.open_round == 3


def test_last_open_round_wins_when_duplicated(root: Path):
    write_topic(root, "a", [open_round(2), open_round(2)])
    write_answer(root, "a", 2)
    assert by_topic(state.scan(root))["a"].state == "answered"


def test_missing_answers_dir_is_waiting(tmp_path: Path):
    (tmp_path / "grill-data").mkdir()
    write_topic(tmp_path, "a", [open_round(1)])
    assert by_topic(state.scan(tmp_path))["a"].state == "waiting"


def test_missing_data_dir_gives_empty_snapshot(tmp_path: Path):
    snap = state.scan(tmp_path)
    assert snap.topics == ()


def test_malformed_json_becomes_error_entry_and_others_survive(root: Path):
    write_topic(root, "good", [open_round(1)])
    (root / "grill-data" / "bad.json").write_text("{not json", encoding="utf-8")
    (root / "grill-data" / "nokeys.json").write_text("{}", encoding="utf-8")
    topics = by_topic(state.scan(root))
    assert topics["good"].state == "waiting"
    assert topics["bad"].state == "error"
    assert topics["bad"].error
    assert topics["nokeys"].state == "error"


def test_html_exists_flag(root: Path):
    write_topic(root, "a", [open_round(1)])
    write_topic(root, "b", [open_round(1)])
    write_html(root, "a")
    topics = by_topic(state.scan(root))
    assert topics["a"].html_exists is True
    assert topics["b"].html_exists is False


def test_updated_at_takes_newer_answer_mtime(root: Path):
    data = write_topic(root, "a", [open_round(1)])
    ans = write_answer(root, "a", 1)
    old = time.time() - 3600
    os.utime(data, (old, old))
    t = by_topic(state.scan(root))["a"]
    expected = time.strftime(state.TIME_FMT, time.localtime(ans.stat().st_mtime))
    assert t.updated_at == expected


def test_version_tracks_data_file_only(root: Path):
    data = write_topic(root, "a", [open_round(1)])
    v1 = by_topic(state.scan(root))["a"].version
    write_answer(root, "a", 1)  # 回答が出ただけでは version は変わらない
    assert by_topic(state.scan(root))["a"].version == v1
    os.utime(data, None)
    now = time.time_ns()
    os.utime(data, ns=(now, now))
    assert by_topic(state.scan(root))["a"].version != v1


def test_title_falls_back_to_topic(root: Path):
    path = root / "grill-data" / "a.json"
    path.write_text(json.dumps({"topic": "a", "rounds": [open_round(1)]}), encoding="utf-8")
    assert by_topic(state.scan(root))["a"].title == "a"


# ---------------------------------------------------------------- 推定ルール

@pytest.mark.parametrize(
    "topic,title,extra,kind,project,issue",
    [
        ("tr-20-species", "#20 テストケース", {}, None, "tr", 20),
        ("birdlog-20-species", "#20 設計", {}, None, "birdlog", 20),
        ("26-trip-calendar", "#26 カレンダー", {}, None, None, 26),
        ("prompt-platform", "プロンプト改善", {}, None, None, None),
        ("pr38", "PR #38 の課題", {}, None, None, 38),
        ("rules-04-github", "04-github.md の精査", {}, None, None, None),
        ("tr-03-media-detail", "テストレビュー T03: 詳細画面", {}, None, None, None),
        ("x", "t", {"kind": "ui-check", "project": "p", "issue": 7}, "ui-check", "p", 7),
        ("x", "t", {"issue": "12"}, None, None, 12),
        ("x", "t", {"kind": "  計画 "}, "計画", None, None),
        ("x", "t", {"kind": ""}, None, None, None),
        ("x", "t", {"kind": 3}, None, None, None),
    ],
)
def test_heuristics(root: Path, topic, title, extra, kind, project, issue):
    write_topic(root, topic, [open_round(1)], title=title, **extra)
    t = by_topic(state.scan(root))[topic]
    assert (t.kind, t.project, t.issue) == (kind, project, issue)


def write_config(root: Path, doc: dict) -> None:
    (root / state.ARCHIVE_FILE).write_text(json.dumps(doc), encoding="utf-8")


@pytest.mark.parametrize(
    "topic,extra,kind,project",
    [
        ("tr-20-species", {}, "test-review", None),          # 接頭辞で種類が付き、tr はプロジェクトにしない
        ("ui-3-x", {}, "ui-check", None),
        ("ui-3-x", {"kind": "自分で決めた"}, "自分で決めた", None),  # 明示が優先
        ("tr-x-1-y", {}, "long", None),                      # 長い接頭辞を優先
        ("birdlog-20-species", {}, None, "birdlog"),
    ],
)
def test_kind_prefixes_from_config(root: Path, topic, extra, kind, project):
    write_config(root, {"kind_prefixes": {"tr-": "test-review", "ui-": "ui-check", "tr-x-": "long", "": "bad"}})
    write_topic(root, topic, [open_round(1)], title="t", **extra)
    t = by_topic(state.scan(root))[topic]
    assert (t.kind, t.project) == (kind, project)


def test_set_archived_keeps_other_config(root: Path):
    write_config(root, {"kind_prefixes": {"tr-": "test-review"}})
    state.set_archived(root, "a", True)
    doc = json.loads((root / state.ARCHIVE_FILE).read_text(encoding="utf-8"))
    assert doc["kind_prefixes"] == {"tr-": "test-review"}
    assert "a" in doc["archived"]
    assert state.load_kind_prefixes(root) == {"tr-": "test-review"}


def test_tr_topic_inherits_project_from_same_issue(root: Path):
    write_config(root, {"kind_prefixes": {"tr-": "test-review"}})
    write_topic(root, "birdlog-20-species", [info_round(1)], title="#20 設計")
    write_topic(root, "tr-20-species", [open_round(1)], title="#20 テスト")
    write_topic(root, "tr-9-other", [open_round(1)], title="#9 テスト")
    topics = by_topic(state.scan(root))
    assert topics["tr-20-species"].project == "birdlog"
    assert topics["tr-9-other"].project is None


def test_no_inherit_when_ambiguous(root: Path):
    write_config(root, {"kind_prefixes": {"tr-": "test-review"}})
    write_topic(root, "alpha-3-x", [info_round(1)], title="#3")
    write_topic(root, "beta-3-y", [info_round(1)], title="#3")
    write_topic(root, "tr-3-z", [open_round(1)], title="#3")
    assert by_topic(state.scan(root))["tr-3-z"].project is None


# ---------------------------------------------------------------- アーカイブ

def test_archive_roundtrip(root: Path):
    write_topic(root, "a", [info_round(1)])
    assert state.load_archive(root) == {}
    archived = state.set_archived(root, "a", True)
    assert "a" in archived
    assert by_topic(state.scan(root))["a"].archived is True
    assert (root / state.ARCHIVE_FILE).exists()
    archived = state.set_archived(root, "a", False)
    assert archived == {}
    assert by_topic(state.scan(root))["a"].archived is False


def test_malformed_archive_file_is_ignored(root: Path):
    (root / state.ARCHIVE_FILE).write_text("garbage", encoding="utf-8")
    write_topic(root, "a", [info_round(1)])
    assert state.load_archive(root) == {}
    assert by_topic(state.scan(root))["a"].archived is False


# ---------------------------------------------------------------- ユーティリティ

@pytest.mark.parametrize(
    "raw,expected",
    [("abc-D_1", "abc-D_1"), ("a b/c", "abc"), ("", "untitled"), ("x" * 100, "x" * 80), (None, "untitled")],
)
def test_sanitize_topic(raw, expected):
    assert state.sanitize_topic(raw) == expected


def test_write_json_atomic_leaves_no_tmp(tmp_path: Path):
    path = tmp_path / "out.json"
    state.write_json_atomic(path, {"k": "値"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "値"}
    assert not list(tmp_path.glob("*.tmp"))


def test_snapshot_to_dict_counts(root: Path):
    write_topic(root, "w", [open_round(1)])
    write_topic(root, "d", [info_round(1)])
    write_topic(root, "a", [open_round(1)])
    write_answer(root, "a", 1)
    (root / "grill-data" / "e.json").write_text("{", encoding="utf-8")
    d = state.snapshot_to_dict(state.scan(root))
    assert d["counts"] == {"waiting": 1, "answered": 1, "done": 1, "error": 1}
    assert {t["topic"] for t in d["topics"]} == {"w", "d", "a", "e"}
    assert d["generated_at"]


def test_resolve_root_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GRILL_ROOT", str(tmp_path))
    assert state.resolve_root() == tmp_path
    monkeypatch.delenv("GRILL_ROOT")
    assert state.resolve_root() == state.DEFAULT_ROOT


def test_error_state_survives_file_vanishing(root: Path):
    path = root / "grill-data" / "gone.json"
    path.write_text("{", encoding="utf-8")
    real_read = Path.read_text

    def read_then_delete(self, *a, **k):
        text = real_read(self, *a, **k)
        if self == path:
            self.unlink()
        return text

    import unittest.mock as um
    with um.patch.object(Path, "read_text", read_then_delete):
        t = by_topic(state.scan(root))["gone"]
    assert t.state == "error" and t.version == "0"


def test_topic_with_forbidden_chars_is_error(root: Path):
    path = root / "grill-data" / "x.json"
    path.write_text(json.dumps({"topic": "../evil", "rounds": [open_round(1)]}), encoding="utf-8")
    t = by_topic(state.scan(root))["x"]
    assert t.state == "error" and "topic" in (t.error or "")
