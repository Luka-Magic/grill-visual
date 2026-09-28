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
        "why": str?,
        "answer": ["a"]?, "answer_note": str?,     # status=answered のとき(answer_note = AI 側の注記)
        "user_note": str?                          # 質問ごとのユーザー自由記述(送信 JSON の notes 由来)
     }]?,
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

CSS = """
:root {
  --bg: #21252b; --surface: #282c34; --surface-dim: #2f343f; --border: #3a4048;
  --text: #b6bec9; --text-bright: #dde3ea; --text-dim: #7b8494;
  --blue: #61afef; --green: #98c379; --orange: #d19a66; --red: #e06c75;
  font-size: 16px;
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--bg); color: var(--text); line-height: 1.75;
  font-family: "Hiragino Sans", "Yu Gothic UI", "Noto Sans JP", "Meiryo", sans-serif;
  padding-bottom: 150px;
}
code, .mono {
  font-family: "Consolas", "Menlo", monospace; font-size: 0.86em;
  background: var(--surface-dim); border-radius: 4px; padding: 1px 5px; color: var(--text-bright);
}
.wrap { max-width: 880px; margin: 0 auto; padding: 30px 20px; }
header { border-bottom: 2px solid var(--border); padding-bottom: 16px; margin-bottom: 20px; }
.kicker {
  font-family: "Consolas", monospace; font-size: 12px; letter-spacing: 0.13em;
  text-transform: uppercase; color: var(--green); margin-bottom: 6px;
}
.kicker::before { content: "❯ "; color: var(--blue); }
h1 { font-size: 24px; line-height: 1.4; font-weight: 700; color: var(--text-bright); }
.lede { color: var(--text-dim); margin-top: 8px; font-size: 14.5px; }
.panel {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 20px; margin-bottom: 20px;
}
.panel h2 {
  font-family: "Consolas", monospace; font-size: 12.5px; letter-spacing: 0.1em;
  text-transform: uppercase; font-weight: 500; color: var(--blue); margin-bottom: 10px;
}
.panel ul { padding-left: 20px; font-size: 14px; }
.panel li { margin-bottom: 6px; overflow-wrap: break-word; }
table.cases { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 13.5px; }
table.cases th { text-align: left; color: var(--blue); font-weight: 500; padding: 5px 8px;
  border: 1px solid var(--border); background: var(--surface-dim); white-space: nowrap; }
table.cases td { padding: 5px 8px; border: 1px solid var(--border); vertical-align: top; overflow-wrap: anywhere; }
table.cases td:first-child { font-weight: 500; color: var(--text-bright); }
.q-card table.cases { display: block; overflow-x: auto; }
table.case { border-collapse: collapse; width: 100%; margin: 8px 0 12px; font-size: 14px; }
table.case th { width: 5.5em; text-align: left; color: var(--blue); font-weight: 500; vertical-align: top;
  padding: 5px 8px; border: 1px solid var(--border); background: var(--surface-dim); white-space: nowrap; }
table.case td { padding: 5px 8px; border: 1px solid var(--border); vertical-align: top; overflow-wrap: anywhere; }
.tree { list-style: none; padding-left: 0; font-size: 14px; }
.tree ul { list-style: none; padding-left: 24px; border-left: 1px solid var(--border); margin-left: 6px; }
.tree li { margin: 5px 0; }
.badge {
  display: inline-block; border-radius: 4px; font-size: 11px; font-weight: 500;
  font-family: "Consolas", monospace; padding: 0 7px; margin-right: 7px; white-space: nowrap;
}
.badge.done { color: var(--green); border: 1px solid var(--green); }
.badge.open { color: var(--orange); border: 1px solid var(--orange); }
.tree .note { color: var(--text-dim); font-size: 12.5px; }
.tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 18px; }
.tab-btn {
  font-family: "Consolas", monospace; font-size: 13px; font-weight: 500;
  background: var(--surface); color: var(--text-dim);
  border: 1px solid var(--border); border-radius: 6px 6px 0 0;
  padding: 7px 16px; cursor: pointer;
}
.tab-btn.active { color: var(--text-bright); border-bottom-color: var(--blue); background: var(--surface-dim); }
.tab-btn:hover { color: var(--text-bright); }
.tab-pane { display: none; }
.tab-pane.active { display: block; }
.q-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 8px; padding: 20px 22px; margin-bottom: 18px;
}
.q-head { display: flex; gap: 10px; align-items: baseline; margin-bottom: 8px; min-width: 0; }
.q-num { font-family: "Consolas", monospace; font-weight: 700; color: var(--orange); font-size: 15px; flex-shrink: 0; }
.q-title { font-weight: 700; font-size: 16.5px; color: var(--text-bright); }
.multi-note {
  font-family: "Consolas", monospace; font-size: 11px; color: var(--text-dim);
  border: 1px solid var(--border); border-radius: 4px; padding: 0 7px; white-space: nowrap;
}
.q-body { font-size: 14px; margin-bottom: 12px; }
.q-image { margin: 0 0 12px; }
.q-image img {
  max-width: 100%; border: 1px solid var(--border); border-radius: 6px; cursor: zoom-in; display: block;
}
.q-image figcaption { font-size: 12px; color: var(--text-dim); margin-top: 4px; }
.opts { display: flex; flex-direction: column; gap: 8px; }
.opt {
  display: flex; gap: 10px; align-items: flex-start; text-align: left;
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 6px; padding: 10px 14px; cursor: pointer;
  font: inherit; font-size: 14px; color: var(--text); width: 100%; min-width: 0;
}
.opt:hover { border-color: var(--blue); }
.opt.selected { border-color: var(--blue); background: rgba(97, 175, 239, 0.12); color: var(--text-bright); }
.opt[disabled] { cursor: default; }
.opt[disabled]:hover { border-color: var(--border); }
.opt.selected[disabled] { border-color: var(--green); background: rgba(152, 195, 121, 0.12); }
.opt.selected[disabled]:hover { border-color: var(--green); }
.opt .key { font-family: "Consolas", monospace; font-weight: 700; color: var(--orange); flex-shrink: 0; }
.opt .body { overflow-wrap: break-word; min-width: 0; }
.opt img { max-width: 220px; border-radius: 4px; border: 1px solid var(--border); display: block; margin-top: 6px; cursor: zoom-in; }
.rec-badge {
  display: inline-block; color: var(--green); border: 1px solid var(--green);
  border-radius: 4px; font-family: "Consolas", monospace; font-size: 11px;
  padding: 0 7px; margin-left: 8px; white-space: nowrap;
}
.why {
  margin-top: 12px; padding: 9px 13px; border-left: 3px solid var(--green);
  background: var(--surface-dim); border-radius: 0 6px 6px 0; font-size: 13px;
}
.why strong { color: var(--green); }
.answer-note {
  margin-top: 12px; padding: 9px 13px; border-left: 3px solid var(--blue);
  background: var(--surface-dim); border-radius: 0 6px 6px 0; font-size: 13px;
}
.q-note {
  display: block; width: 100%; margin-top: 12px; font: inherit; font-size: 13.5px;
  border: 1px solid var(--border); border-radius: 6px; padding: 8px 12px;
  background: var(--bg); color: var(--text); resize: vertical; min-height: 46px;
}
.q-note:focus { outline: none; border-color: var(--blue); }
.q-note::placeholder { color: var(--text-dim); }
.q-note[disabled] {
  background: var(--surface-dim); color: var(--text); opacity: 1;
  -webkit-text-fill-color: var(--text); cursor: default; resize: none; margin-top: 4px;
}
.q-note-label { display: block; color: var(--text-dim); font-size: 12px; margin-top: 12px; }
.free-answer {
  background: var(--surface-dim); border: 1px dashed var(--border); border-radius: 6px;
  padding: 10px 14px; font-size: 13.5px; margin-bottom: 18px; white-space: pre-wrap;
}
.free-answer .label { color: var(--text-dim); font-size: 12px; display: block; margin-bottom: 4px; }
.answer-bar {
  position: fixed; left: 0; right: 0; bottom: 0;
  background: var(--surface); border-top: 2px solid var(--blue); padding: 11px 20px;
}
.answer-inner { max-width: 880px; margin: 0 auto; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
#free-text {
  flex: 1 1 100%; font: inherit; font-size: 13.5px;
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px;
  background: var(--bg); color: var(--text); resize: vertical; min-height: 34px; max-height: 110px;
}
#answer-string {
  flex: 1; min-width: 200px; font-family: "Consolas", monospace; font-size: 13px;
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 12px; overflow-x: auto; white-space: nowrap; color: var(--text-bright);
}
#answer-string.empty { color: var(--text-dim); }
.btn {
  font: inherit; font-size: 13.5px; font-weight: 500; border-radius: 6px;
  padding: 8px 16px; cursor: pointer; border: 1px solid var(--border);
  background: var(--surface-dim); color: var(--text-bright); white-space: nowrap;
}
.btn.primary { background: var(--blue); border-color: var(--blue); color: #14161a; font-weight: 700; }
.btn:hover { opacity: 0.85; }
.btn[disabled] {
  background: var(--surface-dim); border-color: var(--border); color: var(--text-dim);
  font-weight: 500; cursor: default;
}
.btn[disabled]:hover { opacity: 1; }
#submit-status { font-size: 13px; color: var(--green); font-weight: 500; }
#lightbox {
  display: none; position: fixed; inset: 0; background: rgba(10, 12, 16, 0.9);
  z-index: 50; cursor: zoom-out; padding: 30px;
}
#lightbox.show { display: flex; align-items: center; justify-content: center; }
#lightbox img { max-width: 100%; max-height: 100%; border-radius: 6px; }
@media (prefers-reduced-motion: no-preference) {
  .opt, .btn, .tab-btn { transition: border-color 0.12s, background 0.12s, opacity 0.12s, color 0.12s; }
}
"""

JS = """
(function () {
  var CONFIG = __CONFIG__;
  var answers = {};
  (CONFIG.openQuestions || []).forEach(function (q) { answers[q.id] = []; });
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
    if (typeof d.free_text === "string") freeInput.value = d.free_text;
    submitted = d.submitted === true;
    renderBar();
    if (submitted) {
      status.textContent = "送信済みの回答です(変えるなら選び直して再送信)";
      status.style.color = "var(--green)";
    }
  }

  function renderBar() {
    var parts = (CONFIG.openQuestions || [])
      .filter(function (q) { return answers[q.id].length > 0; })
      .map(function (q) { return q.id + ": (" + answers[q.id].join(",") + ")"; });
    if (parts.length === 0) {
      bar.textContent = "選択肢をクリックすると回答がここに組み立てられます";
      bar.classList.add("empty");
    } else {
      bar.textContent = parts.join(" / ");
      bar.classList.remove("empty");
    }
  }

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
      if (!q.recommended.length) return;
      answers[q.id] = q.recommended.slice();
      var card = document.querySelector('.q-card[data-q="' + q.id + '"][data-open="true"]');
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
    var hasAnswers = (CONFIG.openQuestions || []).some(function (q) { return answers[q.id].length > 0; });
    var hasNotes = Object.keys(notes).length > 0;
    if (!hasAnswers && !freeText && !hasNotes) {
      status.textContent = "選択・メモ・自由記述のどれかを入れてください";
      status.style.color = "var(--red)";
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = "送信中…";
    status.textContent = "送信中…";
    status.style.color = "var(--text-dim)";
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
      status.style.color = "var(--green)";
      submitted = true;
      saveDraft();
      if (window.parent !== window) {  // 統合ページの iframe 内なら、親に知らせて一覧を即時更新させる
        window.parent.postMessage({ type: "grill-submitted", topic: CONFIG.topic, round: CONFIG.openRound }, location.origin);
      }
    }).catch(function (e) {
      submitBtn.disabled = false;
      submitBtn.textContent = "送信";
      status.textContent = "送信失敗(" + e.message + ")— コピーでチャットに貼ってください";
      status.style.color = "var(--red)";
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
        badge = f'<span class="badge {n.get("status", "open")}">{"決定" if n.get("status") == "done" else "未決"}</span>'
        note = f' <span class="note">{n["note"]}</span>' if n.get("note") else ""
        children = f'<ul>{render_tree(n["children"])}</ul>' if n.get("children") else ""
        items.append(f"<li>{badge}{n['label']}{note}{children}</li>")
    return "".join(items)


def render_image(path: str, caption: str | None = None) -> str:
    cap = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f'<figure class="q-image"><img src="{path}" alt="">{cap}</figure>'


def render_user_note(q: dict, is_open: bool) -> str:
    """質問ごとのユーザー自由記述欄。open は入力可、過去ラウンドは記入済みだけ読み取り専用。"""
    if is_open:
        return (
            f'<textarea class="q-note" data-q="{q["id"]}" rows="2" '
            f'placeholder="補足・メモ(任意)"></textarea>'
        )
    if not q.get("user_note"):
        return ""
    # ユーザーが打った文字列なのでエスケープする(他の項目と違い HTML として扱わない)
    return (
        '<span class="q-note-label">あなたのメモ</span>'
        f'<textarea class="q-note" rows="2" disabled>{html.escape(q["user_note"])}</textarea>'
    )


def render_question(q: dict, is_open: bool) -> str:
    multi = q.get("multi", False)
    multi_note = '<span class="multi-note">複数選択可</span>' if multi else ""
    image = render_image(q["image"], q.get("image_caption")) if q.get("image") else ""
    answered = q.get("answer") or []
    opts = []
    for o in q["options"]:
        rec = '<span class="rec-badge">➡️ 推奨</span>' if o.get("recommended") else ""
        oimg = f'<img src="{o["image"]}" alt="">' if o.get("image") else ""
        selected = " selected" if o["key"] in answered else ""
        disabled = "" if is_open else " disabled"
        opts.append(
            f'<button class="opt{selected}"{disabled} data-key="{o["key"]}">'
            f'<span class="key">({o["key"]})</span>'
            f'<span class="body">{o["label"]}{rec}{oimg}</span></button>'
        )
    why = f'<div class="why"><strong>推奨理由:</strong> {q["why"]}</div>' if q.get("why") else ""
    note = f'<div class="answer-note">{q["answer_note"]}</div>' if q.get("answer_note") else ""
    user_note = render_user_note(q, is_open)
    return (
        f'<div class="q-card" data-q="{q["id"]}" data-multi="{str(multi).lower()}" data-open="{str(is_open).lower()}">'
        f'<div class="q-head"><span class="q-num">{q["id"]}</span>'
        f'<span class="q-title">{q["title"]}</span>{multi_note}</div>'
        f'<p class="q-body">{q["body"]}</p>{image}'
        f'<div class="opts">{"".join(opts)}</div>{user_note}{why}{note}</div>'
    )


def render_round(r: dict) -> str:
    parts = []
    if r.get("facts"):
        items = "".join(f"<li>{f}</li>" for f in r["facts"])
        parts.append(f'<section class="panel"><h2>前提事実(AI 調査済み)</h2><ul>{items}</ul></section>')
    is_open = r.get("status") == "open"
    for q in r.get("questions", []):
        parts.append(render_question(q, is_open))
    if r.get("declarations"):
        items = "".join(f"<li>{d}</li>" for d in r["declarations"])
        parts.append(f'<section class="panel"><h2>宣言事項(異議は自由記述で)</h2><ul>{items}</ul></section>')
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
        tabs.append(
            f'<button class="tab-btn{is_active}" data-target="pane-{r["round"]}">{label}</button>'
        )
        panes.append(f'<div class="tab-pane{is_active}" id="pane-{r["round"]}">{render_round(r)}</div>')

    open_q_count = len(open_round.get("questions", [])) if open_round else 0
    state = f'Round {open_round["round"]} / 質問 {open_q_count} 件' if open_round else "完了"
    if open_round:
        config = {
            "topic": topic,
            "openRound": open_round["round"],
            "openQuestions": [
                {
                    "id": q["id"],
                    "recommended": [o["key"] for o in q["options"] if o.get("recommended")],
                }
                for q in open_round.get("questions", [])
            ],
        }
        answer_bar = (
            '<div class="answer-bar"><div class="answer-inner">'
            '<textarea id="free-text" placeholder="自由記述(補足・選択肢外の回答など。空でも OK)"></textarea>'
            '<div id="answer-string" class="empty">選択肢をクリックすると回答がここに組み立てられます</div>'
            '<button class="btn" id="all-rec">全部推奨どおり</button>'
            '<button class="btn" id="copy-btn">コピー</button>'
            '<button class="btn primary" id="submit-btn">送信</button>'
            '<span id="submit-status"></span></div></div>'
        )
    else:
        config = {"topic": topic, "openRound": None, "openQuestions": []}
        answer_bar = ""

    tree = ""
    if data.get("tree"):
        tree = f'<section class="panel"><h2>設計ツリー</h2><ul class="tree">{render_tree(data["tree"])}</ul></section>'

    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grill: {data["title"]}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔥</text></svg>">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="kicker">grill session · {topic} · {state}</div>
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
</body>
</html>
"""
    out = OUT_DIR / f"grill-{topic}.html"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"{out}\n{dashboard_url(topic)}")


if __name__ == "__main__":
    main()
