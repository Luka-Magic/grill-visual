"""sanitize.py: 質問票に入れる HTML 断片の許可リスト方式サニタイズ。"""
from __future__ import annotations

import pytest

from sanitize import safe_html, safe_url, to_text

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "src",
    [
        "<code>render.py</code> と <strong>太字</strong><br><em>強調</em><small>小</small>",
        '<table class="cases"><thead><tr><th>#</th></tr></thead><tbody><tr><td rowspan="2">1</td></tr></tbody></table>',
        '<a href="https://example.com/x?a=1&amp;b=2">リンク</a>',
        '<a href="assets/t/index.html">モック</a>',
        '<img src="assets/t/x.png" alt="画面">',
        '<div style="display:grid;width:364px">x</div><span class="badge">y</span>',
        '<div style="position:relative"><span style="position:absolute;top:4px;left:8px">1</span></div>',
        "<ul><li>a</li></ul><ol><li>b</li></ol><p>c</p><pre>d</pre><h3>e</h3>",
        "<details><summary>開く</summary>中身</details>",
        "記号 &lt;tag&gt; と &amp; はそのまま",
    ],
)
def test_allowed_markup_is_kept(src: str):
    assert safe_html(src) == src


def test_plain_text_is_unchanged():
    assert safe_html("ただの文章 (a) / Q1") == "ただの文章 (a) / Q1"


@pytest.mark.parametrize(
    "src,expected",
    [
        ("<script>alert(1)</script>", "&lt;script&gt;alert(1)&lt;/script&gt;"),
        ("<iframe src=\"https://e.test\"></iframe>", "&lt;iframe src=&quot;https://e.test&quot;&gt;&lt;/iframe&gt;"),
        ("<style>body{}</style>", "&lt;style&gt;body{}&lt;/style&gt;"),
    ],
)
def test_disallowed_tags_are_shown_as_text(src: str, expected: str):
    assert safe_html(src) == expected


def test_event_handler_attributes_are_dropped():
    assert safe_html('<img src="a.png" onerror="alert(1)">') == '<img src="a.png">'
    assert safe_html('<span onclick="x()" class="c">t</span>') == '<span class="c">t</span>'


@pytest.mark.parametrize(
    "href",
    ["javascript:alert(1)", "JavaScript:alert(1)", " javascript:alert(1)", "java&#x09;script:alert(1)",
     "data:text/html,<script>alert(1)</script>", "vbscript:x", "&#106;avascript:x", "javascript&colon;x",
     "//evil.example/x", "\\\\evil.example/x"],
)
def test_dangerous_urls_are_dropped(href: str):
    out = safe_html(f'<a href="{href}">x</a>')
    assert out == "<a>x</a>"


@pytest.mark.parametrize(
    "style",
    ["background:url(javascript:x)", "width:expression(alert(1))", "background:\\75rl(http://e.test/x)",
     "position:fixed;inset:0", "position: sticky", "background-image:image-set('x.png' 1x)", "-moz-binding:x"],
)
def test_dangerous_style_is_dropped(style: str):
    assert safe_html(f'<div style="{style}">t</div>') == "<div>t</div>"


def test_target_forces_noopener():
    assert safe_html('<a href="a.html" target="_blank" rel="opener">x</a>') == (
        '<a href="a.html" target="_blank" rel="noopener noreferrer">x</a>')


@pytest.mark.parametrize(
    "src,expected",
    [
        ("<div>unclosed<table><tr><td>x", "<div>unclosed<table><tr><td>x</td></tr></table></div>"),
        ("<p>a</p></p></div>", "<p>a</p>"),
        ("<b><i>x</b>y</i>", "<b><i>x</i></b>y"),
        ("<A HREF=\"JaVaScRiPt:x\">l</A><IMG SRC=x ONERROR=y>", '<a>l</a><img src="x">'),
        ("<img/src=x/onerror=1>", '<img src="x/onerror=1">'),
        ("<svg onload=alert(1)>", "&lt;svg onload=alert(1)&gt;"),
    ],
)
def test_structure_is_balanced(src: str, expected: str):
    assert safe_html(src) == expected


def test_comments_are_dropped():
    assert safe_html("a<!-- x -->b") == "ab"


def test_attribute_values_are_reescaped():
    assert safe_html('<span title="a&quot;b">t</span>') == '<span title="a&quot;b">t</span>'


def test_none_and_empty():
    assert safe_html(None) == ""
    assert safe_html("") == ""


@pytest.mark.parametrize(
    "url,expected",
    [
        ("assets/t/x.png", "assets/t/x.png"),
        ("https://e.test/a.png", "https://e.test/a.png"),
        ("#top", "#top"),
        ("javascript:alert(1)", ""),
        ("//evil.example/x.png", ""),
        ('a.png" onerror="x', "a.png&quot; onerror=&quot;x"),
    ],
)
def test_safe_url(url: str, expected: str):
    assert safe_url(url) == expected


def test_to_text_strips_tags_and_escapes():
    assert to_text("<code>a</code> &amp; <b>b</b>") == "a &amp; b"
    assert to_text("<script>x</script>") == "x"
