# Phase 1–3 — Web app

起動・ログイン・いまできることの概要はリポジトリ直下の [README.md](../../README.md) を正とします。

## 前提

- Node.js 20+
- Docker（Postgres / Redis / MinIO）
- Phase 2 以降: Python ワーカー（`apps/worker`）を別ターミナルで起動

## 起動手順

```bash
# リポジトリルート
cp .env.example apps/web/.env
cp .env.example apps/web/.env.local
docker compose up -d
npm install
npm run db:generate
npm run db:push
npm run db:seed
npm run dev
```

別ターミナルでワーカー:

```bash
cd apps/worker
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m worker.pipeline
```

ブラウザで http://localhost:3000  
ログイン: `ec-team` / `studio`

## Web 側のメモ

- ジョブ受付・進捗ポーリング・プレビュー配信・ZIP・大きさ/位置の再合成はここ
- プリセット（人物・背景・トーン）の追加・改名・削除は `/presets`
- 重い切り抜き・シーン・初回合成は `apps/worker`
- レビュー画面の大きさ・位置調整はスライダーではなく**画像上のドラッグ＆リサイズ**（`SlotCardClient`）。
  人物シーン（`/api/jobs/[id]/scene/[slot]`）とジュエリー切り抜き（`/api/jobs/[id]/cutout/main`）を
  別々に配信し、ブラウザ側でジュエリー画像を重ねてドラッグ操作、指を離すと `PATCH /api/jobs/[id]/slots/[slot]`
  で実際の合成画像を焼き直す
- ピアスはアンカーが左右 2 点あり、`transforms` 配列（アンカーごとに `{scale, offsetX, offsetY}`）で
  左右を個別に調整できる。他カテゴリはアンカー 1 点なので配列の要素数は 1
- 見た目の正本: [公開モック](https://ti-amo-jewelry-studio.surge.sh) / `docs/mockups/product-ui.html`
