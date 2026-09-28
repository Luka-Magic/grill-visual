"""共通 fixture: 一時的な ~/.agent/diagrams 相当のルートと、題材/回答ファイルの書き出しヘルパ。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "grill-data").mkdir()
    (tmp_path / "answers").mkdir()
    return tmp_path


def write_topic(root: Path, topic: str, rounds: list[dict], title: str | None = None, **extra) -> Path:
    doc = {"topic": topic, "title": title if title is not None else f"title of {topic}", "rounds": rounds}
    doc.update(extra)
    path = root / "grill-data" / f"{topic}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return path


def write_answer(root: Path, topic: str, rnd: int) -> Path:
    answers = root / "answers"
    answers.mkdir(exist_ok=True)
    path = answers / f"{topic}-round-{rnd}.json"
    path.write_text(json.dumps({"topic": topic, "round": rnd, "answers": {}}), encoding="utf-8")
    return path


def write_html(root: Path, topic: str) -> Path:
    path = root / f"grill-{topic}.html"
    path.write_text("<html></html>", encoding="utf-8")
    return path


def open_round(n: int, questions: int = 1) -> dict:
    return {"round": n, "status": "open", "questions": [{"id": f"Q{i}", "title": "t", "body": "b", "options": [{"key": "a", "label": "A"}]} for i in range(1, questions + 1)]}


def answered_round(n: int) -> dict:
    return {"round": n, "status": "answered", "questions": []}


def info_round(n: int) -> dict:
    return {"round": n, "status": "info", "declarations": ["done"]}
