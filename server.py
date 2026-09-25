#!/usr/bin/env python3
"""grill-visual: 質問票の配信と回答受信(127.0.0.1:8787、ループバック限定)。

GET  /<file>.html … ~/.agent/diagrams/ の静的配信
POST /submit      … 質問票の回答 JSON を ~/.agent/diagrams/answers/ に保存
                    (エージェントはこのファイルの出現を監視して回答を受け取る)
"""
import json
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path.home() / ".agent" / "diagrams"
ANSWERS = ROOT / "answers"
PORT = 8787
MAX_BODY_BYTES = 1_000_000


class Handler(SimpleHTTPRequestHandler):
    # ブラウザが接続を掴んだままでも他のリクエストを受けられるよう
    # ThreadingHTTPServer で並行処理し、放置接続はタイムアウトで切る
    timeout = 30

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_POST(self):
        if self.path != "/submit":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= MAX_BODY_BYTES:
                raise ValueError("invalid body size")
            doc = json.loads(self.rfile.read(length))
            topic = "".join(
                c for c in str(doc.get("topic", "")) if c.isalnum() or c in "-_"
            )[:80] or "untitled"
            rnd = int(doc.get("round", 0))
            saved = dict(doc)
            saved["received_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            ANSWERS.mkdir(parents=True, exist_ok=True)
            path = ANSWERS / f"{topic}-round-{rnd}.json"
            tmp = path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(path)
            body = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:  # 失敗理由をブラウザ側に返す(ローカル専用のため詳細可)
            self.send_error(400, str(exc))

    def log_message(self, *args):
        pass  # アクセスログ不要(常駐でログ肥大させない)


if __name__ == "__main__":
    ROOT.mkdir(parents=True, exist_ok=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
