# BTC/ETH 15M Telegram Signal Bot

Public Coinbase spot data only. Monitors BTC-USD and ETH-USD throughout each 15-minute window. It evaluates once during the final two minutes (after 13 minutes have elapsed) and sends at most one Telegram message per asset/window. No orders are placed.

## Required .env
TELEGRAM_TOKEN=...
TELEGRAM_CHAT_ID=...

## First deploy
cd /root/Crypto-Signal-Bot.
git pull origin main
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo cp crypto-btc-eth-15m.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crypto-btc-eth-15m
sudo systemctl status crypto-btc-eth-15m --no-pager

## Update after GitHub push
cd /root/Crypto-Signal-Bot.
git pull origin main
sudo systemctl restart crypto-btc-eth-15m
sudo systemctl status crypto-btc-eth-15m --no-pager

## Live logs
journalctl -u crypto-btc-eth-15m -f
