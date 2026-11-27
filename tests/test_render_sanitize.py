"""render.py: 質問データを HTML に入れるときのサニタイズ(sanitize.py の組み込み)。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from html.parser import HTMLParser
from pathlib import Path

import pytest

from conftest import REPO, open_round, write_topic

pytestmark = pytest.mark.unit
RENDER = REPO / "render.py"
XSS = '<script>alert(1)</script><img src="x" onerror="alert(2)"><a href="javascript:alert(3)">l</a>'
ATTR_BREAK = 'x" onmouseover="alert(9)'


def render(root: Path, topic: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RENDER), str(root / "grill-data" / f"{topic}.json")],
        capture_output=True, text=True, env={**os.environ, "GRILL_ROOT": str(root)}, check=check,
    )


def page_of(root: Path, topic: str) -> str:
    render(root, topic)
    return (root / f"grill-{topic}.html").read_text(encoding="utf-8")


def body_of(page: str) -> str:
    """質問データが入る部分(<body> から、自前の <script> の手前まで)。"""
    return page.split("<body", 1)[1].rsplit("<script>", 1)[0]


class _Attrs(HTMLParser):
    """ブラウザと同じ見方で、タグと属性を拾う。"""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, {k: v or "" for k, v in attrs}))


def assert_no_active_markup(body: str) -> None:
    """スクリプト・イベント属性・javascript: の URL が、タグや属性として残っていないこと。"""
    parser = _Attrs()
    parser.feed("<body" + body)
    assert parser.tags
    for tag, attrs in parser.tags:
        assert tag not in {"script", "iframe", "style"}, tag
        assert not [k for k in attrs if k.startswith("on")], (tag, attrs)
        for name in ("href", "src"):
            assert not attrs.get(name, "").strip().lower().startswith(("javascript:", "data:")), (tag, attrs)


def choice_question(**extra) -> dict:
    return {
        "id": "Q1", "title": XSS, "body": XSS, "why": XSS, "answer_note": XSS,
        "image": "javascript:alert(4)", "image_caption": XSS,
        "options": [{"key": "a", "label": XSS, "recommended": True, "image": 'x.png" onerror="alert(5)'}],
        **extra,
    }


def rules_question(**extra) -> dict:
    return {
        "id": "Q2", "type": "rules", "title": XSS, "body": XSS, "why": XSS, "answer_note": XSS,
        "rules": [{
            "id": "R1", "text": XSS, "risk": "high", "ears": XSS, "note": XSS,
            "cases": [{"behavior": XSS, "expected": XSS}],
        }],
        **extra,
    }


def test_script_tags_and_event_attributes_are_neutralized_in_every_field(root: Path):
    rounds = [
        {"round": 1, "status": "answered", "label": XSS, "facts": [XSS], "declarations": [XSS],
         "questions": [choice_question(answer=["a"]), rules_question(answer={"R1": "reject"})]},
        {"round": 2, "status": "open", "label": XSS, "questions": [choice_question(), rules_question()]},
    ]
    write_topic(root, "x-1", rounds, title=XSS, intro=XSS,
                tree=[{"label": XSS, "status": ATTR_BREAK, "note": XSS, "children": [{"label": XSS}]}])
    page = page_of(root, "x-1")
    assert_no_active_markup(body_of(page))
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page  # 消さずに文字として見せる
    assert page.count("<script>") == 1 and page.count("</script>") == 1  # 自前の 1 組だけ


def test_title_tag_gets_plain_text(root: Path):
    write_topic(root, "x-2", [open_round(1)], title="<strong>太字</strong></title><script>alert(1)</script>")
    page = page_of(root, "x-2")
    assert "<title>Grill: 太字alert(1)</title>" in page
    assert "<h1><strong>太字</strong>" in page


def test_allowed_markup_still_renders(root: Path):
    q = {"id": "Q1", "title": "<code>x</code>", "body": '<a href="https://example.com/" target="_blank">資料</a>',
         "options": [{"key": "a", "label": "<strong>A</strong>"}]}
    write_topic(root, "x-3", [{"round": 1, "status": "open", "questions": [q]}], intro="<em>前置き</em>")
    body = body_of(page_of(root, "x-3"))
    assert "<code>x</code>" in body and "<strong>A</strong>" in body and "<em>前置き</em>" in body
    assert '<a href="https://example.com/" target="_blank" rel="noopener noreferrer">資料</a>' in body


@pytest.mark.parametrize("url", ["javascript:alert(1)", "JaVa\tScript:alert(1)", "data:text/html,<script>alert(1)</script>", "//example.com/x.png"])
def test_unsafe_image_urls_are_dropped(root: Path, url: str):
    q = {"id": "Q1", "title": "t", "body": "b", "image": url, "options": [{"key": "a", "label": "A", "image": url}]}
    write_topic(root, "x-4", [{"round": 1, "status": "open", "questions": [q]}])
    body = body_of(page_of(root, "x-4"))
    assert body.count('<img src="" alt="">') == 3  # 問いの画像・選択肢の画像・ライトボックス
    assert_no_active_markup(body)


def test_safe_image_urls_are_kept(root: Path):
    q = {"id": "Q1", "title": "t", "body": "b", "image": "assets/x-5/a.png",
         "options": [{"key": "a", "label": "A", "image": "https://example.com/b.png?x=1&y=2"}]}
    write_topic(root, "x-5", [{"round": 1, "status": "open", "questions": [q]}])
    body = body_of(page_of(root, "x-5"))
    assert '<img src="assets/x-5/a.png" alt="">' in body
    assert '<img src="https://example.com/b.png?x=1&amp;y=2" alt="">' in body


def test_user_input_is_escaped_not_treated_as_html(root: Path):
    typed = '<b>太字のつもり</b> & <img src=x onerror=alert(1)> "引用"'
    rounds = [{
        "round": 1, "status": "answered", "free_text_answer": typed,
        "questions": [
            {"id": "Q1", "title": "t", "body": "b", "options": [{"key": "a", "label": "A"}], "answer": ["a"], "user_note": typed},
            {"id": "Q2", "type": "rules", "title": "t", "body": "b", "answer": {"R1": "adopt"}, "user_note": typed,
             "rules": [{"id": "R1", "text": "r", "risk": "low", "user_note": typed}]},
        ],
    }]
    write_topic(root, "x-6", rounds)
    body = body_of(page_of(root, "x-6"))
    assert "<b>太字のつもり</b>" not in body
    assert "<img src=x" not in body
    escaped = "&lt;b&gt;太字のつもり&lt;/b&gt; &amp; &lt;img src=x onerror=alert(1)&gt;"
    assert body.count(escaped) == 4  # 自由記述・問いのメモ 2 つ・行のコメント(value 属性)
    assert 'value="' + escaped + " &quot;引用&quot;" + '"' in body


def test_ids_and_keys_are_escaped_in_attributes_and_text(root: Path):
    rounds = [{"round": ATTR_BREAK, "status": "open", "questions": [
        {"id": ATTR_BREAK, "title": "t", "body": "b", "options": [{"key": ATTR_BREAK, "label": "A"}]},
        {"id": "Q2", "type": "rules", "title": "t", "body": "b",
         "rules": [{"id": ATTR_BREAK, "text": "r", "risk": ATTR_BREAK}]},
    ]}]
    write_topic(root, "x-7", rounds)
    page = page_of(root, "x-7")
    assert_no_active_markup(body_of(page))
    assert 'data-q="x&quot; onmouseover=&quot;alert(9)"' in page
    assert 'data-key="x&quot; onmouseover=&quot;alert(9)"' in page
    assert 'data-rule="x&quot; onmouseover=&quot;alert(9)"' in page
    assert 'id="pane-x&quot; onmouseover=&quot;alert(9)"' in page


def test_script_json_cannot_close_the_script_tag(root: Path):
    evil = "</script><script>alert(1)//"
    write_topic(root, "x-8", [{"round": 1, "status": "open", "questions": [
        {"id": evil, "title": "t", "body": "b", "options": [{"key": "a", "label": "A", "recommended": True}]}]}])
    page = page_of(root, "x-8")
    assert page.count("</script>") == 1
    config = json.loads(re.search(r"var CONFIG = (\{.*?\});\n", page).group(1))
    assert config["openQuestions"][0]["id"] == evil  # ブラウザが読む値は元のまま


@pytest.mark.parametrize("topic", ["../evil", "a/b", "a b", "<script>", ""])
def test_rejects_topic_outside_the_allowed_characters(root: Path, topic: str):
    path = write_topic(root, "ok", [open_round(1)])
    doc = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**doc, "topic": topic}), encoding="utf-8")
    proc = render(root, "ok", check=False)
    assert proc.returncode != 0
    assert "topic" in proc.stderr
    assert list(root.glob("grill-*.html")) == []
    assert not (root.parent / "grill-evil.html").exists()


def test_rules_and_cases_keep_allowed_markup(root: Path):
    q = {"id": "Q1", "type": "rules", "title": "ルール", "body": "<code>b</code>", "rules": [{
        "id": "R1", "text": "<strong>必ず</strong>保存する", "risk": "high",
        "ears": "<code>WHEN</code> 保存を押す", "note": "<em>補足</em>",
        "cases": [{"behavior": "<code>a.txt</code> を保存", "expected": "一覧に <strong>a.txt</strong> が出る"}],
    }]}
    write_topic(root, "x-9", [{"round": 1, "status": "open", "questions": [q]}])
    body = body_of(page_of(root, "x-9"))
    assert '<div class="rule-text"><strong>必ず</strong>保存する</div>' in body
    assert '<div class="rule-ears"><code>WHEN</code> 保存を押す</div>' in body
    assert '<div class="rule-ai-note"><em>補足</em></div>' in body
    assert '<span class="do"><code>a.txt</code> を保存</span>' in body
    assert '<span class="then">一覧に <strong>a.txt</strong> が出る</span>' in body
    assert '<span class="risk high">高</span>' in body
    assert body.count("<svg") >= 3  # icons.py のアイコンはサニタイズに通さず、そのまま出る
