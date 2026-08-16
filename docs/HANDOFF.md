# 引き継ぎメモ（新しいチャット用）

新しいチャットを始めるときは、このファイルを読んでもらうだけで直近の状況が伝わります。

正本:

- [docs/REQUIREMENTS.md](REQUIREMENTS.md) — 決まっていること／まだ決めてないこと
- [docs/DESIGN.md](DESIGN.md) — 画面フロー・パイプライン・フェーズ
- [README.md](../README.md) — セットアップ・ロードマップ

前チャットの開始フレーズ例: 「`docs/HANDOFF.md` を読んで続けてください」

---

## 直近の状態（2026-08-16）

- **フェーズ:** Phase 4 着手中。レビュー操作（再生成・リトライ・インセット選び直し）は実装済み。プリセット CRUD・進捗磨きは未。
- **直近コミット前の作業:** ブレス／リングの手元構図、回転一周、ピアス片方消し、PuLID の顔検出失敗修正。
- **ブロッキング品質:** リング／ブレスの人物シーンで、手元・手首がまだ安定して写らない。プロンプトは何度か直したが、**ユーザー確認でまだ指先が見えない枠が残る**（オフィスで PC が手を隠す、全身1が後ろ姿、など）。次チャットはここが最優先。

### 製品の約束（変えない）

- ジュエリーは **アップロード実物の切り抜き合成**。AI に描かせない。3D で腕に巻きつけない。
- ネックレス／ピアス: 胴体は正面±15°。顔は斜め・横向き可。カフェ／引きだけ耳かけダウン。
- 大きなズレはレビューのドラッグ／回転で救う。
- ピアスは片耳分3枚 → 両耳へ鏡写し。横顔では **片方を消せる**（`SlotTransform.hidden`）。

### ユーザー確認済み

- ネックレス／ピアスの人物シーンは「だいぶ良い」。
- ピアスの片方消しは確認できた。
- ブレスはジョブは通るが、平面切り抜きが斜めの腕に乗るとシールに見える → **巻きつけはしない**。手首をカメラに向ける＋メイン写真は付けた角度、で緩和。
- リング新規ジョブ: 着用が顔〜胸になり指輪が胸に乗った → 手元を主役にするプロンプトへ変更。その後もオフィス／全身1で指が見えない事例あり（下記「未確認の直し」）。
- 回転スライダーは ±45° では足りない → **±180°（一周）** に変更済み（画面更新だけで使える）。

### いま動くこと

- 3枚 UP → 切り抜き → ディテール3。
- `FAL_KEY` あり: Flux 参照顔 + PuLID で7シーン。なし: ローカル仮。
- 合成: 接触影、明るさの軽い合わせ、原本色寄り。ネックレス／ピアスは顔矩形で初期位置。カフェ／引きの髪オーバーレイは **ネックレスのみ**（ピアスに重ねると消える）。
- レビュー: ドラッグ、回転 ±180°、ピアス片方消し、枠再生成、インセット元変更、ZIP。
- 失敗: 最初から／失敗した段階からリトライ。

---

## この期間で入れた実装

### PuLID が「顔なし」で落ちる問題（修正済み）

- 原因: `fal-ai/flux-pulid` に `start_step>0` を送ると `facexlib align face fail`。リトライしても同じ。
- 対応: `start_step` は送らない。参照顔は YuNet で顔クロップしてから upload。no-face は1回リトライ。キャッシュ `persona_ref.jpg` に顔が無ければ作り直し。
- コード: `apps/worker/worker/scene_gen.py`

### ピアス片方消し（確認済み）

- `SlotTransform.hidden`。レビューの「左を消す／右を消す」。両方消しは不可。
- Web 再合成 `recomposite.ts` と Python `composite_on_scene` の両方で skip。
- ピアス以外のカテゴリには出さない。

### ブレス／リング（進行中・品質未達）

方針: 着用4枚は手元／手首が主役、顔は上端に残す（PuLID の同一顔に顔が必要）。全身・引きは立ち姿だが **指先／手首がフレームに入ること**。手の骨格検出はしない。

主なファイル: `apps/worker/worker/scene_gen.py`

- `HAND_FOCUS_CATEGORIES = {ring, bracelet}`
- 着用: `CATEGORY_FRAMING` を先頭に（手元写真）。ネックレス用の首元ファッションは使わない。
- 全身: 着用のテーブル構図を混ぜない。`CATEGORY_FULL_EXTRA` + `FULL_HAND_POSE`。
- オフィス: PC を指の前に置かない（`WEAR_SETTING_HAND`）。
- 全身1: 顔は斜め、胴体は正面。後ろ姿禁止（`STRICT SIDE PROFILE` は手カテゴリでは使わない）。
- PuLID: 手カテゴリは `id_weight=0.28`, `true_cfg=3.4`, `guidance=6.2`（構図を優先。顔が別人寄りになるリスクあり）。
- 貼り付け初期位置: 着用は下寄り、全身はさらに下（`CATEGORY_ANCHORS` / `BODY_ANCHORS`。shared と pipeline.py を同期）。

新規ジョブヒント: `CATEGORY_WEAR_HINTS` / `CATEGORY_MAIN_PHOTO_HINTS`（メインは真上の円より付けた角度）。

### 回転

- `TRANSFORM_ROTATE_LIMIT = 180`（スライダー ±180°）。API の zod もこれを参照。

---

## 次のチャットが最初にやること

1. Docker / WSL が動いているか確認。PC再開後に **「WSL is unresponsive」** が出ることがある。対処: Docker Desktop の Restart → だめなら管理者 PowerShell で `wsl --shutdown` → PC再起動 → Docker が緑になってから `docker compose up -d`。
2. ワーカーは **更新後コードで1プロセスだけ**。ホットリロードなし。シーンプロンプトを変えたら再起動必須。
3. **リング（必要ならブレス）の新規ジョブ**で、着用4＋全身2＋引きの **すべてで指／手首が見えるか** を確認する。見えない枠のスクリーンショットを根拠に、プロンプトか（方針を破らない範囲の）構図だけ直す。
4. 巻きつけ・AI描画・手検出はまだやらない。
5. 品質が「レビューで仕上げられる」まで行ったら、Phase 4 残り（プリセット CRUD）か Phase 5（14日削除・デプロイ）。

---

## 技術メモ

- 配置の正: `packages/shared/src/index.ts` の `CATEGORY_ANCHORS` / `BODY_ANCHORS`。Python `pipeline.py` と必ず同じ。
- 実座標: `SIZE * anchor.x + transform.offsetX`（`SIZE = 2000`）。
- 人物: `apps/worker/worker/scene_gen.py`。seed は毎回乱数。`start_step` 禁止。
- 顔検出配置: ネックレス／ピアスのみ（`face_anchor.py`）。リング／ブレスは固定アンカー＋手ドラッグ。
- 再生成は `persona_ref.jpg` を再利用。
- ワーカー停止中のジョブは Redis から消え、DB が `running` のままだとリトライ 409。

## 起動

```bash
docker compose up -d
npm run dev          # リポジトリルート
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

注意: 生成中にワーカーを止めない。fal の 7 枚は数分。`202 Accepted` は待ち中。

## 未着手

- リング／ブレスで手元が安定して写ること（最優先・未達）
- 手・手首の自動検出、ブレスレットの3D巻きつけ（方針外）
- persona 本番参照写真（`apps/web/.data/personas/{sofia,elena,mia}.jpg`）
- Phase 4: プリセット追加 CRUD、進捗磨き
- Phase 5: 14日削除、デプロイ
- REQUIREMENTS §9: コスト上限の具体値、本番ホスト、AI表記の要否
