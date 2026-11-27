"""chat.py: 質問票の各問のチャット(ファイル 1 つ = 1 題材、1 行 = 1 発言)。"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import chat

SKILL_DIR = Path(__file__).resolve().parent.parent


def test_append_and_read_roundtrip(root: Path):
    m1 = chat.append(root, "t1", "Q1", "user", "A と B の違いは?")
    m2 = chat.append(root, "t1", "Q1", "ai", "A は速く、B は安全です。")
    assert (m1["id"], m2["id"]) == (1, 2)
    msgs = chat.read(root, "t1")
    assert [m["from"] for m in msgs] == ["user", "ai"]
    assert msgs[0]["q"] == "Q1" and msgs[1]["text"] == "A は速く、B は安全です。"
    assert all("at" in m for m in msgs)


def test_read_missing_topic_is_empty(root: Path):
    assert chat.read(root, "nothing") == []


def test_read_skips_broken_lines(root: Path):
    chat.append(root, "t2", "Q1", "user", "ok")
    with chat.chat_path(root, "t2").open("a", encoding="utf-8") as f:
        f.write("{broken\n")
    assert len(chat.read(root, "t2")) == 1


@pytest.mark.parametrize("q", ["", "Q 1", "Q1<script>", "x" * 41])
def test_rejects_bad_question_id(root: Path, q: str):
    with pytest.raises(ValueError):
        chat.append(root, "t3", q, "user", "hi")


@pytest.mark.parametrize("text", ["", "   ", "あ" * (chat.MAX_TEXT + 1)])
def test_rejects_bad_text(root: Path, text: str):
    with pytest.raises(ValueError):
        chat.append(root, "t3", "Q1", "user", text)


def test_rejects_bad_sender(root: Path):
    with pytest.raises(ValueError):
        chat.append(root, "t3", "Q1", "admin", "hi")


def test_rejects_bad_topic(root: Path):
    with pytest.raises(ValueError):
        chat.append(root, "../etc", "Q1", "user", "hi")


def run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    env = {"GRILL_ROOT": str(root), "PATH": "/usr/bin:/bin"}
    return subprocess.run([sys.executable, str(SKILL_DIR / "chat.py"), *args],
                          capture_output=True, text=True, env=env, timeout=20)


def test_cli_reply_writes_ai_message(root: Path):
    res = run_cli(root, "reply", "t4", "Q2", "推奨は A です。理由は…")
    assert res.returncode == 0, res.stderr
    msgs = chat.read(root, "t4")
    assert msgs[-1]["from"] == "ai" and msgs[-1]["q"] == "Q2"


def test_cli_watch_prints_new_user_messages_and_exits_on_answer(root: Path):
    chat.append(root, "t5", "Q1", "user", "古い質問")  # 監視を始める前の発言は流さない
    proc = subprocess.Popen([sys.executable, str(SKILL_DIR / "chat.py"), "watch", "t5", "1", "--interval", "0.1"],
                            stdout=subprocess.PIPE, text=True,
                            env={"GRILL_ROOT": str(root), "PATH": "/usr/bin:/bin"})
    import time
    time.sleep(0.5)
    chat.append(root, "t5", "Q3", "user", "この選択肢の意味は?")
    chat.append(root, "t5", "Q3", "ai", "AI の返事は流さない")
    time.sleep(0.5)
    answers = root / "answers"
    answers.mkdir(exist_ok=True)
    (answers / "t5-round-1.json").write_text(json.dumps({"answers": {}}), encoding="utf-8")
    out, _ = proc.communicate(timeout=10)
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert any("Q3" in ln and "この選択肢の意味は?" in ln for ln in lines)
    assert not any("古い質問" in ln or "AI の返事" in ln for ln in lines)
    assert "回答" in lines[-1]
    assert proc.returncode == 0
