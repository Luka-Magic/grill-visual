#!/usr/bin/env bash
# grill-visual のお試し用サーバー。見た目を直す間だけ使う(直し終わったら止めて消してよい)。
# 普段使い(serve.sh、~/.agent/diagrams、8787)とは別の場所・別のポートで動かし、
# ui-comments(画面の要素を指してコメントする道具)を入れて配信する。
#   配信ルート: ~/.agent/diagrams-trial(お試し用の質問票だけを置く)
#   ポート:     127.0.0.1:8791(tailnet では tailscale serve で 8382 に中継)
#   コメント:   ~/ai_agent/grill-visual/.ui-comments(git に入れない)
# 使い方: trial.sh で起動(冪等)、trial.sh --restart で起動し直す、trial.sh --stop で止める。
set -u
PORT="${GRILL_TRIAL_PORT:-8791}"
DIR="$HOME/.agent/diagrams-trial"
HERE="$(dirname "$(readlink -f "$0")")"
MARKER=".grill-visual-marker"
UIC_PORT="${GRILL_UI_COMMENTS_PORT:-4320}"
UIC_SRC="$HOME/.claude/skills/ui-comments/src/server.mjs"
UIC_DIR="$HERE/.ui-comments"
mkdir -p "$DIR/grill-data" "$DIR/answers"
touch "$DIR/$MARKER"
# 画像などの共有アセットは普段使いのものを見る
[ -e "$DIR/assets" ] || ln -s "$HOME/.agent/diagrams/assets" "$DIR/assets"

stop_server() {
  local pid
  pid="$(ss -ltnp "sport = :$PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)"
  [ -n "$pid" ] && kill "$pid" && echo "stopped: お試し用サーバー(pid $pid)"
  for _ in 1 2 3 4 5; do
    timeout 1 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null || break
    sleep 0.5
  done
}

case "${1:-}" in
  --stop) stop_server; exit 0 ;;
  --restart) stop_server ;;
esac

# ui-comments の専用サーバー(道具があるときだけ、冪等)
if [ -f "$UIC_SRC" ] && command -v node >/dev/null \
   && ! timeout 2 curl -fsS -o /dev/null "http://127.0.0.1:$UIC_PORT/overlay.js" 2>/dev/null; then
  # 道具は「直接実行されたか」を実ファイルのパスで判定するので、リンクを解決してから渡す
  setsid nohup node "$(readlink -f "$UIC_SRC")" --dir "$UIC_DIR" --port "$UIC_PORT" >"$DIR/.ui-comments.log" 2>&1 < /dev/null &
  sleep 0.5
  echo "started: ui-comments http://127.0.0.1:$UIC_PORT/"
fi

if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null; then
  echo "already running: お試し用 http://localhost:$PORT/"
  exit 0
fi
GRILL_ROOT="$DIR" GRILL_PORT="$PORT" GRILL_UI_COMMENTS=1 setsid nohup python3 "$HERE/server.py" \
  >"$DIR/.server.log" 2>&1 < /dev/null &
sleep 1
if timeout 3 curl -fsS -o /dev/null "http://127.0.0.1:$PORT/$MARKER" 2>/dev/null; then
  echo "started: お試し用 http://localhost:$PORT/"
else
  echo "ERROR: failed to start. See $DIR/.server.log" >&2
  exit 1
fi
