#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python scripts/ml_extract.py
python scripts/ml_train.py
python scripts/ml_store.py
