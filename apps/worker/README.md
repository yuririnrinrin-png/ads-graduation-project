# Ti amo Jewelry Studio — Python worker (Phase 1 stub)

Phase 1 では Web 側がダミー10枚を直接生成します。  
このディレクトリは Phase 2 以降の切り抜き・合成パイプライン用の骨組みです。

## 想定

- Redis + RQ でジョブを受ける
- 1ジョブ = 1プロセスが7段階を順実行（チェックポイント保存）
- 画像生成 API キーはここ（ワーカー）の環境変数のみ

## ローカル（Python 導入後）

```bash
cd apps/worker
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
rq worker tiamo --url redis://localhost:6379
```

`worker/pipeline.py` の `run_job` が本実装の入口です。
