# Ti amo Jewelry Studio

イタリアンゴールドジュエリーの EC 向けに、商品写真 3 枚から掲載用 10 枚を自動生成する社内ツール（卒業制作）。

## いまの状態

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 0 | 完成形 UI モック（見た目・画面フロー） | 完了 |
| Phase 1〜 | Next.js + Python ワーカーでの本実装 | 未着手 |

- **UI モック（ローカル）:** [docs/mockups/product-ui.html](docs/mockups/product-ui.html)
- **公開モック:** https://ti-amo-jewelry-studio.surge.sh
- **合意した要件:** [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md)
- **画面・処理の設計:** [docs/DESIGN.md](docs/DESIGN.md)
- **UI/UX・エンジニアレビュー結果:** [docs/REVIEW.md](docs/REVIEW.md)（Phase 1着手前に確認すること）

## ひとことで言うと

自社 EC 担当が、ほぼそのまま商品ページに載せられる 10 枚を、数分で揃える。

## 出力 10 枚の内訳

1. **ディテール 3 枚** — AI 人物なし。背景差し替え＋色調整のみ  
2. **着用シーン 4 枚** — オフィス／カフェ／デート／休日（部位はカテゴリで読替）  
3. **全身コーディネート 2 枚** — トーンを 2 つ選択  
4. **引き＋右下インセット 1 枚** — 雰囲気とサイズ感を 1 枚で両立  

## 技術方針（確定）

- **画面:** Next.js（App Router）＋共有社内ログイン  
- **処理:** Python ワーカー（切り抜き・合成・ZIP）  
- **人物:** 画像生成 API（初期 fal.ai Flux 系）※ジュエリーは描かせない  
- **商品:** 実物写真の切り抜き合成で実物を守る  
- **キュー / 保存:** Redis + RQ、S3 互換ストレージ  

詳細は [docs/DESIGN.md](docs/DESIGN.md) を参照。
