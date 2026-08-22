# Ti amo Jewelry Studio — Python worker (Phase 2–5)

Redis キュー `tiamo:jobs` を待ち、1ジョブずつ:

`ingest → cutout → detail → scene → composite → inset → ready`

キューの中身はジョブ ID、または JSON `{"jobId":"...","fromStage":"scene","slots":["wear_office"]}`。
`fromStage` はその段階から再開。`slots` があるときはその枠だけ再生成する。

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

期限切れジョブのファイルだけ今すぐ消す（通常は起動中に約10分おき）:

```bash
python -m worker.pipeline purge
```

単発実行（デバッグ）:

```bash
python -m worker.pipeline run <jobId>
```

## Phase の中身

| 段階 | 内容 |
|---|---|
| cutout / detail | 淡色背景マット＋背景・地金（Phase 2） |
| scene | 人物シーン7枚。`FAL_KEY` あり → Flux で参照顔＋PuLID で同一人物7枚。なし → ローカル仮 |
| composite | メイン切り抜きをカテゴリ別アンカーに合成。明るさ合わせ・接触影・肌色の軽い乗算。カフェ／引きは髪オーバーレイ。ネックレス／ピアスは顔の位置で初期 transform を枠ごとに保存 |
| inset | 引きに選んだディテール（`Job.insetSlot`、初期は A）を右下インセット |

- アンカーはカテゴリごとに1〜2点（ピアスのみ左右2点）。ピアスは1個の切り抜きを
  鏡写しして両耳に合成し、`transform` はアンカー数と同じ長さの配列で保存する
  （左右を個別に調整できるように）
- レビュー画面の大きさ・位置・回転は Web（sharp）が scene＋cutout から再合成します。

## 人物シーン（fal.ai）

`apps/web/.env.local` に `FAL_KEY` を入れると、ワーカーが本物の人物シーンを呼びます。

```
FAL_KEY=fal_...
```

流れ（1ジョブあたり最大約 8 回の画像生成 API）:

1. `PresetPersona.imageKey`（URL またはローカルパス）があればそれを顔参照に使う  
2. なければ `fal-ai/flux/dev` で人物の参照ポートレートを1枚生成  
3. 各シーンを `fal-ai/flux-pulid` で生成（ジュエリーは描かせない）  
4. 1024 四方 → 2000×2000 に拡大。呼び出し回数は `Job.apiCallCount`、円換算の累計は `Job.apiSpendYen` に加算。1ジョブ 200円を超える呼び出しはしない（日本語でジョブ停止）

キーが無いときは従来どおりローカルのシルエット仮画像です（課金なし）。  
**コード変更後はワーカープロセスの再起動が必要です。**
