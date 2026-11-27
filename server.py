#!/usr/bin/env python3
"""grill-visual: 質問票の配信・回答受信・統合ページ(127.0.0.1:8787、ループバック限定)。

GET  /  /index.html   … 統合ページ(dashboard.html。スキルのディレクトリから毎回読む)
GET  /api/state       … 全題材の状態 JSON(state.scan の結果。待ち/回答済み/完了/エラー)
GET  /<file>.html 等  … ~/.agent/diagrams/ の静的配信(従来どおり)
POST /submit          … 質問票の回答 JSON を ~/.agent/diagrams/answers/ に保存
                        (エージェントはこのファイルの出現を監視して回答を受け取る)
POST /api/archive     … {"topic": str, "archived": bool} を .grill-dashboard.json に保存
GET  /api/chat?topic= … その題材の各問のチャット({"messages": [...]})
POST /api/chat        … {"topic": str, "q": "Q3", "text": str} をユーザーの発言として追記
                        (AI は chat.py watch で受け取り、chat.py reply で返事を書く)
GET  /ui-comments/overlay.js、/api/threads… … ui-comments の専用サーバー(127.0.0.1:GRILL_UI_COMMENTS_PORT、
                        既定 4320)への中継。GRILL_UI_COMMENTS=1 のときだけ。そのときは統合ページと
                        質問票(grill-*.html)の </body> の前に道具の <script> を差し込む。
                        見た目を直す間のお試し用のサーバー(trial.sh)だけで使い、普段使いには入れない

環境変数(テスト用。通常は未設定でよい):
  GRILL_ROOT … 配信ルート(既定 ~/.agent/diagrams)
  GRILL_PORT … ポート(既定 8787)
  GRILL_UI_COMMENTS … 1 なら ui-comments を入れる(trial.sh が付ける)
"""
from __future__ import annotations

import functools
import http.client
import json
import os
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

import chat
import state

ROOT = state.resolve_root()
PORT = int(os.environ.get("GRILL_PORT", "8787"))
BIND = "127.0.0.1"
SKILL_DIR = Path(__file__).resolve().parent
DASHBOARD = SKILL_DIR / "dashboard.html"
MAX_BODY_BYTES = 1_000_000
DRAIN_LIMIT_BYTES = 8 * MAX_BODY_BYTES  # 大きすぎる本文は読み捨ててから 400 を返す(この上限を超えたら切る)
NO_STORE = "no-store"
UI_COMMENTS_PORT = int(os.environ.get("GRILL_UI_COMMENTS_PORT", "4320"))
UI_COMMENTS_PREFIXES = ("/api/threads",)
UI_COMMENTS = os.environ.get("GRILL_UI_COMMENTS") == "1"
# 統合ページ用。質問票は iframe の中にあり右下に自分のボタンを持つので、統合ページのボタンは上のバーの空きに置く
UI_COMMENTS_DASHBOARD = """<script>
  // ui-comments のボタンの初期位置。質問票の iframe の中にも同じボタンが右下にあるので、
  // 広い画面では上のバーの空き(更新時刻の左)、狭い画面では左下に置く。
  // 一覧に重なっていた旧い初期位置(v1)は一度だけ置き直す。ドラッグで動かした位置はそのまま使われる
  try {
    var key = "ui-comments:" + location.origin + ":grill-dashboard:pos";
    var seeded = key + ":seed";
    if (localStorage.getItem(seeded) !== "v2") {
      var pos = innerWidth >= 760
        ? { x: Math.max(0, innerWidth - 300), y: 0 }
        : { x: 16, y: Math.max(0, innerHeight - 150) };
      localStorage.setItem(key, JSON.stringify(pos));
      localStorage.setItem(seeded, "v2");
    }
  } catch (e) { /* 保存できなければ既定の位置 */ }
</script>
<script src="/ui-comments/overlay.js" data-project="grill-dashboard" defer></script>
"""
UI_COMMENTS_SHEET = '<script src="/ui-comments/overlay.js" data-project="grill-sheet" defer></script>\n'


def inject_before_body_end(html: bytes, snippet: str) -> bytes:
    """</body> の直前に snippet を入れる。</body> が無ければ末尾に足す。"""
    data = snippet.encode("utf-8")
    i = html.rfind(b"</body>")
    return html + data if i < 0 else html[:i] + data + html[i:]

_ARCHIVE_LOCK = threading.Lock()


class Handler(SimpleHTTPRequestHandler):
    # ブラウザが接続を掴んだままでも他のリクエストを受けられるよう
    # ThreadingHTTPServer で並行処理し、放置接続はタイムアウトで切る
    timeout = 30

    def __init__(self, *args, root: Path, **kwargs):
        self.root = root
        super().__init__(*args, directory=str(root), **kwargs)

    # ---------------------------------------------------------------- 応答ヘルパ

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", NO_STORE)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_json(self, doc: dict, status: int = 200) -> None:
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8", status)

    def _discard_body(self, length: int) -> None:
        remaining = min(length, DRAIN_LIMIT_BYTES)
        while remaining > 0:
            chunk = self.rfile.read(min(65536, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_BODY_BYTES:
            self._discard_body(length)
        if not 0 < length <= MAX_BODY_BYTES:
            raise ValueError("invalid body size")
        doc = json.loads(self.rfile.read(length))
        if not isinstance(doc, dict):
            raise ValueError("body must be a JSON object")
        return doc

    # ---------------------------------------------------------------- GET / HEAD

    def _is_ui_comments(self, path: str) -> bool:
        if not UI_COMMENTS:
            return False
        return path == "/ui-comments/overlay.js" or any(
            path == p or path.startswith(p + "/") for p in UI_COMMENTS_PREFIXES
        )

    def _proxy_ui_comments(self, path: str) -> None:
        """ui-comments の専用サーバーへそのまま渡す。Host は 127.0.0.1、Origin は渡さない
        (同じ URL から来た要求なので、専用サーバーの名前の確認はループバックとして通す)。"""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length > MAX_BODY_BYTES:
            self._discard_body(length)
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        target = "/overlay.js" if path == "/ui-comments/overlay.js" else self.path
        headers = {"Content-Type": self.headers.get("Content-Type", "application/json")} if body is not None else {}
        conn = http.client.HTTPConnection("127.0.0.1", UI_COMMENTS_PORT, timeout=10)
        try:
            conn.request(self.command, target, body=body, headers=headers)
            res = conn.getresponse()
            data = res.read()
        except OSError:
            self.send_error(502, "ui-comments server is not running")
            return
        finally:
            conn.close()
        self._send_bytes(data, res.getheader("Content-Type", "application/octet-stream"), res.status)

    def _route_get(self, path: str) -> bool:
        """自前のルートなら応答して True。静的配信に任せるなら False。"""
        if self._is_ui_comments(path):
            self._proxy_ui_comments(path)
        elif path in ("/", "/index.html"):
            self._send_dashboard()
        elif UI_COMMENTS and path.startswith("/grill-") and path.endswith(".html") and "/" not in path[1:]:
            self._send_sheet_with_comments(path)
        elif path == "/api/state":
            self._send_json(state.snapshot_to_dict(state.scan(self.root)))
        elif path == "/api/chat":
            self._get_chat()
        elif path.startswith("/api/"):
            self.send_error(404)
        else:
            return False
        return True

    def _send_dashboard(self) -> None:
        try:
            body = DASHBOARD.read_bytes()
        except OSError as exc:
            self.log_error("dashboard.html を読めない: %s", exc)
            self.send_error(500, "dashboard.html is missing")
            return
        if UI_COMMENTS:
            body = inject_before_body_end(body, UI_COMMENTS_DASHBOARD)
        self._send_bytes(body, "text/html; charset=utf-8")

    def _send_sheet_with_comments(self, path: str) -> None:
        """お試し用: 質問票に ui-comments の <script> を差し込んで返す。"""
        try:
            body = (self.root / path[1:]).read_bytes()
        except OSError:
            self.send_error(404)
            return
        self._send_bytes(inject_before_body_end(body, UI_COMMENTS_SHEET), "text/html; charset=utf-8")

    def _get_chat(self) -> None:
        query = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
        topic = (query.get("topic") or [""])[0]
        try:
            messages = chat.read(self.root, topic)
        except ValueError as exc:
            self.send_error(400, str(exc))
            return
        self._send_json({"messages": messages})

    def do_GET(self) -> None:
        if not self._route_get(self.path.split("?", 1)[0]):
            super().do_GET()

    def do_HEAD(self) -> None:
        if not self._route_get(self.path.split("?", 1)[0]):
            super().do_HEAD()

    # ---------------------------------------------------------------- POST

    def do_PATCH(self) -> None:
        path = self.path.split("?", 1)[0]
        if self._is_ui_comments(path):
            self._proxy_ui_comments(path)
        else:
            self.send_error(405)

    def do_DELETE(self) -> None:
        self.do_PATCH()

    def do_POST(self) -> None:
        path = self.path.split("?", 1)[0]
        if self._is_ui_comments(path):
            self._proxy_ui_comments(path)
            return
        handlers = {"/submit": self._post_submit, "/api/archive": self._post_archive, "/api/chat": self._post_chat}
        handler = handlers.get(path)
        if handler is None:
            self.send_error(404)
            return
        try:
            handler(self._read_json_body())
        except (ValueError, TypeError, KeyError) as exc:  # 入力の問題。理由をブラウザ側に返す(ローカル専用)
            self.send_error(400, str(exc))
        except Exception as exc:
            self.log_error("%s %s: %s: %s", self.command, path, type(exc).__name__, exc)
            self.send_error(500, "internal error")

    def _post_submit(self, doc: dict) -> None:
        topic = state.sanitize_topic(doc.get("topic", ""))
        rnd = int(doc.get("round", 0))
        saved = {**doc, "received_at": time.strftime(state.TIME_FMT)}
        state.write_json_atomic(self.root / state.ANSWERS_DIR / f"{topic}-round-{rnd}.json", saved)
        self._send_json({"ok": True})

    def _post_archive(self, doc: dict) -> None:
        topic = doc.get("topic")
        archived = doc.get("archived")
        if not isinstance(topic, str) or not topic or state.sanitize_topic(topic) != topic:
            raise ValueError("invalid topic")
        if not isinstance(archived, bool):
            raise ValueError("archived must be a boolean")
        with _ARCHIVE_LOCK:
            current = state.set_archived(self.root, topic, archived)
        self._send_json({"ok": True, "archived": sorted(current)})

    def _post_chat(self, doc: dict) -> None:
        # 送り手はブラウザからは常に user。AI の返事は chat.py reply だけが書く
        msg = chat.append(self.root, doc["topic"], doc.get("q", ""), "user", doc.get("text", ""))
        self._send_json({"ok": True, "message": msg})

    def log_message(self, *args) -> None:
        pass  # アクセスログ不要(常駐でログ肥大させない)

    def log_error(self, fmt: str, *args) -> None:  # エラーだけは .server.log(stderr)に残す
        print(f"[{time.strftime(state.TIME_FMT)}] {self.address_string()} {fmt % args}", file=sys.stderr, flush=True)


def make_server(root: Path, port: int) -> ThreadingHTTPServer:
    """root を配信するサーバー。port=0 で空きポート(テスト用)。"""
    root.mkdir(parents=True, exist_ok=True)
    return ThreadingHTTPServer((BIND, port), functools.partial(Handler, root=root))


if __name__ == "__main__":
    make_server(ROOT, PORT).serve_forever()
