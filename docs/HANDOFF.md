# 引き継ぎメモ（新しいチャット用）

新しいチャットを始めるときは、**このファイルを読んでもらうだけ**で直近の状況が伝わります。

開始フレーズ: 「`docs/HANDOFF.md` を読んで続けてください」

正本（このメモより優先）:

- [docs/REQUIREMENTS.md](REQUIREMENTS.md) — 決まっていること／まだ決めてないこと
- [docs/DESIGN.md](DESIGN.md) — 画面フロー・パイプライン・フェーズ
- [README.md](../README.md) — セットアップ・ロードマップ

リポジトリ: `yuririnrinrin-png/ads-graduation-project`、ブランチ `main`。

---

## 直近の状態（2026-08-22）

- **フェーズ:** Phase 5。**14日削除・1ジョブ200円停止・学校用 Vercel 公開は入った。**
- **学校提出 URL:** https://ads-graduation-project-web.vercel.app （ログイン必須。`ec-team` / `studio`）。先生が入れるところまで確認済み。
- **fal.ai:** 2026-08-17〜18 にアカウントロック（`TOP_UP` / `Exhausted balance`）。ダッシュボードに残高があっても API が 403 になる既知不具合。**2026-08-21 に解除済み**。サポートは **support@fal.ai**（英語）。
- **再開ジョブ:** `cmsxf1t6y000mfdbk361q6bdo` は **ready**。品質確認ジョブ: `cmt2yl1rd0001fdngeoj80agb`（引き＋インセットは正面の写真で通った）。
- **品質プロンプトの追加いじり**は、ユーザーが「品質を再開」と言うまでやらない。
- **ワーカーはホットリロードなし。同時に1プロセスだけ。** Python を直したら再起動。起動ログ: `scene_qa=on hand_id_weight=0.18 job_cost_limit=200yen`。引きカット（`wide_inset`）は PuLID を使わず `flux/dev`。
- **画面は 3000 だけ。** 誤って 3001/3002 が立ったら止める。

### Grill 決定（2026-08-22）

- **公開:** Vercel に本物のアプリ（ログイン必須）。Postgres も Vercel 側（Neon）。学校の URL 公開要件はこれで満たした。
- **ワーカー:** Vercel に置かない。提出まではこの PC。会社で毎日使う段階で VPS / Railway / Render。
- **課金:** 1ジョブ **200円**（初回＋同じジョブの再生成）。超えたらジョブを止める。実装済み（固定 150円/USD、fal 2MP 切り上げ → Flux 約8円 / PuLID 約10円）。
- **AI表記:** ツールは書かない（商品ページにもレビューにも出さない）。

### 置き場所（提出まで / 毎日使うとき）

| | 提出まで（今） | 会社で毎日使うとき |
|---|---|---|
| 画面 | この PC の :3000。Vercel はログイン＋一覧用 | Vercel |
| Postgres | ローカル Docker。公開面は Neon（Vercel Storage） | 同じ Neon でよい |
| Redis | この PC の Docker | Upstash 等（画面とワーカーの両方から届く場所） |
| 画像 | この PC の `apps/web/.data` | S3 互換（R2 等） |
| ワーカー | この PC（venv・1プロセス） | VPS / Railway / Render |

### Vercel / Neon（公開面）

- Vercel プロジェクト名: **`ads-graduation-project-web`**
- GitHub: `yuririnrinrin-png/ads-graduation-project`、Root Directory: **`apps/web`**
- 公開 URL: https://ads-graduation-project-web.vercel.app
- 死活: https://ads-graduation-project-web.vercel.app/api/health
- Postgres: Neon 連携 **`neon-champagne-magnet`**。地域は Tokyo が無かったので **Washington, D.C. (East)**。**Neon Auth は OFF**。Free プラン。
- 本番の環境変数（Settings → Environments → Production）:
  - Neon が入れた `DATABASE_URL` / `DATABASE_URL_UNPOOLED`（Sensitive。Vercel 上では後から値を開けない）
  - 手で入れた `NEXTAUTH_URL`（`https://ads-graduation-project-web.vercel.app`）/ `NEXTAUTH_SECRET` / `AUTH_USER` / `AUTH_PASSWORD`
- クラウド DB へは、この PC から `$env:DATABASE_URL=...; npm run db:push` → `npm run db:seed` 済み（表＋プリセット 人物3 / 背景4 / トーン4）。
- `main` へ push すると Vercel が自動で Redeploy する。
- **公開 URL ではジョブ新規生成はできない**（Redis と画像がこの PC のため。`REDIS_URL` 未設定時は日本語で拒否）。生成デモは localhost:3000。
- Neon の接続文字列がチャット／ターミナルに出た。提出が済んだら Neon でパスワードを作り直すとよい。**接続文字列はコミットしない・メールに貼らない。**
- 別プロジェクト `tk-jewelry-workspace` は別作品。触らない。
- `vercel env pull` はローカルの Docker 用 `.env` を上書きするので使わない。

### 1ジョブ200円（実装の要点）

- 正: `packages/shared/src/index.ts` の定数と `apps/worker/worker/job_cost.py` を同じにする。
- ワーカーが fal を呼ぶ**前**に残額を見て、超えるなら `JobCostLimitError`（日本語）。成功後に `Job.apiSpendYen` と `apiCallCount` を加算。
- 同じジョブの枠再生成も累計。ディテール再生成は fal を使わないので上限後も可。
- 旧ジョブで `apiSpendYen=0` かつ `apiCallCount>0` なら、PuLID 単価で概算して埋める。
- 画面: レビューに `約◯/200円`。上限後は着用・全身の再生成とリトライを止める。

### 製品の約束（変えない）

- ジュエリーは **アップロード実物の切り抜き合成**。AI に描かせない。3D で腕に巻きつけない。手検出もしない。
- **胴体は正面±15°。** 顔は斜め・横向きを7枚のうち数枚入れる。後ろ姿・肩越し・歩いている真横は禁止。
- **7枠の表情はすべて別**（`SLOT_EXPRESSION`）。目線は伏し目・外し目・柔らかい正面を混ぜる。
- **デート:** 女性が手前でピント。男性は **顔や斜めが見える**（後ろ姿だけにしない）。二人で楽しんでいる雰囲気。ジュエリーが見える。男性は背景で小さくぼかす。男性の手元・時計を手前にしない。
- **髪型:** アップと耳かけダウンの両方（ダウンはカフェと引き）。
- **服:** 首元開きとタートルを混在。
- **リング／ブレス着用4枚:** 手首／指が主役。顔は奥か端。
- **全身・引き:** 立ち姿。手首／指はフレーム内。**腕組み禁止。**
- モデル（男性含む）に **時計・他のジュエリーを描かせない。** 全ての場面。商品はあとから合成。
- 大きなズレはレビューのドラッグ／回転で救う。
- ピアスは片耳分3枚 → 両耳へ鏡写し。横顔では片方を消せる（`SlotTransform.hidden`）。

### いま動くこと

- 3枚 UP → 切り抜き → ディテール3。
- `FAL_KEY` あり: Flux 参照顔 + PuLID で着用シーン。なし: ローカル仮。
- リング／ブレスの **全身・引き**、およびネックレス等の **引き（wide_inset）** は PuLID を使わず `fal-ai/flux/dev`。
- 合成: 接触影、明るさの軽い合わせ、原本色寄り。ネックレス／ピアスは顔矩形で初期位置。髪オーバーレイは **ネックレスのみ**。
- レビュー: ドラッグ、回転 ±180°、ピアス片方消し、枠再生成、インセット元変更、ZIP。
- 失敗: 最初から／失敗した段階からリトライ。12分以上止まっているときは強制リトライも出る。
- **進捗画面:** 5段階（切り抜き→ディテール→人物シーン→合成→仕上げ）、目安と経過、画面を閉じても続く旨。途中画像の先出しなし。
- **14日削除:** ワーカーが約10分おきに期限切れジョブのファイルを消す。一覧・ジョブ画面を開いたときも消す。状態は `expired`。ZIP / 再生成は不可。
- **1ジョブ200円:** 人物生成（fal）の累計。同じジョブの枠再生成も含む。超えたらそのジョブを停止（日本語）。ディテール再生成は課金なしなので可。
- **学校公開:** https://ads-graduation-project-web.vercel.app （ログイン可。生成は不可）
- **死活確認:** http://localhost:3000/api/health ／ 公開面は `/api/health`
- **プリセット管理** `/presets`: 人物・背景・トーンの追加／改名／削除。
- 画面とワーカーは **別ターミナル**。同じだと `localhost:3000` が拒否される。

---

## この期間に入れた修正（2026-08-17〜21）

会話の流れ: 新ジョブが人物シーンで落ちてリトライできない → 胴体が15°を超える → Windows で JPEG 上書き失敗 → fal ロックで失敗なのにクレジットが減る。

### 1. ジョブが人物 QA で死なない

以前は `wear_cafe` などが「顔が正面すぎ」で何度も落ち、`raise` して **ジョブ全体が failed** になった。PuLID は参照顔（正面）をコピーするので、斜め枠は永遠に通らないことがある。

今: やり直し後も通らなければ **最後の1枚を残して次のカットへ**（`keeping last frame`）。レビューまで届く。

関連: `apps/worker/worker/scene_gen.py` の `_generate_scene_until_qa`。

### 2. 胴体 ±15° を守る（ユーザー指摘）

「顔を横に」と書くと、モデルが **胴体ごと横向き** になった（デート・ホリデー・全身・引き）。原因:

- `HEAD: STRICT SIDE PROFILE 80-90` のような指示
- ネガティブに `frontal face` を入れて全身を横にしていた
- QA が「正面顔」を落とすので、生成側が全身横向きで逃げていた

今:

- 胴体は両肩が見える正面。横向きなのは **顔だけ（だいたい40〜50度）**
- 真横の全身プロンプトは禁止（フックも `80-90` / `strict side profile` を落とす）
- `scene_qa.py`: 胸幅／顔幅が狭い → `torso too side-on`。真横顔（`eye_span < 0.22`）も胴体横向き扱い
- 斜め枠の「正面すぎ」は証明写真レベルだけ落とす（`eye_span > 0.42` かつ `nose_offset < 0.05`）

機械チェック: `.cursor/hooks/check_scene_spec.py`、ルール `.cursor/rules/scene-persona.mdc`。

### 3. Windows の JPEG 上書き失敗

エラー: `[Errno 22] Invalid argument: ...\scene\wear_holiday.jpg`

画面が同じ JPEG を開いたまま上書きすると Windows で落ちる。`apps/worker/worker/image_io.py` で一時ファイル経由＋リトライ。開くときはハンドルをすぐ閉じる。

### 4. リトライ UX

- 失敗後は「最初から／失敗した段階から」
- DB が `running` のまま（ワーカー落ち）だと 409 だった → `force` で上書き可
- 進捗画面が **12分以上更新されない** ときだけ「止まっているのでやり直す」を出す
- `fail_job` は `rollback` してから `failed` を書く（トランザクション壊れで失敗が残らないように）

### 5. fal クレジットを無駄にしない（未コミットだった分をこのコミットに含む）

失敗なのに残高が減る理由:

- 受付 POST は 200（課金）→ 結果 GET が 403 ロック
- 1カットあたり PuLID を何度も回し、途中結果を捨てていた
- 途中までできたカットを保存せず、リトライで7枚すべて再生成

今:

- `FalBillingError`: ロック／残高切れですぐ止める。日本語メッセージを DB に残す
- `MAX_SCENE_TRIES = 2`、`MAX_FLUX_TRIES = 1`。PuLID で1枚あれば Flux 予備は呼ばない
- カットごとにすぐ保存。`fromStage=scene` のリトライは **すでにある `{slot}.jpg` を再利用**
- `worker/__init__.py` は空（フックが `scene_gen` を読むとき pipeline を引っ張らない）

ロック中は新ジョブ・リトライをしない。チャージ前の連打は途中課金だけ進む。

---

## fal.ai 運用メモ

- キー: `apps/web/.env.local` の `FAL_KEY`（コミットしない。メールにも貼らない）
- ダッシュボードに残高があっても API が `User is locked. Reason: TOP_UP` を返すことがある（fal 側の解除漏れ）
- サポート: **support@fal.ai**（英語）。ログインと同じメールから送る。キー本体は送らない
- 解除後にまだ 403 なら、同じアカウントで **API キーを新規発行** して `.env.local` を差し替え、ワーカー再起動
- 公式: https://fal.ai/docs/documentation/model-apis/support

---

## プリセット CRUD

画面: http://localhost:3000/presets。社内ログイン済みなら誰でも編集。

写真の実体: `apps/web/.data/presets/{personas,backgrounds}/{id}.jpg`（git 対象外）。**背景写真を足したあとはワーカー再起動。** 人物写真は次ジョブから。

---

## 次のチャットが最初にやること

開始フレーズ: 「`docs/HANDOFF.md` を読んで続けてください」

1. Docker + `npm run dev`（**3000 だけ**）+ ワーカー1つ（venv、ログ `scene_qa=on job_cost_limit=200yen`）。Python を直したら再起動。
2. 人物シーンのプロンプト／QA は、ユーザーが「品質を再開」と言うまで触らない。
3. 会社で毎日使う段階になるまで、ワーカーのクラウド接続（Upstash + 画像の S3/R2）はやらない。
4. `main` push 後に Vercel が自動ビルドする。失敗していたら Deployments のログを見る。

---

## 技術メモ

- 配置の正: `packages/shared/src/index.ts` の `CATEGORY_ANCHORS` / `BODY_ANCHORS`。`pipeline.py` と必ず同じ。
- 実座標: `SIZE * anchor.x + transform.offsetX`（`SIZE = 2000`）。
- 顔検出配置: ネックレス／ピアスのみ。リング／ブレスは固定アンカー＋ドラッグ。
- 再生成は `persona_ref.jpg` を再利用（再クロップしない）。壊れたら `persona_ref_src`。
- ワーカー停止中のジョブは Redis から消え、DB が `running` のままだと通常リトライは 409。12分経過で強制リトライ、または `POST /api/jobs/:id/retry` に `{ force: true }`。
- PuLID 手カテゴリ: `id_weight=0.18`。`start_step` 禁止。
- `python -m worker.pipeline` は **venv の python** で起動する（システムの `python` だと numpy なしで落ちる）。

主なファイル:

- `apps/worker/worker/job_cost.py` — 1ジョブ200円。fal の前に止める
- `apps/web/src/lib/job-cost-guard.ts` — 再生成／リトライの API 側ガード
- `apps/web/vercel.json` — Root Directory `apps/web` 用の install
- `apps/worker/worker/scene_gen.py` — プロンプト、PuLID/Flux、課金中断、保存
- `apps/worker/worker/scene_qa.py` — 生成後の顔／胴体チェック
- `apps/worker/worker/image_io.py` — Windows 安全な読み書き
- `apps/worker/worker/pipeline.py` — パイプライン、`fail_job`、既存シーン再利用
- `apps/web/src/components/RetryActions.tsx` / `ProgressPanel.tsx` / `app/api/jobs/[id]/retry/route.ts`
- `.cursor/hooks/check_scene_spec.py`

## 起動（PC再起動後）

```bash
docker compose up -d
npm run dev          # リポジトリルート。このターミナルは画面専用
```

別ターミナル（1つだけ）:

```bash
cd apps/worker
.venv\Scripts\activate
python -m worker.pipeline
```

- http://localhost:3000
- ログイン: `ec-team` / `studio`
- 本物の人物: `apps/web/.env.local` の `FAL_KEY`
- プリセット: http://localhost:3000/presets

生成中にワーカーを止めない。fal の人物枚は数分。`202 Accepted` は待ち中。

## 未着手 / やらない

- Phase 5 残り: ワーカーのクラウド接続（毎日使う段階）。Neon パスワードの作り直し（接続文字列がチャットに出た）
- 手・手首の自動検出、ブレスレットの3D巻きつけ、AI にジュエリーを描かせること（方針外）
- Shopify への自動アップロード（v1 対象外）
- 商品ページ／レビューへの「AI使用」自動表記（Grill でやらないと決定）
