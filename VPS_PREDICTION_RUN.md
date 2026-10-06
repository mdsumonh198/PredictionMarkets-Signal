# BTC / ETH prediction paper bot — VPS setup

This is a separate read-only paper bot. It monitors the actual 900-second contract interval continuously. Starting at minute 13, it reviews live reference momentum and the contract target once per second. It sends at most one verified UP/DOWN candidate per contract. Inconclusive reviews retry until minute 14; new entries are then blocked during the final settlement-averaging minute. Official settled results reply to the original candidate. It does not promise a signal or a win every interval.

Public Kalshi contract discovery needs no key. Official live BRTI / ETHUSD_RTI streaming needs either Kalshi authenticated access with the required feed availability, or licensed CF Benchmarks credentials. A public market reference-price field alone does not supply continuous reference ticks. Coinbase spot is never substituted for this feed. Kalshi quotes and estimated fees are labelled; the client's Coinbase execution quotes and fees are not verified.

## First installation

Upload this folder to GitHub, then on the VPS:

```bash
cd /root/Crypto-Signal-Bot.
git pull --ff-only
bash deploy-prediction.sh
```

The first run creates private templates and stops. Edit:

```bash
nano /root/.config/crypto-prediction/prediction.env
nano /root/.config/crypto-prediction/config.json
```

Fill PREDICTION_TELEGRAM_TOKEN and PREDICTION_TELEGRAM_CHAT_ID using a paper testing chat. For Kalshi reference access, fill KALSHI_API_KEY_ID and place the provider's private key at KALSHI_PRIVATE_KEY_PATH. Alternatively fill CFB_USERNAME and CFB_API_KEY. Never paste credentials into chat or commit them. Verify config contract rules against the client's Coinbase contracts and replace example fee assumptions with verified costs.

Run `bash deploy-prediction.sh` again. It installs prediction dependencies, runs tests, checks both current public contracts, then checks both reference streams for up to 130 seconds. No Telegram is sent by either readiness check. If a check fails, the script exits before starting or changing the prediction service. Missing access is not bypassed with spot prices. The existing crypto-scanner spot service is untouched.

## Check after startup

```bash
sudo systemctl status crypto-prediction --no-pager -l
sudo journalctl -u crypto-prediction --since "5 minutes ago" --no-pager
```

The enabled systemd service runs after closing the console and starts on VPS reboot. No server reboot is needed. An unavailable reference feed prevents signals and is reported in logs. Warm-up needs 120 seconds after startup or reconnect. Keep this in paper mode; strategy profit and live authenticated streaming have not been validated here.

## Timing example

A contract from 10:00 to 10:15 is monitored from the start. Candidate review starts at 10:13. A valid candidate is sent immediately after verification; the bot does not wait for 10:15. If no candidate qualifies by 10:14, no late entry is sent. Confirmed settlement is checked every 15 seconds after expiry and then posted as a reply.

Official feed documentation: https://docs.kalshi.com/websockets/cfbenchmarks-value
