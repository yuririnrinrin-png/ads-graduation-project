# Phase 1–3 — Web app

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

## いまできること

- 商品3枚 UP → 切り抜き → ディテール3
- 人物シーン（ローカル仮）＋実物合成（着用・全身・引き+インセット）
- レビューで大きさ・位置調整（確定で再合成）
- ZIP / ジョブ削除 / 全件一覧

人物の本番AI（顔固定）・枠の再生成 UI は Phase 4 以降／未決事項。  
見た目の正本: [公開モック](https://ti-amo-jewelry-studio.surge.sh)
