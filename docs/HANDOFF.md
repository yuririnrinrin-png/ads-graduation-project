# 引き継ぎメモ（新しいチャット用）

新しいチャットを始めるときは、このファイルを読んでもらうだけで直近の状況が伝わります。
（例: 「`docs/HANDOFF.md` を読んで続けてください」と伝える）

正本のドキュメントは以下の3つ。詳しい経緯や決定理由はここを見ればわかります。

- [docs/REQUIREMENTS.md](REQUIREMENTS.md) — 決まっていること／まだ決めてないこと
- [docs/DESIGN.md](DESIGN.md) — 画面フロー・パイプライン・フェーズの状態・変更履歴
- [README.md](../README.md) — セットアップ手順・現在できること・ロードマップ

## 直近の状態（2026-08-13 時点）

- **フェーズ:** Phase 3（人物シーン生成＋実物合成＋大きさ位置調整）着手中
- **今回やったこと（実キーで検証しながらプロンプトを何度も調整）:**
  1. **人物シーンを fal.ai で本当に生成できるようにした**（`apps/worker/worker/scene_gen.py`）
     - `FAL_KEY` あり → `fal-ai/flux/dev` で参照顔を1枚生成 →
       `fal-ai/flux-pulid` で同一人物の7シーンを生成（ジュエリーは描かせない）
     - `FAL_KEY` なし → 従来のローカル仮シーン（課金なし、開発用）
     - `PresetPersona.imageKey`（URL/ローカルパス）があれば参照顔に優先利用
     - API 呼び出し回数は `Job.apiCallCount` に加算（目安 最大約8回/ジョブ）
  2. **実キーで1ジョブ試したところ見つかった問題と対処**
     - fal.ai の残高チャージ直後は「アカウントロック」がすぐ解除されないことがある
       （$10チャージ後も `403 Forbidden: Exhausted balance` が数分続いた。時間を置いたら解消）
     - ワーカーを何度も再起動した結果、**古いワーカープロセスが複数同時に残ってしまい**、
       `FAL_KEY` を知らない古いプロセスがジョブを横取りしてローカル仮シーンのまま完了する事故があった
       → ワーカーは**常に1つだけ**動かす。疑わしい時は `worker.pipeline` を名前に含む
       python プロセスを全部 kill してから1つだけ起動し直すのが安全
     - レビュー画面の「失敗した段階からリトライ」ボタンは**まだ未実装（Phase 4）**。
       押せないのは仕様。失敗時は「最初から（新規ジョブ）」を使う
  3. **プロンプトを3往復ほど調整**（実際の生成結果を見ながら）
     - 初回: 着用4枚の背景が全部同じような「ぼかしたバストアップ」、全身2枚が実は全身になっていない
       → 各シーンに具体的な小道具・場所を追加、全身は「頭から少なくとも太もも半分まで」に緩和
       （つま先まで写す必要はない、という要望に合わせた）
     - 2回目: 7枚とも表情・向き・ポーズがほぼ同じ → シーンごとに角度・表情・ファッションを明示
     - 3回目: 7枚とも髪型が「まとめ髪」に寄ってしまった → 髪型の指示をプロンプト前半に移動し、
       シーンごとに「まとめ髪禁止／下ろした髪禁止」を動的に切り替える否定リストを追加
     - 現状: `POSE_VARIATION`（表情・顔の向き）、`HAIR_STYLE`（髪型・上げ下ろし）、
       `WEAR_FASHION` / `TONE_SETTING`（服装）の3つの辞書でシーンごとに差別化している
     - **まだ最終確認前**。次のチャットで実キーの結果を見て、狙った通り
       （髪型ミックス・表情の多様さ・服装の違い）になっているか確認が必要
  4. コミット・GitHub へ push 済み（`205df6d`）

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
- 人物シーン生成は `apps/worker/worker/scene_gen.py` に集約。主な構成:
  - `PERSONA_LOOK` — persona名 → 見た目の説明文（参照顔生成用）
  - `WEAR_SETTING` / `WEAR_FASHION` — 着用4枚の場所・小道具・服装
  - `TONE_SETTING` — 全身トーン（オフィス/休日/エレガント/リラックス）の服装
  - `POSE_VARIATION` — シーンごとの顔の向き・表情
  - `HAIR_STYLE` / `HAIR_NEGATIVE_BY_STATE` — シーンごとの髪型（上げ/下げ/ハーフ）と、
    それ以外の髪型を禁止する否定リストをセットで管理
  - `build_scene_prompt()` がこれらを1つのプロンプトに組み立てる。**髪型の指示は文の前半に置く**
    （プロンプトは前半の語ほど強く効く傾向があるため）
  - `id_weight`（PuLIDの顔固定強さ）は全身 0.65 / バストアップ 0.75 に下げている。
    1.0 のままだと表情もポーズも髪型も参照顔にそのまま寄ってしまう
  - ジュエリー自体は常にプロンプトと否定リストの両方で禁止（AIに描かせない方針を守るため）

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

ログイン: `ec-team` / `studio`

本物の人物シーンを試すときは `apps/web/.env.local` に:

```
FAL_KEY=fal_...
```

（キーは `key_id:key_secret` の形。fal.ai ダッシュボードの Keys ページで発行）

**注意:**
- ワーカーは Python プロセスなのでコード変更後・`FAL_KEY` 追加後は**必ず再起動**（ホットリロードなし）
- 複数のワーカーを同時に立てない（古いプロセスが残っているとジョブを横取りされて古い挙動になる）。
  疑わしいときは PowerShell で
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'worker.pipeline' }`
  で確認し、余分なものを `Stop-Process -Id <pid> -Force` してから1つだけ起動し直す
- fal.ai のチャージ直後は反映まで数分かかることがある（`403 Exhausted balance` が出ても、
  少し待って直接APIを叩き直すと解消するケースがあった）

## 未着手・今後の候補

- **最優先:** 直近のプロンプト調整（髪型ミックス・表情多様化）を実キーでもう一度確認する。
  1回で完璧になるプロンプトではないので、結果を見ながら `scene_gen.py` の
  `POSE_VARIATION` / `HAIR_STYLE` / `WEAR_FASHION` を微調整する想定
- Phase 3 残り: persona 参照写真の本番データ投入（`PresetPersona.imageKey`）
- Phase 4: インセット選び直し・枠再生成（レビュー画面の「再生成」ボタンは現状 disabled）・
  進捗磨き・「失敗した段階からリトライ」の実装・プリセット追加
- Phase 5: 画質・リトライ・14日削除・デプロイ固め
- `docs/REQUIREMENTS.md` §9「未決」の残り（コスト上限の具体値、ホスティング等）
