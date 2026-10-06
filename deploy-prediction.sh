#!/usr/bin/env bash
# Run from the repository on Ubuntu as root. Never downloads account keys.
set -euo pipefail
cd /root/Crypto-Signal-Bot.
private_dir=/root/.config/crypto-prediction
if [[ ! -f "$private_dir/prediction.env" ]]; then
  install -d -m 700 "$private_dir"
  install -m 600 prediction.env.example "$private_dir/prediction.env"
  install -m 600 prediction-config.kalshi-paper.json "$private_dir/config.json"
  echo "Edit $private_dir/prediction.env with reference-feed and Telegram credentials, then rerun."
  exit 1
fi
[[ -f "$private_dir/config.json" ]] || install -m 600 prediction-config.kalshi-paper.json "$private_dir/config.json"
chmod 600 "$private_dir/prediction.env" "$private_dir/config.json"
.venv/bin/python -m pip install -r requirements-prediction.txt
.venv/bin/python -B -m unittest discover -q
# This private file is shell KEY=value format; quote values containing spaces.
set -a
source "$private_dir/prediction.env"
set +a
: "${PREDICTION_TELEGRAM_TOKEN:?Set the prediction Telegram token privately}"
: "${PREDICTION_TELEGRAM_CHAT_ID:?Set the prediction Telegram chat ID privately}"
.venv/bin/python -m scanner.prediction_bot --provider kalshi --config "$private_dir/config.json" --public-check
.venv/bin/python -m scanner.prediction_bot --provider kalshi --config "$private_dir/config.json" --check
# Only install/restart after both checks pass. The original spot service is untouched.
install -m 644 crypto-prediction.service.example /etc/systemd/system/crypto-prediction.service
systemctl daemon-reload
systemctl enable crypto-prediction
systemctl restart crypto-prediction
systemctl status crypto-prediction --no-pager -l
