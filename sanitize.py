"""grill-visual: 質問票に入れる HTML 断片の許可リスト方式サニタイズ(標準ライブラリのみ)。

質問データの文字列は <code> や表・画像・リンクを使えるよう HTML として挿入する。
外部の文章(issue 本文など)が混ざってもスクリプトが動かないよう、許可したタグと属性だけを
通し、それ以外のタグは文字として見せる(エスケープ)。

- 許可しないタグ(script / iframe / style など)… 文字として表示
- on○○ などの許可しない属性 … 落とす
- href / src … http(s)・相対パス・# だけ。javascript: / data: / // で始まるものなどは属性ごと落とす
- style … 外部の読み込み(url( など)・CSS エスケープ(\)・画面への固定(position:fixed / sticky)を
  含むものは属性ごと落とす。position:absolute は使えるが、render.py 側で質問カードなどの枠の外に
  はみ出さないようにしている
- target 付きのリンク … rel="noopener noreferrer" を強制する
- 閉じ忘れたタグは末尾で閉じ、対応しない閉じタグは捨てる(質問票のレイアウトを崩さない)
- コメント … 落とす

限界: `a<b and c>d` のように「<」の直後が許可タグ名だと、そのタグとして解釈される。
文中で < を使うときは &lt; と書く。
"""
from __future__ import annotations

import html
import re
from html.parser import HTMLParser

ALLOWED_TAGS = frozenset({
    "a", "b", "br", "caption", "code", "details", "div", "em", "h3", "h4", "hr", "i", "img",
    "kbd", "li", "ol", "p", "pre", "small", "span", "strong", "summary",
    "table", "tbody", "td", "th", "thead", "tr", "ul",
})
VOID_TAGS = frozenset({"br", "hr", "img"})
ALLOWED_ATTRS = frozenset({
    "alt", "border", "cellpadding", "class", "colspan", "height", "href", "rel", "rowspan",
    "src", "style", "target", "title", "width",
})
URL_ATTRS = frozenset({"href", "src"})
FORCED_REL = "noopener noreferrer"
SAFE_SCHEMES = frozenset({"http", "https"})
SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.\-]*):")
# 制御文字・空白(java\tscript: のような分断を詰めてからスキームを判定する)
IGNORABLE_RE = re.compile(r"[\x00-\x20\x7f]+")
DANGEROUS_STYLE_RE = re.compile(
    r"javascript:|expression\s*\(|url\s*\(|image-set|@import|\\|behavior|binding"
    r"|position\s*:\s*(?:fixed|sticky)",
    re.IGNORECASE,
)


def _is_safe_url(value: str) -> bool:
    compact = IGNORABLE_RE.sub("", html.unescape(value)).lower()
    if compact.startswith(("//", "\\\\", "/\\", "\\/")):  # プロトコル相対(別ホストを指す)
        return False
    m = SCHEME_RE.match(compact)
    return m is None or m.group(1) in SAFE_SCHEMES


def _safe_attr(name: str, value: str | None) -> str | None:
    """通してよい属性なら値(エスケープ前)を返す。落とすなら None。"""
    if name not in ALLOWED_ATTRS or name == "rel":  # rel は target に合わせて付け直す
        return None
    value = value or ""
    if name in URL_ATTRS and not _is_safe_url(value):
        return None
    if name == "style" and DANGEROUS_STYLE_RE.search(value):
        return None
    return value


class _Sanitizer(HTMLParser):
    def __init__(self, keep_tags: bool) -> None:
        super().__init__(convert_charrefs=True)
        self.keep_tags = keep_tags
        self.out: list[str] = []
        self.open_tags: list[str] = []  # まだ閉じていない許可タグ(閉じ忘れの補完に使う)

    def _tag(self, tag: str, attrs: list[tuple[str, str | None]], closing: str) -> None:
        if not self.keep_tags:
            return
        if tag not in ALLOWED_TAGS:
            self.out.append(html.escape(self.get_starttag_text() or ""))
            return
        kept = [(n, v) for n, v in ((n, _safe_attr(n, v)) for n, v in attrs) if v is not None]
        if any(n == "target" for n, _ in kept):
            kept.append(("rel", FORCED_REL))
        rendered = "".join(f' {n}="{html.escape(v, quote=True)}"' for n, v in kept)
        self.out.append(f"<{tag}{rendered}{closing}>")
        if tag not in VOID_TAGS and not closing:
            self.open_tags.append(tag)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag(tag, attrs, "")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag(tag, attrs, "" if tag in VOID_TAGS else " /")

    def handle_endtag(self, tag: str) -> None:
        if not self.keep_tags:
            return
        if tag not in ALLOWED_TAGS:
            self.out.append(html.escape(f"</{tag}>"))
            return
        if tag not in self.open_tags:
            return  # 対応する開始タグが無い閉じタグは捨てる
        while self.open_tags:  # 内側の閉じ忘れを閉じてから、このタグを閉じる
            inner = self.open_tags.pop()
            self.out.append(f"</{inner}>")
            if inner == tag:
                break

    def close_all(self) -> None:
        while self.open_tags:
            self.out.append(f"</{self.open_tags.pop()}>")

    def handle_data(self, data: str) -> None:
        self.out.append(html.escape(data, quote=False))

    def handle_comment(self, data: str) -> None:
        pass  # コメントは落とす(条件付きコメント等の抜け道を作らない)

    def handle_decl(self, decl: str) -> None:
        pass

    def handle_pi(self, data: str) -> None:
        pass

    def unknown_decl(self, data: str) -> None:
        pass


def _run(value: str | None, keep_tags: bool) -> str:
    if not value:
        return ""
    parser = _Sanitizer(keep_tags)
    parser.feed(str(value))
    parser.close()
    parser.close_all()
    return "".join(parser.out)


def safe_html(value: str | None) -> str:
    """許可したタグ・属性だけを残した HTML 断片を返す。"""
    return _run(value, keep_tags=True)


def to_text(value: str | None) -> str:
    """タグを外したテキスト(HTML エスケープ済み)。<title> など、タグを使えない場所用。"""
    return _run(value, keep_tags=False)


def safe_url(value: str | None) -> str:
    """属性値に入れる URL。危険なスキームなら空文字。返り値は属性用にエスケープ済み。"""
    if not value or not _is_safe_url(value):
        return ""
    return html.escape(value, quote=True)
