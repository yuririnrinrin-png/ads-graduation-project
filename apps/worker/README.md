# Ti amo Jewelry Studio — Python worker (Phase 2–3)

Redis キュー `tiamo:jobs` を待ち、1ジョブずつ:

`ingest → cutout → detail → scene → composite → inset → ready`

## 前提

- Docker で Postgres / Redis が起動している
- `apps/web` と同じ `DATABASE_URL` / `REDIS_URL`
- 生成ファイルはデフォルトで `apps/web/.data/jobs/...`（`DATA_ROOT` で変更可）

## セットアップ

```bash
cd apps/worker
python -m venv .venv
# Windows:
.venv\Scripts\activate
pip install -r requirements.txt
python -m worker.pipeline
```

単発実行（デバッグ）:

```bash
python -m worker.pipeline run <jobId>
```

## Phase の中身

| 段階 | 内容 |
|---|---|
| cutout / detail | 淡色背景マット＋背景・地金（Phase 2） |
| scene | 人物シーン7枚（いまは同一 persona のローカル仮生成。FAL 等は未決差し替え） |
| composite | メイン切り抜きをカテゴリ別アンカーに合成。transform 保存 |
| inset | 引きにディテールAを右下インセット |

レビュー画面の大きさ・位置変更は Web（sharp）が scene＋cutout から再合成します。
