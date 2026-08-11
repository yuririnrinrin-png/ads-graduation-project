# Phase 1 — Web app

## 前提

- Node.js 20+
- Docker（Postgres / Redis / MinIO）

## 起動手順

```bash
# リポジトリルート
cp .env.example apps/web/.env.local
docker compose up -d
npm install
npm run db:generate
npm run db:push
npm run db:seed
npm run dev
```

ブラウザで http://localhost:3000  
ログイン: `ec-team` / `studio`（`.env.local` で変更可）

## Phase 1 でできること

- 共有社内ログイン
- プリセット付きジョブ作成
- ダミー 10 枚（2000×2000 JPEG）の ZIP ダウンロード

実画像の切り抜き・人物生成は Phase 2 以降（`apps/worker`）。
