# Claude Code 向け

このリポジトリを Claude Code で開いたとき、最初に [docs/HANDOFF.md](docs/HANDOFF.md) を読む。開始フレーズは同じでよい:

「`docs/HANDOFF.md` を読んで続けてください」

正本（HANDOFF より優先）:

- [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- [docs/DESIGN.md](docs/DESIGN.md)
- [README.md](README.md)

## やらないこと（ユーザーが言うまで）

- 人物シーンの**品質プロンプト**と `scene_qa.py` の追加いじり（「品質を再開」まで）
- 商品ページ／レビューへの「AI使用」表記
- ワーカーを Vercel に置くこと。提出まではこの PC。会社で毎日使う段階で VPS / Railway / Render

## 人物7枚を直すとき

`apps/worker/worker/scene_gen.py` を編集する前に [`.cursor/rules/scene-persona.mdc`](.cursor/rules/scene-persona.mdc) を守る。

機械チェックは Cursor と同じスクリプト:

```
apps/worker/.venv/Scripts/python.exe .cursor/hooks/check_scene_spec.py
```

（Mac/Linux は `apps/worker/.venv/bin/python`）

Claude Code では `.claude/settings.json` のフックが、保存後と停止時に同じ検査を回す。本体を複製しない。

## 起動の約束

- 画面は **http://localhost:3000 だけ**
- ワーカーは venv で **1プロセス**。ホットリロードなし。起動ログ: `scene_qa=on job_cost_limit=200yen`
- `FAL_KEY` などは `apps/web/.env.local`（Git に載せない）

## チャット全文

Cursor の `agent-transcripts` は Git に入っていない。必要ならこの PC の

`%USERPROFILE%\.cursor\projects\c-Users-yurir-src-ads-graduation-project\agent-transcripts`

をコピーする。接続文字列が混ざるので GitHub には上げない。続きだけなら HANDOFF で足りる。
