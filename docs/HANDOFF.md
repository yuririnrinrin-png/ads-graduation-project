# 引き継ぎメモ（新しいチャット用）

新しいチャットを始めるときは、このファイルを読んでもらうだけで直近の状況が伝わります。
（例: 「`docs/HANDOFF.md` を読んで続けてください」と伝える）

正本のドキュメントは以下の3つ。詳しい経緯や決定理由はここを見ればわかります。

- [docs/REQUIREMENTS.md](REQUIREMENTS.md) — 決まっていること／まだ決めてないこと
- [docs/DESIGN.md](DESIGN.md) — 画面フロー・パイプライン・フェーズの状態・変更履歴
- [README.md](../README.md) — セットアップ手順・現在できること・ロードマップ

## 直近の状態（2026-08-13 20:46 時点）

- **フェーズ:** Phase 3（人物シーン生成＋実物合成＋大きさ位置調整）着手中
- **ユーザー確認:** 配置・影・傾き・シーンの多様化は「だいぶ良くなった」。この状態を commit / push した

### いま動くこと

- 商品写真 3 枚 → 切り抜き → ディテール 3 枚（背景＋地金）
- `FAL_KEY` あり: 同一人物の 7 シーン（Flux 参照顔 + PuLID）。なし: ローカル仮
- 実物切り抜きを人物に合成。軽量な影＋ネックレス/ピアスの固定チルト
- ネックレス/ピアスの初期位置は顔の矩形から自動でずらす（鼻に乗る事故の対策）
- レビュー画面で画像上ドラッグして大きさ・位置を調整 → ZIP

### このチャットで入れた変更（新しいチャットが把握すべき本体）

1. **配置バグ（ネックレスが顔に乗る）の軽量対策**
   - 本格の首ランドマーク検出はしない。顔の矩形（YuNet）だけ取り、顎の下＝鎖骨／顔の左右＝耳へずらす
   - リング／ブレスレットは対象外（手元なので顔では解けない）
   - ずらし量は `JobAsset.transform` の `offsetX/Y` に保存。Web 再合成（sharp）は変更不要
   - 着用／全身は**スロットごと**に別 transform（以前は着用4枚で同じ値を共有していた）
   - ドラッグ上限 `TRANSFORM_OFFSET_LIMIT = 1000`（Python 側 `OFFSET_LIMIT` と同じ）
   - 顔は画面中央のものを優先（デート相手やボケを最大顔として拾うとネックレスが外れる）
   - 実装: `apps/worker/worker/face_anchor.py` + `worker/models/face_detection_yunet_2023mar.onnx`
   - 依存: `opencv-python-headless==5.0.0.93`

2. **7枚が全部同じ（正面・髪下ろし・無表情）だった問題**
   - 原因: `fal-ai/flux-pulid` の `max_sequence_length` 初期値が **128**。ポーズ・髪型・デート相手がプロンプト後半にあり、切られて参照顔のコピーになっていた
   - 対応: `max_sequence_length: "512"`、`true_cfg: 1.8`、ポーズ／髪型／デート相手を文の先頭へ
   - 髪アップ枠（オフィス／デート／全身1）は `id_weight` 0.48。それ以外 0.55〜0.62
   - `PERSONA_LOOK` は髪型に触れない。髪の色・長さは `PERSONA_HAIR`、状態は `HAIR_STYLE`

3. **実キーで確認したジョブ（最新が正）**
   - **見るならこれ:** `c19bea57d7fc94fc8a1cf657c`
     - デート: ぼかした男性＋髪アップ。ネックレスは本人の首
     - オフィス／全身1: お団子。カフェ／休日／全身2: 下ろし＋歯が見える笑顔
     - 場面（オフィス机・カフェ・ビーチ）は枠ごとに違う
     - 残る限界: 顔はカメラに向きがち。引きのハーフアップは効きにくい
     - レビュー: `/jobs/c19bea57d7fc94fc8a1cf657c`
   - 配置確認用（多様化前）: `c3a33f2de22c54ab1b67ffbeb`
   - 中間（512 のみ・髪アップ弱）: `cc2a2d39d3543425a9bd144c0`
   - 配置バグ再現の旧ジョブ: `cmsr9b090001dfdd06s0cw3m7`

### 次のチャットが最初にやるべきこと

1. ワーカーは**更新後コードで1つだけ**起動する。このチャットの実キー確認は
   `python -m worker.pipeline run <jobId>` の単発実行だったので、UI から新規ジョブを作る前に
   待ち受けワーカーを立てること
2. 顔の横向き・引きのハーフアップをさらに足すなら、枠ごとの `id_weight` を再調整
   （下げすぎると別人になる）
3. Phase 3 残り: persona 参照写真の本番データ投入（`PresetPersona.imageKey`）
4. Phase 4: インセット選び直し・枠再生成（ボタンは disabled）・失敗段階からのリトライ

## 技術的なポイント

- ジュエリー配置の正は `packages/shared/src/index.ts` の `CATEGORY_ANCHORS` / `BODY_ANCHORS`。
  ピアスだけアンカー2点（左右鏡写し）
- 実座標は `SIZE * anchor.x + transform.offsetX`（`SIZE = 2000`）。仕様を変えるときは
  Python（`pipeline.py`）と Web（`recomposite.ts` / `SlotCardClient.tsx`）の**両方**
- `rotate` はユーザー調整不可の固定チルト（時計回り）。Pillow だけ符号反転
- 影はアルファをぼかした暗いシルエットを本体の下に先乗せするだけ（3D ライティングではない）
- 人物シーンは `apps/worker/worker/scene_gen.py`
  - `POSE_VARIATION` / `HAIR_STYLE` / `WEAR_SETTING` / `WEAR_FASHION` / `TONE_SETTING`
  - `SLOT_NEGATIVE_EXTRA` — 枠ごとに「参照顔のコピー」を否定
  - デートは「TWO PEOPLE」＋ぼかした男性の後ろ姿・手元を先頭付近に書く
- 顔検出: 中央 18–82% かつ顔中心が上 70% にある顔を優先。外れれば従来の固定アンカー
- ドラッグ UI: シーンと切り抜きを別配信 → 指を離すと `PATCH /api/jobs/[id]/slots/[slot]` で焼き直し

## 開発環境の起動

```bash
docker compose up -d          # Postgres / Redis / MinIO
npm install
npm run dev                   # apps/web（Next.js, localhost:3000 or 3002 if busy）
```

別ターミナルでワーカー（**必ず1つだけ**）:

```bash
cd apps/worker
.venv\Scripts\activate        # 初回は python -m venv .venv 済ませておく
pip install -r requirements.txt
python -m worker.pipeline
```

単発デバッグ: `python -m worker.pipeline run <jobId>`

ログイン: `ec-team` / `studio`

本物の人物シーンを試すときは `apps/web/.env.local` に:

```
FAL_KEY=fal_...
```

（キーは `key_id:key_secret` の形。fal.ai ダッシュボードの Keys ページで発行）

**注意:**
- ワーカーはホットリロードなし。コード変更後・`FAL_KEY` 追加後は必ず再起動
- 複数ワーカー禁止。疑わしいときは PowerShell で
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'worker.pipeline' }`
  を確認し、余分を `Stop-Process -Id <pid> -Force`
- fal.ai のチャージ直後は `403 Exhausted balance` が数分続くことがある
- 1ジョブあたり画像生成 API は目安 最大約 8 回（参照顔 1 + シーン 7）

## 未着手・今後の候補

- 顔の完全な横顔、引きのハーフアップはまだ弱い
- 首の骨格ランドマークによる動的アンカーは対象外（顔矩形＋固定オフセットのみ）
- AI がシーンに細いネックレスを描いてしまうことがある（禁止プロンプトはあるが完全ではない）
- Phase 3 残り: persona 参照写真の本番データ
- Phase 4: インセット選び直し・枠再生成・進捗磨き・失敗段階からリトライ・プリセット追加
- Phase 5: 画質・リトライ・14日削除・デプロイ固め
- `docs/REQUIREMENTS.md` §9「未決」（コスト上限の具体値、ホスティング等）

## 短い経緯（必要なら）

- 人物シーンを fal.ai（Flux + PuLID）で生成できるようにした。ワーカーは常に1つ
- `PERSONA_LOOK` に髪型を書くと後段の「アップに」と矛盾 → 髪の色・長さだけ分離
- 固定アンカー（ネックレス y=36%）は構図ブレに弱く、寄ったバストアップで顔に乗った
- 影＋固定チルト（案B）を先に入れた。3D パース補正と AI 描画はしない方針のまま
- そのあと顔矩形で初期位置をずらす軽量対策を入れ、続けてプロンプト切断（128）を直した
