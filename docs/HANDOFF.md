# 引き継ぎメモ（新しいチャット用）

新しいチャットを始めるときは、このファイルを読んでもらうだけで直近の状況が伝わります。
（例: 「`docs/HANDOFF.md` を読んで続けてください」と伝える）

正本のドキュメントは以下の3つ。詳しい経緯や決定理由はここを見ればわかります。

- [docs/REQUIREMENTS.md](REQUIREMENTS.md) — 決まっていること／まだ決めてないこと
- [docs/DESIGN.md](DESIGN.md) — 画面フロー・パイプライン・フェーズの状態・変更履歴
- [README.md](../README.md) — セットアップ手順・現在できること・ロードマップ

## 直近の状態（2026-08-12 時点）

- **フェーズ:** Phase 3（人物シーン生成＋実物合成＋大きさ位置調整）着手中
- **直近やったこと:**
  1. レビュー画面の大きさ・位置調整を、スライダーから「画像の上で直接ドラッグ＆リサイズ」に変更
  2. ピアスは片耳分（1個）を3アングル撮影するだけでよく、システム側で自動的に両耳へ鏡写し合成する方式に決定・実装
  3. ピアスの左右それぞれの大きさ・位置を個別にドラッグ調整できるように対応（顔の大きさに合わせた微調整用）
  4. 上記をコミット・GitHub へ push 済み

## 技術的なポイント（新しいチャットが実装を続けるときに知っておくべきこと）

- ジュエリーの配置は「アンカー」という概念で管理している（`packages/shared/src/index.ts` の
  `CATEGORY_ANCHORS` / `BODY_ANCHORS`）。ほとんどのカテゴリはアンカー1点、ピアスだけ2点（左右耳）
- 各アンカーごとに `{scale, offsetX, offsetY}` の transform を持つ。DB（`JobAsset.transform`）には
  アンカー数と同じ長さの配列で保存される
- ドラッグUIは `apps/web/src/components/SlotCardClient.tsx`。人物シーン単体
  （`/api/jobs/[id]/scene/[slot]`）とジュエリー切り抜き単体（`/api/jobs/[id]/cutout/main`）を
  別々に配信し、ブラウザ側で重ねて操作 → 指を離すと `PATCH /api/jobs/[id]/slots/[slot]` で
  実際の合成画像（sharp）を焼き直す
- 実際の初回合成（ジョブ作成時）は Python ワーカー（`apps/worker/worker/pipeline.py`）が担当。
  Web 側の再合成ロジック（`apps/web/src/lib/recomposite.ts`, sharp）とほぼ同じ計算式を
  Python（Pillow）で再実装しているので、アンカーやtransformの仕様を変える時は**両方**直す必要がある

## 開発環境の起動

```bash
docker compose up -d          # Postgres / Redis / MinIO
npm install
npm run dev                   # apps/web（Next.js, localhost:3000）
```

別ターミナルでワーカー:

```bash
cd apps/worker
.venv\Scripts\activate        # 初回は python -m venv .venv 済ませておく
python -m worker.pipeline
```

ログイン: `ec-team` / `studio`

**注意:** ワーカーは Python プロセスなのでコード変更後は再起動が必要（ホットリロードなし）。
今回の作業中、実際に一度これで「古いロジックのまま」動いてしまうミスがあった。

## 未着手・今後の候補

- Phase 4: インセット選び直し・枠再生成・進捗磨き・プリセット追加
- Phase 5: 画質・リトライ・14日削除・デプロイ固め
- `docs/REQUIREMENTS.md` §9「未決」に残っている項目（画像生成APIベンダー選定など）
