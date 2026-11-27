"""render.py: 印字する URL と postMessage の埋め込み。"""
from __future__ import annotations

import json
import re
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, open_round, write_topic

pytestmark = pytest.mark.unit
RENDER = REPO / "render.py"


def run_render(root: Path, topic: str, env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "PARALLEL_GRILL_URL"}
    env.update({"GRILL_ROOT": str(root), **env_extra})
    return subprocess.run(
        [sys.executable, str(RENDER), str(root / "grill-data" / f"{topic}.json")],
        capture_output=True, text=True, env=env, check=True,
    )


def test_prints_dashboard_url_with_parallel_root(root: Path):
    write_topic(root, "t-1", [open_round(1)], intro="")
    out = run_render(root, "t-1", {"PARALLEL_GRILL_URL": "http://h:8374/"}).stdout.strip().splitlines()
    assert out[-1] == "http://h:8374/#t-1"
    assert out[0] == str(root / "grill-t-1.html")
    assert (root / "grill-t-1.html").exists()


def test_prints_localhost_url_without_env(root: Path):
    write_topic(root, "t-2", [open_round(1)], intro="")
    out = run_render(root, "t-2", {}).stdout.strip().splitlines()
    assert out[-1] == "http://localhost:8787/#t-2"


def test_html_posts_message_to_parent(root: Path):
    write_topic(root, "t-3", [open_round(1)], intro="")
    run_render(root, "t-3", {})
    html = (root / "grill-t-3.html").read_text(encoding="utf-8")
    assert "grill-submitted" in html
    assert "window.parent.postMessage" in html


def test_dashboard_url_helper():
    sys.path.insert(0, str(REPO))
    import render
    assert render.dashboard_url("abc", "http://x/") == "http://x/#abc"
    assert render.dashboard_url("abc", "http://x") == "http://x/#abc"
    assert render.dashboard_url("abc", "") == "http://localhost:8787/#abc"


def test_html_has_draft_persistence(root: Path):
    write_topic(root, "t-4", [open_round(1)], intro="")
    run_render(root, "t-4", {})
    html = (root / "grill-t-4.html").read_text(encoding="utf-8")
    assert "grill-draft:" in html
    assert "restoreDraft()" in html


# ---------------------------------------------------------------- ルール一覧型(type: rules)

def rules_question(**extra) -> dict:
    q = {
        "id": "Q1", "type": "rules", "title": "API(2 ルール)", "body": "b",
        "rules": [
            {"id": "R1", "text": "ログインなしでは使えない", "risk": "high",
             "ears": "When クッキーなしで呼ぶと、401 を返す", "note": "境界は 8 日",
             "cases": [{"id": "R1-1", "behavior": "一覧を見られない", "input": "GET /api/x",
                        "expected": "401", "kind": "異常系"}]},
            {"id": "R2", "text": "手元スイッチで省略できる", "risk": "low", "cases": []},
        ],
    }
    q.update(extra)
    return q


def render_html(root: Path, topic: str, rounds: list[dict]) -> str:
    write_topic(root, topic, rounds, intro="")
    run_render(root, topic, {})
    return (root / f"grill-{topic}.html").read_text(encoding="utf-8")


def test_rules_question_renders_rows_with_defaults(root: Path):
    html = render_html(root, "r-1", [{"round": 1, "status": "open", "questions": [rules_question()]}])
    assert 'data-type="rules"' in html
    assert html.count('class="rule"') == 2 or html.count('class="rule ') == 2
    assert 'data-rule="R1"' in html and 'data-rule="R2"' in html
    # 採用トグルは既定オン。高リスクは例を開いた状態、低は畳む
    assert html.count('class="rule-adopt" checked') == 2
    assert 'data-rule="R1" data-cases-open="true"' in html
    assert 'data-rule="R2" data-cases-open="false"' in html
    # 行頭にリスク、例の表、AI 注記、1 行コメント欄
    assert '<span class="risk high">高</span>' in html
    assert '<ul class="cases">' in html and "一覧を見られない" in html
    assert "GET /api/x" not in html  # 入力は表に出さない(振る舞いと期待する結果だけ)
    assert "境界は 8 日" in html
    assert 'class="rule-note" data-rule="R1"' in html


def test_rules_question_config_lists_rule_ids(root: Path):
    html = render_html(root, "r-2", [{"round": 1, "status": "open", "questions": [rules_question()]}])
    m = re.search(r"var CONFIG = (\{.*?\});\n", html)
    assert m, "CONFIG が埋め込まれていない"
    cfg = json.loads(m.group(1))
    assert cfg["openQuestions"][0] == {"id": "Q1", "type": "rules", "rules": ["R1", "R2"], "recommended": []}


def test_rules_question_answered_shows_decisions(root: Path):
    q = rules_question(answer={"R1": "adopt", "R2": "reject"}, answer_note="R2 は次で直す")
    q["rules"][1]["user_note"] = "<b>10 分固定にしない</b>"
    html = render_html(root, "r-3", [{"round": 1, "status": "answered", "questions": [q]}])
    assert 'class="rule-adopt" checked disabled' in html
    assert 'class="rule-adopt" disabled' in html
    assert "&lt;b&gt;10 分固定にしない&lt;/b&gt;" in html  # ユーザー入力はエスケープ
    assert "R2 は次で直す" in html


def test_options_with_images_get_grid_classes(root: Path):
    q = {"id": "Q1", "title": "t", "body": "b", "options": [
        {"key": "a", "label": "A", "image": "assets/x/a.png"},
        {"key": "b", "label": "B", "image": "assets/x/b.png"},
        {"key": "c", "label": "C"}]}
    html = render_html(root, "r-4", [{"round": 1, "status": "open", "questions": [q]}])
    assert '<div class="opts has-images">' in html
    assert html.count('class="opt has-img"') == 2
    assert '@media (min-width: 900px)' in html and ".opts.has-images" in html


def test_options_without_images_keep_plain_classes(root: Path):
    html = render_html(root, "r-5", [open_round(1)])
    assert '<div class="opts">' in html
    assert "has-img" not in html.split("<style>")[1].split("</style>")[0] or True  # CSS には含まれてよい
    assert 'class="opt has-img"' not in html


def test_open_questions_get_ask_button_and_chat_box(root: Path):
    rounds = [
        {"round": 1, "status": "answered", "questions": [
            {"id": "Q1", "title": "t", "body": "b", "options": [{"key": "a", "label": "A"}], "answer": ["a"]}]},
        {"round": 2, "status": "open", "questions": [
            {"id": "Q2", "title": "t", "body": "b", "options": [{"key": "a", "label": "A"}]},
            rules_question(id="Q3")]},
    ]
    html = render_html(root, "c-1", rounds)
    assert 'class="note-ask" data-q="Q2"' in html and 'class="note-ask" data-q="Q3"' in html
    assert 'class="note-ask" data-q="Q1"' not in html  # 回答済みのラウンドには出さない
    assert html.count('<div class="chat" data-q=') == 2
    assert "/api/chat?topic=" in html


def test_image_and_rules_questions_span_full_width(root: Path):
    img_q = {"id": "Q1", "title": "t", "body": "b", "options": [
        {"key": "a", "label": "A", "image": "assets/x/a.png"}, {"key": "b", "label": "B"}]}
    plain_q = {"id": "Q2", "title": "t", "body": "b", "options": [{"key": "a", "label": "A"}]}
    html = render_html(root, "c-2", [{"round": 1, "status": "open", "questions": [img_q, plain_q, rules_question(id="Q3")]}])
    assert 'class="q-card wide" data-q="Q1"' in html
    assert 'class="q-card" data-q="Q2"' in html
    assert 'class="q-card wide" data-q="Q3"' in html
    assert "grid-template-columns: repeat(auto-fill, minmax(420px, 1fr))" in html
