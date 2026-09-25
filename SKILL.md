---
name: grill-visual
description: grill(計画の問い詰めインタビュー)をタブ式のダーク HTML 質問票で行う。質問はブラウザで提示、回答は送信ボタンで自動回収。「grill して」「質問票で聞いて」「visual grill」などで使用。
---

# Grill Visual — HTML 質問票で grill する

計画・設計・アイデアを実装前に問い詰めて認識ズレをなくす grill を、
ブラウザの質問票で行うスキル。質問データは JSON、レンダーは driver、
回答は送信ボタン → ファイル出現で AI が自動再開する。

## インタビューの規律(grilling 準拠・内蔵)

- 共通理解に達するまでユーザーに徹底的にインタビューする。計画を**設計ツリー**
  (各決定から下位の決定がぶら下がる)として捉える。
- **ラウンド制**: 前提が確定している質問(= フロンティア)だけを 1 ラウンドに
  まとめて聞く。各質問には番号と**推奨案+理由**を付ける。未回答の質問に依存する
  質問は次ラウンドに回す。
- **事実調べは AI の仕事**(ファイル・環境・外部情報は質問前に自分で調査する。
  ユーザーに調べ物をさせない)。**決定はユーザーの仕事**。
- 回答を受けたらツリーを更新し、次のフロンティアを計算して次ラウンドへ。
- フロンティアが空になったら合意サマリを提示し、共有理解の確認を取ってから
  実装に入る。確認前に行動しない。
- アンチパターン: 大きすぎるトピックで grill する / 質問に受け身で答えさせるだけ /
  議論だけして途中でプロトタイプを作らない。

## ワークフロー

1. **事実調査**: 質問の前提となる事実を Bash/Read 等で確定させる。
2. **質問データ作成**: `~/.agent/diagrams/grill-data/<topic>.json` を書く
   (スキーマは `render.py` の docstring 参照。文字列は HTML として挿入されるので
   `<code>` / `<strong>` 可。ユーザー入力や外部データは埋め込まない)。
   - ラウンドはタブになる。過去ラウンドは `"status": "answered"` +
     `answer` / `answer_note` / `user_note` / `free_text_answer` で履歴化、
     現行ラウンドだけ `"status": "open"`。まとめタブは `"status": "info"`。
     `answer_note` は AI 側の注記、`user_note` はユーザーが質問ごとのメモ欄に
     書いた文章(送信 JSON の `notes` 由来)。別枠で両方描画される。
   - `tree` に設計ツリー(決定済み done / 未決 open)を反映する。
   - UI 改善など見た目が論点の質問は、スクリーンショットを
     `~/.agent/diagrams/assets/<topic>/` に置き、質問・選択肢の `image` で参照
     (クリックで原寸表示される)。
3. **レンダー**: `python3 ~/.claude/skills/grill-visual/render.py <topic>.json`
   → `~/.agent/diagrams/grill-<topic>.html`(1 題材 1 ファイル・URL 固定)。
4. **配信**: `~/.claude/skills/grill-visual/serve.sh` を実行(冪等)。
   `http://localhost:8787/` で配信される(127.0.0.1 限定・LAN 非公開)。
5. **提示**: チャットに URL `http://localhost:8787/grill-<topic>.html` を書く。
   「送信ボタンで回答すると自動で再開する。コピー文字列・チャット直書きでも可」
   と短く添える。自由記述・選択肢外の回答を必ず歓迎する。質問ごとのメモ欄と
   画面下の全体自由記述欄があり、どちらも送信 JSON に載る。送信が成功すると
   ボタンは「送信済み」で無効化され、失敗すると「送信」に戻って再試行できる。
6. **回答待ち**: Monitor で回答ファイルを監視する(1 回きりの通知で良いので
   until ループ + exit):
   `until [ -f "$HOME/.agent/diagrams/answers/<topic>-round-<N>.json" ]; do sleep 1; done; echo 受信`
   ユーザーがチャットで直接回答した場合は TaskStop で監視を止める。
7. **次ラウンド**: 回答 JSON を Read → データ JSON を更新(現行ラウンドを
   answered 化・次ラウンド追加・ツリー更新)→ 再レンダー。URL は変わらない。
   回答 JSON は `{"answers": {"Q1": ["a"]}, "notes": {"Q1": "…"}, "free_text": "…"}`
   の形。`answers[Qn]` → その質問の `answer`、`notes[Qn]` → `user_note`、
   `free_text` → ラウンドの `free_text_answer` に写す。`notes` は書かれた質問の
   キーだけ入る。
8. **完了**: フロンティアが空になったら「実装サマリ」info タブを足して確認を取る。
   CONTEXT.md / ADR 化が必要な開発題材では domain-modeling の規律
   (用語の異議はその場で指摘・ADR は「戻しにくい/文脈なしでは不可解/実トレードオフ」
   の 3 条件が揃うときだけ)に従い、リポジトリにファイルを増やす前に置き場所の承認を取る。

## 構成ファイル

- `render.py` — driver(Python3 標準ライブラリのみ)。テンプレート・CSS・JS を内蔵
- `server.py` — 配信 + `POST /submit`(ThreadingHTTPServer。127.0.0.1:8787)
- `serve.sh` — サーバーの冪等起動(ポート衝突・二重起動を検知)

## トラブルシューティング(実際に踏んだもの)

- **ページが開かない/固まる**: 旧実装のシングルスレッド HTTPServer はブラウザの
  keep-alive 接続 1 本で全リクエストが詰まった。ThreadingHTTPServer で解消済み。
  再発時は `pkill -f "grill-visual/server\.[p]y"` → `serve.sh`。
  (pkill のパターンに `[p]` を入れないと自分のシェルごと kill される)
- **送信ボタンが失敗する**: サーバー停止が原因ならフォールバック(コピー文字列 /
  チャット直書き)で回答をもらい、サーバーは次ラウンド提示時に立て直す。
