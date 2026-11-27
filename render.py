#!/usr/bin/env python3
"""grill-visual driver: 質問データ JSON からタブ式の質問票 HTML を生成する。

使い方:
    python3 render.py ~/.agent/diagrams/grill-data/<topic>.json

出力:
    ~/.agent/diagrams/grill-<topic>.html(1 題材 1 ファイル。URL 固定)

印字: 出力パスと、統合ページの URL(<root>#<topic>。root は環境変数 PARALLEL_GRILL_URL、
      無ければ http://localhost:8787/)。

スキーマ(文字列は HTML として挿入される。<code>/<strong> 可。外部入力は入れない):
{
  "topic": "slug", "title": "見出し", "intro": "リード文",
  "kind": "plan"|"test-review"|"ui-check"?, "project": str?, "issue": int?,   # 統合ページの絞り込み用(省略時は topic/title から推定)
  "tree": [{"label": str, "status": "done"|"open", "note": str?, "children": [...]?}],
  "rounds": [{
     "round": 1, "label": "任意のタブ名"?, "status": "open"|"answered"|"info",
     "facts": [str, ...]?,
     "questions": [{
        "id": "Q1", "title": str, "body": str, "multi": bool?,
        "image": "assets/<topic>/x.png"?,
        "options": [{"key": "a", "label": str, "recommended": bool?, "image": str?}],
                                                   # 画像付きの選択肢は、広い窓(900px 以上)で横に並ぶ
        "why": str?,
        "answer": ["a"]?, "answer_note": str?,     # status=answered のとき(answer_note = AI 側の注記)
        "user_note": str?                          # 質問ごとのユーザー自由記述(送信 JSON の notes 由来)
     } | {                                         # ルール一覧型: 1 問の中に採用/不採用を決める行が並ぶ
        "id": "Q1", "type": "rules", "title": str, "body": str,
        "rules": [{
           "id": "R1", "text": str, "risk": "high"|"mid"|"low", "ears": str?, "note": str?,
           "cases": [{"id": str?, "behavior": str, "input": str?, "expected": str?, "kind": str?}]?,
           "user_note": str?                       # 行ごとのユーザーの 1 行コメント(notes["Q1/R1"] 由来)
        }],
        "answer": {"R1": "adopt"|"reject"}?, "answer_note": str?, "user_note": str?
     }]?,
     # 回答 JSON: 通常の問いは answers[Qn] = ["a"]、ルール一覧型は answers[Qn] = {"R1": "adopt", ...}
     # (既定は全行 adopt)。行の 1 行コメントは notes["Qn/Rm"]、問い全体のメモは notes["Qn"]。
     "declarations": [str, ...]?,
     "free_text_answer": str?
  }]
}
"""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from state import resolve_root  # noqa: E402  (同じディレクトリの state.py)

OUT_DIR = resolve_root()
DEFAULT_DASHBOARD_ROOT = "http://localhost:8787/"
# 画面の要素を指してコメントする道具(ui-comments)。server.py が専用サーバーへ中継する。
# 専用サーバーが動いていなければ読み込みに失敗するだけで、質問票は普通に動く
UI_COMMENTS_TAG = '<script src="/ui-comments/overlay.js" data-project="grill-sheet" defer></script>'
FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+JP:wght@400;500;600;700"
    "&family=IBM+Plex+Mono:wght@400;500;600&display=swap"
)

CSS = """
/* Hallmark · checked: 2026-11-27 · genre: modern-minimal (inferred: a working tool) · scope: app
 * floor: fixed 26a 30a 34 40 39a 48 7a 10a 50 54 63 67 38iii 27 · waive 39b: an option is a two-line card (label and its reason), not a control bar
 * built: the project · redesign: polish · v2.0.0 */
:root {
  --bg: #1c1a17; --panel: #24221e; --side: #201e1b; --line: #3a3730; --line2: #2e2b26;
  --text: #ebe6dc; --sub: #b0a99b; --mute: #9a9487;
  --accent: #e27a52; --on-accent: #1c1a17; --wait: #e27a52; --review: #93b6cc; --done: #95b283;
  --sel-bg: rgba(226, 122, 82, 0.13); --done-bg: rgba(149, 178, 131, 0.10);
  --hover: #2b2924; --input: #191714; --bar: #24221e; --err: #f08a7a;
  --field-line: #7a7468; --focus: #e27a52; --knob: #f2eee6; --scrim: rgba(12, 11, 9, 0.9);
  --done-off: #56664c;
  --s-wait: #95b283; --s-review: #93b6cc; --s-done: #e0736b;
  --sans: "IBM Plex Sans JP", "Hiragino Sans", "Noto Sans JP", "Yu Gothic UI", "Meiryo", sans-serif;
  --mono: "IBM Plex Mono", "Consolas", "Menlo", monospace;
  font-size: 14.5px;
}
* { box-sizing: border-box; margin: 0; }
html, body { overflow-x: clip; }
body { background: var(--bg); color: var(--text); line-height: 1.7; font-family: var(--sans); }
:where(button, a, input, textarea, select, summary, [tabindex]):focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
button:active:not([disabled]) { transform: translateY(1px); }
code { font-family: var(--mono); font-size: 0.9em; background: var(--input); border-radius: 4px; padding: 1px 4px; color: var(--text); }
.mono { font-family: var(--mono); }
a { color: var(--review); }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; background: currentColor; flex: none; }
.wrap { max-width: 780px; margin: 0 auto; padding: 36px 32px 40px; display: flex; flex-direction: column; gap: 24px; }
body.has-bar .wrap { padding-bottom: 152px; }
/* ヘッダ */
.kicker { display: flex; justify-content: space-between; gap: 12px; font-size: 12px; color: var(--mute); margin-bottom: 12px; }
.kicker .topic { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kicker .state { display: inline-flex; align-items: center; gap: 8px; color: var(--s-wait); white-space: nowrap; }
.kicker .state.done { color: var(--s-done); }
h1 { font-size: 26px; line-height: 1.4; font-weight: 600; color: var(--text); text-wrap: balance; overflow-wrap: break-word; min-width: 0; }
.lede { color: var(--sub); margin-top: 12px; }
/* パネル(設計ツリー・前提事実・宣言事項) */
.panel { background: var(--panel); border: 1px solid var(--line2); border-radius: 8px; padding: 16px 20px; }
.panel h2 { display: flex; justify-content: space-between; align-items: center; gap: 12px; font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 12px; }
.panel h2 small { font-weight: 400; color: var(--mute); font-size: 12px; margin-left: 8px; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; }
.panel-head h2 { margin-bottom: 0; }
.legend { display: flex; gap: 16px; font-size: 12px; font-weight: 400; color: var(--sub); white-space: nowrap; }
.legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend .mark { width: 8px; height: 8px; border-radius: 50%; }
.panel.dashed { background: none; border: 1px dashed var(--line); padding: 16px 20px; }
.panel.dashed h2 { margin-bottom: 8px; }
.items { list-style: none; padding: 0; font-size: 14px; color: var(--sub); display: flex; flex-direction: column; gap: 8px; }
.items li { display: flex; gap: 8px; overflow-wrap: anywhere; }
.items li::before { content: "・"; color: var(--mute); flex: none; }
table.cases { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 13px; }
table.cases th { text-align: left; color: var(--sub); font-weight: 500; padding: 4px 8px; border: 1px solid var(--line2); white-space: nowrap; }
table.cases td { padding: 4px 8px; border: 1px solid var(--line2); vertical-align: top; overflow-wrap: anywhere; color: var(--sub); }
table.cases td:first-child { color: var(--text); }
.q-card table.cases { display: block; overflow-x: auto; }
/* 設計ツリー */
.tree { list-style: none; padding: 0; font-size: 14px; display: flex; flex-direction: column; gap: 8px; }
.tree ul { list-style: none; padding-left: 20px; margin: 8px 0 0 4px; border-left: 1px solid var(--line); display: flex; flex-direction: column; gap: 8px; }
.tree .node { display: flex; align-items: flex-start; gap: 12px; }
.tree .node .text { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.tree .note { margin-left: 8px; }
.tree .mark { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--wait); flex: none; margin-top: 8px; }
.tree li.done > .node .mark { background: var(--done); border-color: var(--done); }
.tree li.done > .node .label { color: var(--sub); }
.tree .note { color: var(--mute); font-size: 12.5px; }
/* タブ */
.tabs { display: flex; gap: 20px; border-bottom: 1px solid var(--line); flex-wrap: wrap; }
.tab-btn {
  display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500;
  background: none; border: 0; border-bottom: 2px solid transparent; margin-bottom: -1px;
  color: var(--mute); padding: 12px 2px; cursor: pointer;
}
.tab-btn.active { color: var(--text); border-bottom-color: var(--accent); }
.tab-btn:hover { color: var(--text); }
.tab-btn .mark { font-size: 11px; }
.tab-btn .mark.answered { color: var(--s-done); }
.tab-btn .mark.open { color: var(--s-wait); }
.tab-pane { display: none; }
.tab-pane.active { display: flex; flex-direction: column; gap: 24px; }
/* 問いカード */
.q-card { background: var(--panel); border: 1px solid var(--line2); border-radius: 8px; padding: 24px 24px 20px; display: flex; flex-direction: column; gap: 16px; }
.q-head { display: flex; align-items: flex-start; gap: 12px; }
.q-tools { display: flex; align-items: center; gap: 8px; margin-left: auto; font-size: 12px; flex-wrap: wrap; justify-content: flex-end; padding-top: 4px; }
.q-num { margin-right: 8px; font-variant-numeric: tabular-nums; }
.multi-note { color: var(--sub); border: 1px solid var(--line); border-radius: 4px; padding: 0 8px; white-space: nowrap; }
.q-answered { color: var(--done); white-space: nowrap; }
.q-title { flex: 1; min-width: 0; font-size: 17.5px; line-height: 1.5; font-weight: 600; color: var(--text); text-wrap: balance; overflow-wrap: break-word; }
.q-body { font-size: 14px; color: var(--sub); margin-top: -8px; overflow-wrap: anywhere; }
.q-image { margin: 0; }
.q-image img { max-width: 100%; border: 1px solid var(--line); border-radius: 6px; cursor: zoom-in; display: block; }
.q-image figcaption { font-size: 12px; color: var(--mute); margin-top: 4px; }
.opt-hint { font-size: 12px; color: var(--mute); margin-bottom: -8px; }
.opts { display: flex; flex-direction: column; gap: 8px; }
.opt {
  display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; gap: 12px; align-items: start; text-align: left;
  border: 1.5px solid var(--line2); background: var(--panel); border-radius: 8px; padding: 12px 16px 12px 12px;
  cursor: pointer; font: inherit; font-size: 14px; color: var(--text); width: 100%; min-width: 0;
}
.opt:hover { border-color: var(--mute); background: var(--hover); }
.opt .key {
  width: 26px; height: 26px; border-radius: 50%; border: 1.5px solid var(--line); display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600; color: var(--sub); flex: none;
}
.q-card[data-multi="true"] .opt .key { border-radius: 4px; }
.opt .body { display: flex; flex-direction: column; gap: 4px; padding-top: 2px; min-width: 0; overflow-wrap: break-word; }
.opt .why-inline { font-size: 12.5px; line-height: 1.6; color: var(--sub); font-weight: 400; }
.rec-badge { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; font-weight: 600; color: var(--done); white-space: nowrap; padding-top: 4px; }
.opt.selected { border-color: var(--accent); background: var(--sel-bg); }
.opt.selected .key { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.opt.selected .body { font-weight: 600; }
.opt[disabled] { cursor: not-allowed; }
.opt[disabled]:hover { border-color: var(--line2); background: var(--panel); }
.opt[disabled]:not(.selected) { background: transparent; border-color: var(--line2); color: var(--mute); }
.opt[disabled]:not(.selected) .key { border-color: var(--line2); color: var(--mute); }
.opt.selected[disabled] { border-color: var(--done); background: var(--done-bg); }
.opt.selected[disabled]:hover { border-color: var(--done); background: var(--done-bg); }
.opt.selected[disabled] .key { background: var(--done); border-color: var(--done); color: var(--on-accent); }
.opt > img { grid-column: 1 / -1; max-width: 320px; width: 100%; border-radius: 6px; border: 1px solid var(--line); display: block; cursor: zoom-in; }
@media (min-width: 900px) {
  /* 画像付きの選択肢は横に並べて見比べる(最大 3 列)。画像なしの選択肢は 1 行使う */
  .opts.has-images { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
  .opts.has-images .opt:not(.has-img) { grid-column: 1 / -1; }
  .opts.has-images .opt.has-img > img { max-width: 100%; }
}
/* ルール一覧型 */
.rules { border-top: 1px solid var(--line2); }
.rule { border-bottom: 1px solid var(--line2); padding: 12px 0; }
.rule-head { display: flex; gap: 12px; align-items: flex-start; }
.risk {
  font-size: 11px; border-radius: 999px; padding: 0 8px;
  white-space: nowrap; margin-top: 4px; border: 1px solid currentColor; flex-shrink: 0;
}
.risk.high { color: var(--err); } .risk.mid { color: var(--wait); } .risk.low { color: var(--done); }
.rule-main { flex: 1; min-width: 0; }
.rule-text { color: var(--text); font-size: 14.5px; overflow-wrap: break-word; }
.rule.rejected .rule-text { color: var(--mute); text-decoration: line-through; }
.rule-ears { font-size: 13px; color: var(--sub); background: var(--input); border-radius: 4px; padding: 2px 8px; margin: 4px 0; }
.rule-cases-toggle { background: none; border: 0; color: var(--mute); font-size: 12px; cursor: pointer; padding: 0; }
.rule-cases-toggle:hover { color: var(--text); }
.rule-cases { margin-top: 8px; }
.rule-cases .cases { display: block; overflow-x: auto; }
.rule-ai-note { font-size: 12.5px; color: var(--sub); margin: 2px 0 8px; }
.rule-ctl { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; flex-shrink: 0; }
.switch { position: relative; width: 40px; height: 22px; display: inline-block; }
.switch input { opacity: 0; width: 0; height: 0; position: absolute; }
.switch span { position: absolute; inset: 0; border-radius: 999px; background: var(--line); cursor: pointer; }
.switch span::after { content: ""; position: absolute; top: 3px; left: 3px; width: 16px; height: 16px; border-radius: 50%; background: var(--knob); }
.switch input:checked + span { background: var(--done); }
.switch input:checked + span::after { left: 21px; }
.switch input:disabled + span { cursor: not-allowed; background: var(--line2); }
.switch input:checked:disabled + span { background: var(--done-off); }
.rule-cmt { display: inline-flex; align-items: center; justify-content: center; min-width: 32px; min-height: 32px; background: none; border: 1px solid var(--line); border-radius: 6px; color: var(--mute); font: inherit; font-size: 13px; padding: 0 8px; cursor: pointer; }
.rule-cmt.on { color: var(--accent); border-color: var(--accent); }
.rule-note {
  display: block; width: 100%; margin-top: 8px; font: inherit; font-size: 13.5px;
  border: 1px solid var(--field-line); border-radius: 6px; padding: 8px 12px; background: var(--input); color: var(--text);
}
.rule-note:focus { border-color: var(--accent); }
.rule-note::placeholder { color: var(--mute); }
.rule-note[disabled] { border-color: var(--line2); background: var(--panel); cursor: not-allowed; -webkit-text-fill-color: var(--sub); }
.rules-foot { font-size: 12.5px; font-variant-numeric: tabular-nums; color: var(--mute); }
/* 注記・推奨理由・メモ */
.why, .answer-note, .user-note { display: flex; gap: 12px; font-size: 13.5px; color: var(--sub); overflow-wrap: anywhere; }
.why strong, .answer-note strong, .user-note strong { flex: none; font-size: 12px; font-weight: 600; padding-top: 1px; }
.why strong { color: var(--done); }
.answer-note strong { color: var(--review); }
.user-note strong { color: var(--text); }
.q-note {
  display: block; width: 100%; font: inherit; font-size: 13.5px; line-height: 1.5;
  border: 1px solid var(--field-line); border-radius: 6px; padding: 8px 12px;
  background: var(--input); color: var(--text); resize: none; field-sizing: content; min-height: 42px;
}
.q-note:focus { border-color: var(--accent); }
.q-note::placeholder { color: var(--mute); }
.free-answer { border: 1px dashed var(--line); border-radius: 8px; padding: 12px 16px; font-size: 13.5px; color: var(--sub); white-space: pre-wrap; }
.free-answer .label { color: var(--mute); font-size: 12px; display: block; margin-bottom: 4px; }
/* 送信バー */
.answer-bar { position: fixed; left: 0; right: 0; bottom: 0; background: var(--bar); border-top: 1px solid var(--line); padding: 12px 32px; }
.answer-inner { max-width: 780px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; }
.answer-row { display: flex; align-items: center; gap: 8px 12px; flex-wrap: wrap; }
.progress { display: flex; flex-direction: column; gap: 4px; width: 88px; flex: none; }
.progress span { font-size: 12px; font-variant-numeric: tabular-nums; color: var(--sub); white-space: nowrap; }
.progress i { display: block; height: 4px; border-radius: 2px; background: var(--line2); overflow: hidden; }
.progress i b { display: block; height: 100%; width: 100%; background: var(--accent); transform: scaleX(0); transform-origin: left; }
#answer-string {
  flex: 1 1 200px; min-width: 0; font-family: var(--mono); font-size: 12.5px; padding: 8px 12px; border-radius: 6px;
  background: var(--input); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; color: var(--text);
}
#answer-string.empty { color: var(--mute); }
.answer-btns { display: flex; align-items: center; gap: 12px; margin-left: auto; flex-wrap: wrap; }
.btn { font: inherit; font-size: 13px; border: 0; background: none; border-radius: 6px; padding: 8px 12px; color: var(--sub); cursor: pointer; white-space: nowrap; }
.btn:hover { color: var(--text); background: var(--hover); }
#all-rec { color: var(--done); }
#copy-btn { border: 1px solid var(--line); color: var(--text); padding: 8px 16px; }
.btn.primary { background: var(--accent); color: var(--on-accent); font-weight: 600; padding: 8px 24px; font-size: 13.5px; }
.btn.primary:hover { background: var(--accent); color: var(--on-accent); filter: brightness(1.08); }
.btn[disabled] { background: var(--line2); color: var(--mute); font-weight: 500; cursor: not-allowed; }
#free-text {
  display: block; width: 100%; font: inherit; font-size: 13.5px; border: 1px solid var(--field-line); border-radius: 6px;
  padding: 8px 12px; background: var(--input); color: var(--text); resize: none; field-sizing: content; min-height: 38px; max-height: 160px;
}
#free-text[hidden] { display: none; }
#free-text:focus { border-color: var(--accent); }
#free-text::placeholder { color: var(--mute); }
#submit-status { font-size: 12.5px; color: var(--done); text-align: right; }
#submit-status:empty { display: none; }
/* 各問のチャット */
.ask-btn {
  display: inline-flex; align-items: center; gap: 8px; font: inherit; font-size: 12px;
  min-height: 32px; background: none; border: 1px solid var(--line); border-radius: 999px; padding: 0 12px; color: var(--sub); cursor: pointer; white-space: nowrap;
}
.ask-btn:hover { color: var(--text); background: var(--hover); }
.ask-btn.on { color: var(--accent); border-color: var(--accent); }
.ask-btn.unread::after { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
.ask-count { font-size: 11px; font-variant-numeric: tabular-nums; color: var(--mute); }
.ask-count:empty { display: none; }
.chat { border-top: 1px dashed var(--line); padding-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.chat[hidden] { display: none; }
.chat-log { display: flex; flex-direction: column; gap: 8px; max-height: 320px; overflow-y: auto; }
.chat-log:empty { display: none; }
.msg { max-width: 88%; padding: 8px 12px; border-radius: 8px; font-size: 13.5px; line-height: 1.6; white-space: pre-wrap; overflow-wrap: anywhere; }
.msg.user { align-self: flex-end; background: var(--sel-bg); color: var(--text); border-bottom-right-radius: 2px; }
.msg.ai { align-self: flex-start; background: var(--input); color: var(--text); border: 1px solid var(--line2); border-bottom-left-radius: 2px; }
.msg .who { display: block; font-size: 11px; color: var(--mute); margin-bottom: 2px; }
.msg.ai .who { color: var(--review); }
.chat-wait { font-size: 12px; color: var(--mute); }
.chat-wait[hidden] { display: none; }
.chat-form { display: flex; gap: 8px; align-items: flex-end; }
.chat-input {
  flex: 1; min-width: 0; font: inherit; font-size: 13.5px; line-height: 1.5; border: 1px solid var(--field-line); border-radius: 6px;
  padding: 8px 12px; background: var(--input); color: var(--text); resize: none; field-sizing: content; min-height: 38px; max-height: 160px;
}
.chat-input:focus { border-color: var(--accent); }
.chat-input::placeholder { color: var(--mute); }
.chat-send { border: 1px solid var(--line); color: var(--text); }
.chat-hint { font-size: 11.5px; color: var(--mute); }
.chat-err { font-size: 12px; color: var(--err); }
.chat-err:empty { display: none; }
/* 広い画面: 問いを 2〜3 列に並べる。画像(モック)付き・ルール一覧型・パネルは 1 行を使い切る */
@media (min-width: 960px) {
  .wrap { max-width: 1480px; }
  header .lede, header h1 { max-width: 900px; }
  .tab-pane.active { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); align-items: start; }
  .tab-pane.active > .panel, .tab-pane.active > .free-answer, .tab-pane.active > .q-card.wide { grid-column: 1 / -1; }
  .answer-inner { max-width: 1480px; }
}
#lightbox { display: none; position: fixed; inset: 0; background: var(--scrim); z-index: 50; cursor: zoom-out; padding: 32px; }
#lightbox.show { display: flex; align-items: center; justify-content: center; }
#lightbox img { max-width: 100%; max-height: 100%; border-radius: 6px; }
@media (max-width: 760px) {
  .wrap { padding: 24px 16px 40px; }
  body.has-bar .wrap { padding-bottom: 212px; }
  .answer-bar { padding: 12px 16px; }
  .answer-btns { margin-left: 0; }
}
@media (prefers-reduced-motion: no-preference) {
  .opt, .btn, .tab-btn { transition: border-color 0.12s, background-color 0.12s, color 0.12s; }
  .progress i b { transition: transform 0.15s; }
}
"""

JS = """
(function () {
  var CONFIG = __CONFIG__;
  var answers = {};
  function isRules(q) { return q.type === "rules"; }
  function defaultRules(q) {
    var a = {};
    (q.rules || []).forEach(function (r) { a[r] = "adopt"; });
    return a;
  }
  (CONFIG.openQuestions || []).forEach(function (q) { answers[q.id] = isRules(q) ? defaultRules(q) : []; });

  // ---- ルール一覧型: 例の開閉・コメント欄は回答済みのタブでも動かす(読むため) ----
  document.querySelectorAll(".rule").forEach(function (row) {
    var cases = row.querySelector(".rule-cases");
    var toggle = row.querySelector(".rule-cases-toggle");
    if (cases && toggle) {
      cases.hidden = row.getAttribute("data-cases-open") !== "true";
      toggle.textContent = (cases.hidden ? "▸" : "▾") + toggle.textContent.slice(1);
      toggle.addEventListener("click", function () {
        cases.hidden = !cases.hidden;
        toggle.textContent = (cases.hidden ? "▸" : "▾") + toggle.textContent.slice(1);
      });
    }
    var cmt = row.querySelector(".rule-cmt");
    var noteWrap = row.querySelector(".rule-note-wrap");
    if (cmt && noteWrap) {
      cmt.addEventListener("click", function () {
        noteWrap.hidden = !noteWrap.hidden;
        var input = noteWrap.querySelector("input");
        if (!noteWrap.hidden && input && !input.disabled) input.focus();
        cmt.classList.toggle("on", !noteWrap.hidden || !!(input && input.value.trim()));
      });
    }
  });
  function updateRulesFoot(card) {
    var foot = card.querySelector(".rules-foot");
    if (!foot) return;
    var adopt = 0, reject = 0, notes = 0;
    card.querySelectorAll(".rule").forEach(function (row) {
      var sw = row.querySelector(".rule-adopt");
      if (sw && sw.checked) adopt++; else reject++;
      var input = row.querySelector(".rule-note");
      if (input && input.value.trim()) notes++;
    });
    foot.textContent = "採用 " + adopt + " / 不採用 " + reject + " / コメント " + notes;
  }
  function syncRulesCard(card, q) {
    card.querySelectorAll(".rule").forEach(function (row) {
      var id = row.getAttribute("data-rule");
      var sw = row.querySelector(".rule-adopt");
      var adopted = answers[q.id][id] !== "reject";
      if (sw) sw.checked = adopted;
      row.classList.toggle("rejected", !adopted);
    });
    updateRulesFoot(card);
  }
  var bar = document.getElementById("answer-string");
  var status = document.getElementById("submit-status");

  document.querySelectorAll(".tab-btn").forEach(function (btn) {
    btn.addEventListener("click", function () {
      document.querySelectorAll(".tab-btn").forEach(function (b) { b.classList.remove("active"); });
      document.querySelectorAll(".tab-pane").forEach(function (p) { p.classList.remove("active"); });
      btn.classList.add("active");
      document.getElementById(btn.getAttribute("data-target")).classList.add("active");
    });
  });

  var lightbox = document.getElementById("lightbox");
  var lightboxImg = lightbox ? lightbox.querySelector("img") : null;
  document.querySelectorAll(".q-image img, .opt img").forEach(function (img) {
    img.addEventListener("click", function (e) {
      e.stopPropagation();
      lightboxImg.src = img.src;
      lightbox.classList.add("show");
    });
  });
  if (lightbox) lightbox.addEventListener("click", function () { lightbox.classList.remove("show"); });

  // ---- 各問のチャット(回答の送信とは独立) ----
  (function setupChat() {
    var boxes = {};
    document.querySelectorAll(".chat").forEach(function (box) { boxes[box.getAttribute("data-q")] = box; });
    if (!Object.keys(boxes).length || !CONFIG.topic) return;
    var counts = {};      // q → 表示済みの発言数
    var lastText = "";
    function el(tag, cls, text) { var n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; }
    function render(messages) {
      var byQ = {};
      messages.forEach(function (m) { (byQ[m.q] = byQ[m.q] || []).push(m); });
      Object.keys(boxes).forEach(function (q) {
        var box = boxes[q], list = byQ[q] || [];
        var btn = document.querySelector('.ask-btn[data-q="' + q + '"]');
        if (list.length === counts[q]) return;
        var log = box.querySelector(".chat-log");
        var frag = document.createDocumentFragment();
        list.forEach(function (m) {
          var div = el("div", "msg " + (m.from === "ai" ? "ai" : "user"));
          div.appendChild(el("span", "who", m.from === "ai" ? "AI" : "あなた"));
          div.appendChild(document.createTextNode(m.text));  // 本文は常にテキストとして描く
          frag.appendChild(div);
        });
        log.replaceChildren(frag);
        log.scrollTop = log.scrollHeight;
        var last = list[list.length - 1];
        box.querySelector(".chat-wait").hidden = !last || last.from !== "user";
        if (btn) {
          btn.querySelector(".ask-count").textContent = list.length ? String(list.length) : "";
          var gotReply = counts[q] !== undefined && last && last.from === "ai";
          if (gotReply && box.hidden) btn.classList.add("unread");
        }
        counts[q] = list.length;
      });
    }
    function poll() {
      return fetch("/api/chat?topic=" + encodeURIComponent(CONFIG.topic), { cache: "no-store" })
        .then(function (res) { if (!res.ok) throw new Error("HTTP " + res.status); return res.text(); })
        .then(function (text) { if (text !== lastText) { lastText = text; render(JSON.parse(text).messages || []); } })
        .catch(function () { /* サーバーが無い(ファイルを直接開いた)ときは黙って待つ */ });
    }
    function send(q) {
      var box = boxes[q], input = box.querySelector(".chat-input"), err = box.querySelector(".chat-err");
      var text = input.value.trim();
      if (!text) return;
      var btn = box.querySelector(".chat-send");
      btn.disabled = true; err.textContent = "";
      fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic: CONFIG.topic, q: q, text: text }) })
        .then(function (res) { if (!res.ok) throw new Error("HTTP " + res.status); input.value = ""; return poll(); })
        .catch(function (e) { err.textContent = "送れませんでした(" + e.message + ")。チャットに直接書いてもかまいません"; })
        .then(function () { btn.disabled = false; input.focus(); });
    }
    document.querySelectorAll(".ask-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var box = boxes[btn.getAttribute("data-q")];
        box.hidden = !box.hidden;
        btn.classList.toggle("on", !box.hidden);
        btn.classList.remove("unread");
        if (!box.hidden) box.querySelector(".chat-input").focus();
      });
    });
    Object.keys(boxes).forEach(function (q) {
      var box = boxes[q], input = box.querySelector(".chat-input");
      box.querySelector(".chat-send").addEventListener("click", function () { send(q); });
      input.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(q); }
      });
    });
    poll();
    setInterval(function () { if (document.visibilityState === "visible") poll(); }, 3000);
  })();

  if (!bar) return;  // 回答対象の open ラウンドが無いページ(サマリ等)

  // ---- 下書き(localStorage)。別ページへ行って戻っても選択・メモ・自由記述が残る ----
  var DRAFT_PREFIX = "grill-draft:" + CONFIG.topic + ":";
  var DRAFT_KEY = DRAFT_PREFIX + CONFIG.openRound;
  var freeInput = document.getElementById("free-text");
  var submitted = false;  // この下書きが送信済みか(送信後に開き直したとき、何を答えたか見える)

  function collectNotes() {
    var notes = {};
    document.querySelectorAll('.q-card[data-open="true"] .q-note').forEach(function (ta) {
      var v = ta.value.trim();
      if (v) notes[ta.getAttribute("data-q")] = v;
    });
    document.querySelectorAll('.q-card[data-open="true"] .rule-note').forEach(function (input) {
      var v = input.value.trim();
      if (v) notes[input.closest(".q-card").getAttribute("data-q") + "/" + input.getAttribute("data-rule")] = v;
    });
    return notes;
  }
  function saveDraft() {
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({
        answers: answers, notes: collectNotes(), free_text: freeInput.value, submitted: submitted
      }));
    } catch (e) { /* 保存できない環境(プライベートモード等)でも回答はできる */ }
  }
  function markDirty() { submitted = false; saveDraft(); }
  function clearOldDrafts() {  // 同じ題材の過去ラウンドの下書きは捨てる
    try {
      for (var i = localStorage.length - 1; i >= 0; i--) {
        var k = localStorage.key(i);
        if (k && k.indexOf(DRAFT_PREFIX) === 0 && k !== DRAFT_KEY) localStorage.removeItem(k);
      }
    } catch (e) { /* 読めなければ何もしない */ }
  }
  function restoreDraft() {
    var d = null;
    try { d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); } catch (e) { d = null; }
    if (!d || typeof d !== "object") return;
    (CONFIG.openQuestions || []).forEach(function (q) {
      var card = document.querySelector('.q-card[data-q="' + q.id + '"][data-open="true"]');
      if (!card) return;
      if (isRules(q)) {
        var saved = d.answers ? d.answers[q.id] : null;
        if (saved && typeof saved === "object" && !Array.isArray(saved)) {
          q.rules.forEach(function (r) {
            if (saved[r] === "adopt" || saved[r] === "reject") answers[q.id][r] = saved[r];
          });
        }
        card.querySelectorAll(".rule-note").forEach(function (input) {
          var k = q.id + "/" + input.getAttribute("data-rule");
          if (d.notes && typeof d.notes[k] === "string") {
            input.value = d.notes[k];
            input.closest(".rule-note-wrap").hidden = false;
            var cmt = input.closest(".rule").querySelector(".rule-cmt");
            if (cmt) cmt.classList.add("on");
          }
        });
        syncRulesCard(card, q);
        var qta = card.querySelector(".q-note");
        if (qta && d.notes && typeof d.notes[q.id] === "string") qta.value = d.notes[q.id];
        return;
      }
      var keys = (d.answers && Array.isArray(d.answers[q.id])) ? d.answers[q.id] : [];
      answers[q.id] = keys.filter(function (k) {  // 今の選択肢に存在するものだけ戻す
        return typeof k === "string" && card.querySelector('.opt[data-key="' + k + '"]');
      });
      card.querySelectorAll(".opt").forEach(function (o) {
        o.classList.toggle("selected", answers[q.id].indexOf(o.getAttribute("data-key")) >= 0);
      });
      var ta = card.querySelector(".q-note");
      if (ta && d.notes && typeof d.notes[q.id] === "string") ta.value = d.notes[q.id];
    });
    if (typeof d.free_text === "string") {
      freeInput.value = d.free_text;
      if (d.free_text.trim()) freeInput.hidden = false;
    }
    submitted = d.submitted === true;
    renderBar();
    if (submitted) {
      status.textContent = "送信済みの回答です(変えるなら選び直して再送信)";
      status.style.color = "var(--done)";
    }
  }

  function hasAnswer(q) { return isRules(q) || answers[q.id].length > 0; }
  function describe(q) {
    if (!isRules(q)) return q.id + ": (" + answers[q.id].join(",") + ")";
    var rejects = q.rules.filter(function (r) { return answers[q.id][r] === "reject"; });
    var adopt = q.rules.length - rejects.length;
    return q.id + ": (採用 " + adopt + (rejects.length ? " / 不採用 " + rejects.join(",") : "") + ")";
  }
  var progressText = document.getElementById("progress-text");
  var progressFill = document.getElementById("progress-fill");
  function renderBar() {
    var all = CONFIG.openQuestions || [];
    var parts = all.filter(hasAnswer).map(describe);
    if (parts.length === 0) {
      bar.textContent = "選択肢を選ぶと回答がここに組み立てられます";
      bar.classList.add("empty");
    } else {
      bar.textContent = parts.join(" / ");
      bar.classList.remove("empty");
    }
    if (progressText) progressText.textContent = parts.length + " / " + all.length + " 回答";
    if (progressFill) progressFill.style.transform = "scaleX(" + (all.length ? parts.length / all.length : 0) + ")";
  }
  var freeToggle = document.getElementById("free-toggle");
  if (freeToggle) freeToggle.addEventListener("click", function () {
    freeInput.hidden = !freeInput.hidden;
    if (!freeInput.hidden) freeInput.focus();
  });

  document.querySelectorAll('.q-card[data-open="true"][data-type="rules"]').forEach(function (card) {
    var q = (CONFIG.openQuestions || []).filter(function (x) { return x.id === card.getAttribute("data-q"); })[0];
    if (!q) return;
    card.querySelectorAll(".rule").forEach(function (row) {
      var id = row.getAttribute("data-rule");
      var sw = row.querySelector(".rule-adopt");
      if (sw) sw.addEventListener("change", function () {
        answers[q.id][id] = sw.checked ? "adopt" : "reject";
        row.classList.toggle("rejected", !sw.checked);
        updateRulesFoot(card);
        markDirty();
        renderBar();
      });
      var input = row.querySelector(".rule-note");
      if (input) input.addEventListener("input", function () {
        row.querySelector(".rule-cmt").classList.toggle("on", true);
        updateRulesFoot(card);
        markDirty();
      });
    });
    updateRulesFoot(card);
  });

  document.querySelectorAll('.q-card[data-open="true"]').forEach(function (card) {
    var q = card.getAttribute("data-q");
    var multi = card.getAttribute("data-multi") === "true";
    card.querySelectorAll(".opt").forEach(function (opt) {
      opt.addEventListener("click", function () {
        var key = opt.getAttribute("data-key");
        var idx = answers[q].indexOf(key);
        if (idx >= 0) {
          answers[q].splice(idx, 1);
          opt.classList.remove("selected");
        } else {
          if (!multi) {
            answers[q] = [];
            card.querySelectorAll(".opt").forEach(function (o) { o.classList.remove("selected"); });
          }
          answers[q].push(key);
          answers[q].sort();
          opt.classList.add("selected");
        }
        markDirty();
        renderBar();
      });
    });
  });

  var allRec = document.getElementById("all-rec");
  if (allRec) allRec.addEventListener("click", function () {
    (CONFIG.openQuestions || []).forEach(function (q) {
      var card = document.querySelector('.q-card[data-q="' + q.id + '"][data-open="true"]');
      if (isRules(q)) {  // ルール一覧型の推奨は「全行採用」
        answers[q.id] = defaultRules(q);
        syncRulesCard(card, q);
        return;
      }
      if (!q.recommended.length) return;
      answers[q.id] = q.recommended.slice();
      card.querySelectorAll(".opt").forEach(function (o) {
        o.classList.toggle("selected", q.recommended.indexOf(o.getAttribute("data-key")) >= 0);
      });
    });
    markDirty();
    renderBar();
  });

  document.getElementById("copy-btn").addEventListener("click", function () {
    var text = bar.classList.contains("empty") ? "" : bar.textContent;
    if (!text) return;
    var btn = this;
    function done(label) {
      btn.textContent = label;
      setTimeout(function () { btn.textContent = "コピー"; }, 1800);
    }
    function fallback() {
      var range = document.createRange();
      range.selectNodeContents(bar);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
      done("選択しました — Ctrl+C で");
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { done("コピーしました ✓"); }, fallback);
    } else { fallback(); }
  });

  var submitBtn = document.getElementById("submit-btn");
  submitBtn.addEventListener("click", function () {
    var freeText = freeInput.value.trim();
    var notes = collectNotes();
    var hasAnswers = (CONFIG.openQuestions || []).some(hasAnswer);
    var hasNotes = Object.keys(notes).length > 0;
    if (!hasAnswers && !freeText && !hasNotes) {
      status.textContent = "選択・メモ・自由記述のどれかを入れてください";
      status.style.color = "var(--err)";
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = "送信中…";
    status.textContent = "送信中…";
    status.style.color = "var(--sub)";
    fetch("/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: CONFIG.topic, round: CONFIG.openRound,
        answers: answers, notes: notes, free_text: freeText
      })
    }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      submitBtn.textContent = "送信済み";
      status.textContent = "送信しました ✓ AI が自動で処理を再開します";
      status.style.color = "var(--done)";
      submitted = true;
      saveDraft();
      if (window.parent !== window) {  // 統合ページの iframe 内なら、親に知らせて一覧を即時更新させる
        window.parent.postMessage({ type: "grill-submitted", topic: CONFIG.topic, round: CONFIG.openRound }, location.origin);
      }
    }).catch(function (e) {
      submitBtn.disabled = false;
      submitBtn.textContent = "送信";
      status.textContent = "送信失敗(" + e.message + ")— コピーでチャットに貼ってください";
      status.style.color = "var(--err)";
    });
  });

  document.querySelectorAll('.q-card[data-open="true"] .q-note').forEach(function (ta) {
    ta.addEventListener("input", markDirty);
  });
  freeInput.addEventListener("input", markDirty);
  clearOldDrafts();
  restoreDraft();
})();
"""


def render_tree(nodes: list) -> str:
    items = []
    for n in nodes:
        status = "done" if n.get("status") == "done" else "open"
        note = f'<span class="note">{n["note"]}</span>' if n.get("note") else ""
        children = f'<ul>{render_tree(n["children"])}</ul>' if n.get("children") else ""
        items.append(
            f'<li class="{status}"><span class="node"><i class="mark"></i>'
            f'<span class="text"><span class="label">{n["label"]}</span>{note}</span></span>{children}</li>'
        )
    return "".join(items)


def tree_counts(nodes: list) -> tuple[int, int]:
    """設計ツリーの(決定, 未決)の件数。子も数える。"""
    done = open_ = 0
    for n in nodes:
        if n.get("status") == "done":
            done += 1
        else:
            open_ += 1
        d, o = tree_counts(n.get("children") or [])
        done, open_ = done + d, open_ + o
    return done, open_


def render_tree_panel(nodes: list) -> str:
    done, open_ = tree_counts(nodes)
    legend = (
        '<span class="legend">'
        f'<span><i class="mark" style="background:var(--done)"></i>決定 {done}</span>'
        f'<span><i class="mark" style="border:1.5px solid var(--wait)"></i>未決 {open_}</span></span>'
    )
    return (
        f'<section class="panel"><div class="panel-head"><h2>設計ツリー</h2>{legend}</div>'
        f'<ul class="tree">{render_tree(nodes)}</ul></section>'
    )


def render_image(path: str, caption: str | None = None) -> str:
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="q-image"><img src="{path}" alt="">{cap}</figure>'


def render_user_note(q: dict, is_open: bool) -> str:
    """質問ごとのユーザー自由記述欄。open は入力可、過去ラウンドは記入済みだけ読み取り専用。"""
    if is_open:
        return (
            f'<textarea class="q-note" data-q="{q["id"]}" rows="1" '
            f'placeholder="補足・メモ(任意)"></textarea>'
        )
    if not q.get("user_note"):
        return ""
    # ユーザーが打った文字列なのでエスケープする(他の項目と違い HTML として扱わない)
    return f'<div class="user-note"><strong>あなたのメモ</strong><span>{html.escape(q["user_note"])}</span></div>'


def render_q_head(q: dict, is_open: bool, multi: bool = False) -> str:
    """問いカードの上段(Q 番号・複数選択可・回答済み)と題。"""
    multi_note = '<span class="multi-note">複数選択可</span>' if multi else ""
    answered = '<span class="q-answered">✓ 回答済み</span>' if not is_open and q.get("answer") else ""
    ask = (
        f'<button type="button" class="ask-btn" data-q="{q["id"]}" title="この問いについて AI に聞く">'
        '聞く<span class="ask-count"></span></button>'
    ) if is_open else ""
    tools = f'<div class="q-tools">{multi_note}{answered}{ask}</div>' if (multi_note or answered or ask) else ""
    return (
        f'<div class="q-head"><h3 class="q-title"><span class="q-num">{q["id"]}</span>{q["title"]}</h3>{tools}</div>'
    )


def render_chat(q: dict, is_open: bool) -> str:
    """各問の会話欄(open のラウンドだけ)。中身はブラウザが /api/chat から描く。"""
    if not is_open:
        return ""
    return (
        f'<div class="chat" data-q="{q["id"]}" hidden><div class="chat-log"></div>'
        '<div class="chat-wait" hidden>AI の返事を待っています…</div>'
        '<div class="chat-form"><textarea class="chat-input" rows="1" '
        'placeholder="この問いについて AI に聞く(Enter で送信、Shift+Enter で改行)"></textarea>'
        '<button type="button" class="btn chat-send">送る</button></div>'
        '<div class="chat-err"></div>'
        '<div class="chat-hint">回答の送信とは別です。AI が質問票を見ていれば、ここに返事が出ます。</div></div>'
    )


def render_why(q: dict) -> str:
    return f'<div class="why"><strong>推奨理由</strong><span>{q["why"]}</span></div>' if q.get("why") else ""


def render_answer_note(q: dict) -> str:
    return f'<div class="answer-note"><strong>AI 注記</strong><span>{q["answer_note"]}</span></div>' if q.get("answer_note") else ""


RISK_LABEL = {"high": "高", "mid": "中", "low": "低"}


def render_cases_table(cases: list[dict]) -> str:
    """例(テストケース)の横長表。1 例 = 1 行。"""
    if not cases:
        return ""
    rows = "".join(
        f'<tr><td>{c["behavior"]}</td><td>{c.get("input", "")}</td>'
        f'<td>{c.get("expected", "")}</td><td>{c.get("kind", "")}</td></tr>'
        for c in cases
    )
    return (
        '<table class="cases"><tr><th>振る舞い</th><th>入力</th><th>期待結果</th><th>分類</th></tr>'
        f"{rows}</table>"
    )


def render_rule(rule: dict, decision: str | None, is_open: bool) -> str:
    """ルール一覧の 1 行。採用トグルは既定オン。高リスクは例を開いた状態で出す。"""
    risk = rule.get("risk", "mid")
    adopted = decision != "reject"
    cases = rule.get("cases") or []
    cases_open = risk == "high" or decision == "reject"
    checked = " checked" if adopted else ""
    disabled = "" if is_open else " disabled"
    ears = f'<div class="rule-ears">{rule["ears"]}</div>' if rule.get("ears") else ""
    toggle = (
        f'<button type="button" class="rule-cases-toggle">▸ 例 {len(cases)} 件</button>' if cases else ""
    )
    ai_note = f'<div class="rule-ai-note">{rule["note"]}</div>' if rule.get("note") else ""
    cases_html = f'<div class="rule-cases" hidden>{ai_note}{render_cases_table(cases)}</div>' if cases or ai_note else ""
    if is_open:
        note_input = f'<input class="rule-note" data-rule="{rule["id"]}" placeholder="1 行コメント(任意)">'
        note_hidden, cmt_on = " hidden", ""
    elif rule.get("user_note"):
        # ユーザーが打った文字列なのでエスケープする
        note_input = (
            f'<input class="rule-note" data-rule="{rule["id"]}" disabled '
            f'value="{html.escape(rule["user_note"], quote=True)}">'
        )
        note_hidden, cmt_on = "", " on"
    else:
        note_input, note_hidden, cmt_on = "", " hidden", ""
    rejected = "" if adopted else " rejected"
    return (
        f'<div class="rule{rejected}" data-rule="{rule["id"]}" data-cases-open="{str(cases_open).lower()}">'
        f'<div class="rule-head"><span class="risk {risk}">{RISK_LABEL.get(risk, risk)}</span>'
        f'<div class="rule-main"><div class="rule-text">{rule["text"]}</div>{ears}{toggle}</div>'
        f'<div class="rule-ctl"><label class="switch">'
        f'<input type="checkbox" data-rule="{rule["id"]}" class="rule-adopt"{checked}{disabled}><span></span></label>'
        f'<button type="button" class="rule-cmt{cmt_on}" title="1 行コメント" aria-label="1 行コメント"><svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2.5 3.5h11v7h-6l-3 2.5v-2.5h-2z" stroke-linejoin="round"/></svg></button></div></div>'
        f'{cases_html}<div class="rule-note-wrap"{note_hidden}>{note_input}</div></div>'
    )


def render_rules_question(q: dict, is_open: bool) -> str:
    decisions = q.get("answer") or {}
    if not isinstance(decisions, dict):
        decisions = {}
    rows = "".join(render_rule(r, decisions.get(r["id"]), is_open) for r in q["rules"])
    adopt = sum(1 for r in q["rules"] if decisions.get(r["id"]) != "reject")
    foot = f'<div class="rules-foot">採用 {adopt} / 不採用 {len(q["rules"]) - adopt}</div>'
    user_note = render_user_note(q, is_open)
    return (
        f'<div class="q-card wide" data-q="{q["id"]}" data-type="rules" data-open="{str(is_open).lower()}">'
        f'{render_q_head(q, is_open)}<p class="q-body">{q["body"]}</p>'
        f'<div class="rules">{rows}</div>{foot}{user_note}{render_why(q)}{render_answer_note(q)}'
        f'{render_chat(q, is_open)}</div>'
    )


def render_question(q: dict, is_open: bool) -> str:
    if q.get("type") == "rules":
        return render_rules_question(q, is_open)
    multi = q.get("multi", False)
    image = render_image(q["image"], q.get("image_caption")) if q.get("image") else ""
    answered = q.get("answer") or []
    # open のとき推奨理由は最初の推奨選択肢の中に出す。回答済みはカード下の行に出す
    why_inline_left = bool(q.get("why")) and is_open
    opts = []
    for o in q["options"]:
        rec = '<span class="rec-badge">推奨</span>' if o.get("recommended") else ""
        why_inline = ""
        if why_inline_left and o.get("recommended"):
            why_inline = f'<span class="why-inline">{q["why"]}</span>'
            why_inline_left = False
        oimg = f'<img src="{o["image"]}" alt="">' if o.get("image") else ""
        has_img = " has-img" if o.get("image") else ""
        selected = " selected" if o["key"] in answered else ""
        disabled = "" if is_open else " disabled"
        opts.append(
            f'<button class="opt{has_img}{selected}"{disabled} data-key="{o["key"]}">'
            f'<span class="key">{o["key"]}</span>'
            f'<span class="body">{o["label"]}{why_inline}</span>{rec}{oimg}</button>'
        )
    opts_class = "opts has-images" if any(o.get("image") for o in q["options"]) else "opts"
    hint = '<div class="opt-hint">複数選べます</div>' if multi else '<div class="opt-hint">1 つ選びます</div>'
    why = "" if is_open else render_why(q)
    user_note = render_user_note(q, is_open)
    # 画像(モック)付きの問いは、狭い列だと見にくいので広い画面でも 1 行を使い切る
    wide = " wide" if q.get("image") or opts_class != "opts" else ""
    return (
        f'<div class="q-card{wide}" data-q="{q["id"]}" data-multi="{str(multi).lower()}" data-open="{str(is_open).lower()}">'
        f'{render_q_head(q, is_open, multi)}<p class="q-body">{q["body"]}</p>{image}'
        f'{hint}<div class="{opts_class}">{"".join(opts)}</div>{user_note}{why}{render_answer_note(q)}'
        f'{render_chat(q, is_open)}</div>'
    )


def question_config(q: dict) -> dict:
    """ブラウザ側 JS に渡す、問いごとの最小情報。"""
    if q.get("type") == "rules":
        return {"id": q["id"], "type": "rules", "rules": [r["id"] for r in q["rules"]], "recommended": []}
    return {"id": q["id"], "recommended": [o["key"] for o in q["options"] if o.get("recommended")]}


def render_round(r: dict) -> str:
    parts = []
    if r.get("facts"):
        items = "".join(f"<li>{f}</li>" for f in r["facts"])
        parts.append(
            '<section class="panel dashed"><h2><span>前提事実<small>AI 調査済み</small></span></h2>'
            f'<ul class="items">{items}</ul></section>'
        )
    is_open = r.get("status") == "open"
    for q in r.get("questions", []):
        parts.append(render_question(q, is_open))
    if r.get("declarations"):
        items = "".join(f"<li>{d}</li>" for d in r["declarations"])
        head = "合意サマリ" if r.get("status") == "info" else "宣言事項<small>異議があれば自由記述へ</small>"
        parts.append(f'<section class="panel dashed"><h2><span>{head}</span></h2><ul class="items">{items}</ul></section>')
    if r.get("free_text_answer"):
        parts.append(
            f'<div class="free-answer"><span class="label">自由記述の回答</span>{r["free_text_answer"]}</div>'
        )
    return "".join(parts)


def dashboard_url(topic: str, root: str | None = None) -> str:
    """統合ページで、この題材を開く URL。root は PARALLEL_GRILL_URL(子セッションに渡る)。"""
    base = root if root is not None else os.environ.get("PARALLEL_GRILL_URL", "")
    base = base.strip() or DEFAULT_DASHBOARD_ROOT
    return f"{base.rstrip('/')}/#{topic}"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: render.py <topic>.json")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    topic = data["topic"]
    rounds = data["rounds"]
    open_rounds = [r for r in rounds if r.get("status") == "open"]
    open_round = open_rounds[-1] if open_rounds else None

    tabs, panes = [], []
    active = open_round or rounds[-1]
    for r in rounds:
        label = r.get("label") or f'Round {r["round"]}'
        is_active = " active" if r is active else ""
        status = r.get("status")
        mark = {"answered": '<span class="mark answered">✓</span>', "open": '<span class="mark open">●</span>'}.get(status, "")
        tabs.append(
            f'<button class="tab-btn{is_active}" data-target="pane-{r["round"]}">{label}{mark}</button>'
        )
        panes.append(f'<div class="tab-pane{is_active}" id="pane-{r["round"]}">{render_round(r)}</div>')

    open_q_count = len(open_round.get("questions", [])) if open_round else 0
    state = (
        f'<span class="state">Round {open_round["round"]} / 質問 {open_q_count} 件</span>'
        if open_round else '<span class="state done">完了</span>'
    )
    if open_round:
        config = {
            "topic": topic,
            "openRound": open_round["round"],
            "openQuestions": [question_config(q) for q in open_round.get("questions", [])],
        }
        answer_bar = (
            '<div class="answer-bar"><div class="answer-inner">'
            '<textarea id="free-text" rows="1" hidden placeholder="自由記述(補足・選択肢外の回答など)"></textarea>'
            '<div class="answer-row">'
            f'<div class="progress"><span id="progress-text">0 / {open_q_count} 回答</span><i><b id="progress-fill"></b></i></div>'
            '<div id="answer-string" class="empty">選択肢を選ぶと回答がここに組み立てられます</div>'
            '<div class="answer-btns">'
            '<button class="btn" id="free-toggle">+ 自由記述</button>'
            '<button class="btn" id="all-rec">推奨で埋める</button>'
            '<button class="btn" id="copy-btn">コピー</button>'
            '<button class="btn primary" id="submit-btn">送信</button>'
            '</div></div><div id="submit-status"></div></div></div>'
        )
    else:
        config = {"topic": topic, "openRound": None, "openQuestions": []}
        answer_bar = ""

    tree = render_tree_panel(data["tree"]) if data.get("tree") else ""
    body_class = ' class="has-bar"' if open_round else ""

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="description" content="grill の質問票。選択肢を選んで送信すると、AI が次の作業に進みます。">
<title>Grill: {data["title"]}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔥</text></svg>">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{FONTS_URL}" rel="stylesheet">
<style>{CSS}</style>
</head>
<body{body_class}>
<div class="wrap">
<header>
  <div class="kicker"><span class="topic">{topic}</span>{state}</div>
  <h1>{data["title"]}</h1>
  <p class="lede">{data.get("intro", "")}</p>
</header>
{tree}
<div class="tabs">{"".join(tabs)}</div>
{"".join(panes)}
</div>
{answer_bar}
<div id="lightbox"><img src="" alt=""></div>
<script>{JS.replace("__CONFIG__", json.dumps(config, ensure_ascii=False))}</script>
{UI_COMMENTS_TAG}
</body>
</html>
"""
    out = OUT_DIR / f"grill-{topic}.html"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out}\n{dashboard_url(topic)}")


if __name__ == "__main__":
    main()
