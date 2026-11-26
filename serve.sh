#!/usr/bin/env bash
# grill-visual: ~/.agent/diagrams を http://localhost:8787/ で配信する(冪等)。
# 質問票 HTML と統合ページ(http://localhost:8787/)を開くための常駐サーバー。
# ループバック限定で外部には公開しない。ポートは GRILL_PORT で変えられる(既定 8787)。
# server.py を直したら `serve.sh --restart` で起動し直す(質問票 HTML・dashboard.html は再起動不要)。
set -u
PORT="${GRILL_PORT:-8787}"
DIR="$HOME/.agent/diagrams"
MARKER=".grill-visual-marker"
mkdir -p "$DIR"
touch "$DIR/$MARKER"

# --restart: server.py を直したあとに、動いているサーバーを止めて起動し直す
if [ "${1:-}" = "--restart" ]; then
  pkill -f "^[^ ]*python3 [^ ]*/grill-visual/server\.py$" 2>/dev/null && echo "stopped: 古いサーバー"
  for _ in 1 2 3 4 5; do
    timeout 1 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null || break
    sleep 0.5
  done
fi

# 既に自分のサーバーが動いているか(マーカーファイルの配信可否で判定)
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null; then
  echo "already running: 統合ページ http://localhost:$PORT/"
  exit 0
fi

# ポートは開いているがマーカーが取れない = 他アプリが使用中
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/" 2>/dev/null; then
  echo "ERROR: port $PORT is used by another app. Edit PORT in $0" >&2
  exit 1
fi

GRILL_PORT="$PORT" setsid nohup python3 "$HOME/.claude/skills/grill-visual/server.py" \
  >"$DIR/.server.log" 2>&1 < /dev/null &
sleep 1
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null; then
  echo "started: 統合ページ http://localhost:$PORT/"
else
  echo "ERROR: failed to start. See $DIR/.server.log" >&2
  exit 1
fi
