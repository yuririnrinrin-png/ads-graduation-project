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
- 重い切り抜き・シーン・初回合成は `apps/worker`
- 見た目の正本: [公開モック](https://ti-amo-jewelry-studio.surge.sh) / `docs/mockups/product-ui.html`
