#!/usr/bin/env bash
set -e
cd /mnt/e/opencell
source .venv-wsl/bin/activate
for id in thattai2001-gamma1-mrna-degradation-rate thattai2001-k2-translation-rate thattai2001-gamma2-protein-degradation-rate; do
  echo "====== $id ======"
  printf "y\ny\ny\ny\nSrinivas Drona\n" | NO_COLOR=1 python tools/review_param.py review data/params/micro_model_thattai2001.yaml "$id" 2>&1 | tail -2
done
