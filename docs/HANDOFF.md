# 引き継ぎメモ（新しいチャット用）

新しいチャットを始めるときは、このファイルを読んでもらうだけで直近の状況が伝わります。
（例: 「`docs/HANDOFF.md` を読んで続けてください」と伝える）

正本のドキュメントは以下の3つ。詳しい経緯や決定理由はここを見ればわかります。

- [docs/REQUIREMENTS.md](REQUIREMENTS.md) — 決まっていること／まだ決めてないこと
- [docs/DESIGN.md](DESIGN.md) — 画面フロー・パイプライン・フェーズの状態・変更履歴
- [README.md](../README.md) — セットアップ手順・現在できること・ロードマップ

## 直近の状態（2026-08-14）

- **フェーズ:** Phase 4 着手中（レビューの直し系はユーザー確認済み）
- Phase 3（配置・影・傾き・シーン多様化）は以前「だいぶ良くなった」で commit / push 済み

### ユーザー確認（このチャット）

- 完了ジョブの**枠再生成**: 最初は同じ絵だった → seed を毎回乱数にしたあと **うまくいった**（人物は維持、構図が変わる）
- **インセット元の変更**: うまくいった
- **失敗からのリトライ**: うまくいった
- ディテール A/B/C の再生成は実物切り抜きなので、ほぼ同じになるのは想定どおり

### いま動くこと

- 商品写真 3 枚 → 切り抜き → ディテール 3 枚（背景＋地金）
- `FAL_KEY` あり: 同一人物の 7 シーン（Flux 参照顔 + PuLID）。なし: ローカル仮
- 実物切り抜き合成。影＋明るさ合わせ＋肌色の軽い乗算。ネックレス/ピアスの固定チルト。顔矩形で初期位置。カフェ／引きは髪オーバーレイ（取れたとき）
- レビュー: ドラッグ調整、枠再生成、インセット元変更、ZIP
- 失敗画面: 最初からリトライ / 失敗した段階からリトライ

### このチャットで入れた変更

1. **Phase 4 レビュー操作**
   - `POST /api/jobs/:id/retry` `{ mode: "start" | "failed" }`
   - `POST /api/jobs/:id/slots/:slot/regen`
   - `PATCH /api/jobs/:id/inset` `{ insetSlot: "detail_a"|"detail_b"|"detail_c" }`
   - Redis payload は jobId 文字列、または JSON `{ jobId, fromStage, slots }`
   - 単枠再生成は `scene/persona_ref.jpg` を再利用（別人にしない）
   - `Job.insetSlot`（Prisma）。`apps/web` で `npx prisma db push` 済み想定
2. **再生成が同じ絵になる問題**
   - `fal-ai/flux-pulid` に毎回ランダム `seed`（未指定だと同じショットのコピー）
   - preview/scene の `Cache-Control` を no-store。画像 URL に `job.updatedAt` を付与
3. **進捗が途中で止まって見える問題**
   - ワーカーを人物シーン中に止めると、Redis から job は消えているのに DB は `running` のまま
   - 画面のポーラーは status 変化だけ見ていた → **stage 変化でも refresh**
   - 壊れた JSON をキューに入れるとワーカー全体が落ちていた → parse 失敗はログして継続
4. **着用の貼り付け感**
   - 人物プロンプト: **胴体は正面±15°、顔は斜め・横向き可**。首・耳が見える髪型（カフェ／引きはダウン＋耳かけ）。着用4枚は開いた首元
   - 表情は枠ごとに別（キリッ／自然＋伏し目／甘え／華やか／静かな横顔／屈託ない／上品＋伏し目）
   - 合成: 薄い接触影、明るさはごく軽く。色は原本寄り。カフェ／引きは髪オーバーレイ
   - レビュー: ドラッグ＋回転スライダー（±45°）
   - 新規ジョブ: メインはできるだけ正面、と案内するだけ

確認に使ったジョブ例: `cmss8dt5x0009fdrs9618vmfd`（ネックレス、シーンから再開したあと再生成・インセット確認）

### 次のチャットが最初にやるべきこと

1. ワーカーは**更新後コードで1つだけ**。ホットリロードなし。複数禁止
2. 生成中にワーカーを止めない。止めたジョブは Redis に残らないので、DB が `running` のままだと UI のリトライは 409。必要なら DB を `failed` にするか、JSON で `fromStage` を再キュー
3. Phase 4 残り: 進捗表示の磨き、プリセット追加 CRUD
4. Phase 3 残り: persona 本番写真。`apps/web/.data/personas/{sofia,elena,mia}.jpg` を置けば seed が `imageKey` を埋める（首・耳が見える写真が望ましい）
5. Phase 5: 14日削除・デプロイ固め

## 技術的なポイント

- 配置の正は `packages/shared/src/index.ts` の `CATEGORY_ANCHORS` / `BODY_ANCHORS`
- 実座標は `SIZE * anchor.x + transform.offsetX`（`SIZE = 2000`）。仕様変更は Python と Web の両方
- 人物シーン: `apps/worker/worker/scene_gen.py`（seed は生成のたびに乱数）
- 顔検出: 中央 18–82% かつ顔中心が上 70% を優先
- パイプライン再開: `fromStage` より前の段階はディスクのチェックポイントを読む

## 開発環境の起動

```bash
docker compose up -d
npm install
cd apps/web && npx prisma db push   # insetSlot 列。初回やスキーマ変更後
npm run dev                         # リポジトリルート
```

別ターミナル（**必ず1つだけ**）:

```bash
cd apps/worker
.venv\Scripts\activate
python -m worker.pipeline
```

ログイン: `ec-team` / `studio`  
本物の人物シーン: `apps/web/.env.local` に `FAL_KEY`（`key_id:key_secret`）

**注意:**
- コード変更後・`FAL_KEY` 追加後はワーカー再起動
- fal の人物 7 枚は数分。ログの `202 Accepted` は待ち中
- 1ジョブあたり画像生成 API は目安 最大約 8 回（参照顔 1 + シーン 7）。再生成は対象枠のみ +1

## 未着手・今後の候補

- 首ランドマークによる動的アンカーは対象外
- persona 本番参照写真（首・耳が見えるもの）
- Phase 4 残り: 進捗磨き・プリセット追加
- Phase 5: 画質・14日削除・デプロイ
- `docs/REQUIREMENTS.md` §9「未決」
