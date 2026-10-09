#!/usr/bin/env bash
# grill-visual: 質問票と統合ページを http://localhost:8787/ で配信する常駐サーバーを起動する(冪等)。
# ループバック限定で外部には公開しない。
# 環境変数: GRILL_ROOT(配信するフォルダ。既定 ~/.claude/grill-visual)、GRILL_PORT(既定 8787)
set -u
PORT="${GRILL_PORT:-8787}"
DIR="${GRILL_ROOT:-$HOME/.claude/grill-visual}"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER=".grill-visual-marker"
mkdir -p "$DIR"
touch "$DIR/$MARKER"

# 既に自分のサーバーが動いているか(マーカーファイルの配信可否で判定)
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null; then
  echo "already running: 統合ページ http://localhost:$PORT/"
  exit 0
fi

# ポートは開いているがマーカーが取れない = 他アプリが使用中
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then
  echo "ERROR: port $PORT is used by another app. Set GRILL_PORT to another port." >&2
  exit 1
fi

GRILL_ROOT="$DIR" GRILL_PORT="$PORT" setsid nohup python3 "$SKILL_DIR/server.py" \
  >"$DIR/.server.log" 2>&1 < /dev/null &
sleep 1
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null; then
  echo "started: 統合ページ http://localhost:$PORT/"
else
  echo "ERROR: failed to start. See $DIR/.server.log" >&2
  exit 1
fi
