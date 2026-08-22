# Ti amo Jewelry Studio

イタリアンゴールドジュエリーの EC 向けに、商品写真 3 枚から掲載用 10 枚を自動生成する社内ツール（卒業制作）。

## ひとことで言うと

自社 EC 担当が、ほぼそのまま商品ページに載せられる 10 枚を、数分で揃える。

## ロードマップ

```
 Ti amo Jewelry Studio
 =====================

 [完了] Phase 0  完成形UIモック
    |
    v
 [完了] Phase 1  骨組み
    |            認証 / ジョブCRUD / ダミー10枚ZIP / UI寄せ
    |
    v
 [完了] Phase 2  ディテール3枚
    |            3枚UP → 切り抜き → 背景+地金
    |
    v
 [完了] Phase 3  人物シーン + 実物合成
    |              着用4 / 全身2 / 引き+インセット + transform
    |              （FAL_KEY ありで Flux+PuLID、なしはローカル仮）
    |
    v
 [完了] Phase 4  レビュー完成
    |           インセット選び直し / 枠再生成 / 失敗リトライ / プリセットCRUD / 進捗
    |
    v
 [今ここ] Phase 5  本番固め
                14日削除・1ジョブ200円・学校用 Vercel 公開（完了）
                ワーカーのクラウド接続は会社で毎日使う段階

 ユーザーの流れ（完成時）:
  ログイン → 3枚UP+設定 → 待つ → 直す → ZIP
```

| Phase | 内容 | 状態 |
|---|---|---|
| 0 | 完成形 UI モック | **完了** |
| 1 | monorepo・認証・ジョブ CRUD・UI モック寄せ | **完了** |
| 2 | 切り抜き＋背景＋地金でディテール 3 枚 | **完了** |
| 3 | 人物シーン生成＋実物合成＋ transform | **完了**（persona 本番写真は任意） |
| 4 | インセット選び直し・枠再生成・失敗リトライ・プリセット CRUD・進捗表示 | **完了** |
| 5 | 画質・14 日削除・デプロイ | **進行中**（14日削除・200円停止・学校用 Vercel 公開まで。ワーカーは提出までこのPC） |

## ドキュメント

- **公開モック:** https://ti-amo-jewelry-studio.surge.sh
- **ローカルモック:** [docs/mockups/product-ui.html](docs/mockups/product-ui.html)
- **要件:** [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- **設計:** [docs/DESIGN.md](docs/DESIGN.md)
- **レビュー記録:** [docs/REVIEW.md](docs/REVIEW.md)

## 出力 10 枚の内訳

1. **ディテール 3 枚** — AI 人物なし。背景差し替え＋色調整のみ  
2. **着用シーン 4 枚** — オフィス／カフェ／デート／休日（部位はカテゴリで読替）  
3. **全身コーディネート 2 枚** — トーンを 2 つ選択  
4. **引き＋右下インセット 1 枚** — 雰囲気とサイズ感を 1 枚で両立  

### ピアスの両耳対応

撮影は他カテゴリと同じく「片耳分を 3 アングル」でOK。ペア写真を分割する必要はなく、
ツール側で 1 個の切り抜きを鏡写しして両耳に自動合成します。レビュー画面では左右それぞれの
大きさ・位置を個別にドラッグ調整できます（顔の大きさに合わせた微調整用）。

## 技術方針

- **画面:** Next.js（App Router）＋共有社内ログイン  
- **メタデータ正本:** Postgres（Redis はキュー）  
- **処理:** Python ワーカー。1ジョブ＝1プロセス＋チェックポイント  
- **商品:** 実物写真の切り抜き合成（AI にジュエリーを描かせない）  
- **人物:** 本番は fal.ai（Flux + PuLID）。`FAL_KEY` が無いときは同一 persona のローカル仮シーン  

詳細は [docs/DESIGN.md](docs/DESIGN.md)。

## リポジトリ構成

```
apps/web/          # Next.js（画面・API・認証）
apps/worker/       # Python ワーカー（切り抜き・シーン・合成）
packages/shared/   # スロット定義・ZIP ファイル名・カテゴリ
docker-compose.yml # Postgres / Redis / MinIO
docs/              # 要件・設計・モック
```

## 起動

手順の正本は [apps/web/README.md](apps/web/README.md)。ワーカーは [apps/worker/README.md](apps/worker/README.md)。

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

別ターミナル:

```bash
cd apps/worker
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m worker.pipeline
```

- http://localhost:3000  
- ログイン: `ec-team` / `studio`（`.env.local` で変更可）

## いまできること

- 共有ログイン・ジョブ一覧（全件）・削除  
- 商品写真 3 枚アップロード＋プリセットでジョブ作成  
- 切り抜き → ディテール 3 枚  
- 人物シーン（`FAL_KEY` あり → Flux+PuLID／なし → ローカル仮）＋実物合成（着用・全身・引き+インセット）  
- ネックレス／ピアスは顔の位置を見て初期配置する（ズレはレビュー画面のドラッグで再調整可）  
- レビュー画面で**画像上をドラッグ**して大きさ・位置を調整（スライダーではなく直接操作） → ZIP ダウンロード  
- ピアスは片耳分の撮影から自動で両耳へ鏡写し合成。左右は個別に調整可能  
- ダメな枠の**再生成**（人物プリセットは維持）・失敗時は**最初から／失敗した段階からリトライ**  
- 引き＋インセットの右下写真はディテール A/B/C から選び直し可  
- 生成結果は **14 日で自動削除**（一覧に残り日数。期限切れ後は ZIP 不可）  
- 1ジョブの人物生成は **200円まで**（同じジョブの再生成も含む。超えたらそのジョブを停止）  
- 死活確認: http://localhost:3000/api/health  

## 本番（提出まで / 毎日使うとき）

提出までは、生成はこの PC で行います（Postgres / Redis は Docker、画面とワーカーはホスト）。

```bash
docker compose up -d
npm run dev          # または npm run build && npm run start -w @ti-amo/web
# 別ターミナル
cd apps/worker && .venv\Scripts\python.exe -m worker.pipeline
```

学校提出用の公開 URL: **https://ads-graduation-project-web.vercel.app**（本物のアプリ・ログイン必須。ID `ec-team` / パスワード `studio`）。人物生成ワーカーは載せない。

Vercel の Root Directory は `apps/web`。Postgres は Neon（Vercel Storage）。環境変数は `DATABASE_URL` / `NEXTAUTH_URL` / `NEXTAUTH_SECRET` / `AUTH_USER` / `AUTH_PASSWORD`。

Vercel 上ではジョブの新規生成はできません（Redis と画像ディスクがこの PC にあるため）。生成は `localhost:3000`。会社で毎日使う段階で、ワーカーを VPS / Railway / Render に移し、Redis と画像をクラウドへ繋ぎます。詳細は [REQUIREMENTS.md](docs/REQUIREMENTS.md) §9。 
