#!/usr/bin/env bash
# 取り込み済みのデータから、特徴量・モデル・AI 資産・配信物を作り直す。
# 取得はしない(取得は scripts/ingest/* が済ませている)。
#
#     bash scripts/rebuild_all.sh
set -euo pipefail

PY=.venv/Scripts/python.exe
[ -x "$PY" ] || PY=.venv/bin/python

echo "=== 1/5 検証 ==="
"$PY" scripts/validate/validate_dataset.py

echo "=== 2/5 特徴量 ==="
"$PY" scripts/ml/build_features.py

echo "=== 3/5 学習 ==="
"$PY" scripts/ml/train_autoencoder.py

echo "=== 4/5 異常度(交差適合)と AI 資産 ==="
"$PY" scripts/ml/build_anomaly.py
"$PY" scripts/ml/build_ai_assets.py

echo "=== 5/5 配信物 ==="
"$PY" scripts/export/build_web_assets.py

echo "=== 完了 ==="
