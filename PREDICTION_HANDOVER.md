# Prediction bot handover — 6 October 2026

Implemented and verified with 120 automated tests total:

- Separate BTC/ETH prediction paper runner (spot runner unchanged).
- Public Kalshi contract discovery, exact rule-template and timestamp validation, normalized rule hashes.
- Live CF Benchmarks reference adapters through entitled Kalshi WebSocket or direct licensed CF WebSocket. Production host and signing format follow official documentation.
- BTC BRTI / ETH ETHUSD_RTI separation, stale/future/gapped tick rejection, reconnect clearing and 120-second warm-up.
- Final-two-minute decision window, deadline after 30 seconds of retry, missed-window audit records.
- Trend plus buffered reference-average target-side comparison, contract ask/spread/fee checks.
- SQLite contract/chat deduplication, ambiguous-send reservations, pre-send freshness/timing checks.
- Clearly labelled paper Telegram candidates and official-settlement result replies. No automatic real orders or calibrated profitability claims.
- Public API BTC/ETH mapping check saved in PREDICTION_PUBLIC_DATA_CHECK.json. This is a data-schema check, not an authenticated-stream or live-strategy validation.

## Local commands

```
python -m pip install -r requirements-prediction.txt
python -m unittest discover -q
python -m scanner.prediction_bot --config prediction-config.kalshi-paper.json --check
python -m scanner.prediction_bot --config prediction-config.kalshi-paper.json
```

The final two commands require private environment credentials. Add --notify only when a dedicated paper Telegram token/chat has been configured. The check does not send messages.

## VPS commands after GitHub pull

Do not replace crypto-scanner with prediction_bot. Install a separate service after private setup:

```
cd '/root/Crypto-Signal-Bot.'
git pull --ff-only
.venv/bin/python -m pip install -r requirements-prediction.txt
.venv/bin/python -m unittest discover -q
install -d -m 700 /root/.config/crypto-prediction
cp prediction-config.kalshi-paper.json /root/.config/crypto-prediction/config.json
cp prediction.env.example /root/.config/crypto-prediction/prediction.env
chmod 600 /root/.config/crypto-prediction/config.json /root/.config/crypto-prediction/prediction.env
```

Do not overwrite an existing private config/env on later updates. Edit the private environment file with the account API key ID and PEM path (or licensed CF credentials), and dedicated paper Telegram credentials; store PEM privately with mode 600. Confirm permitted reference-data use and entitlements. Verify the preset's estimated fees against the client's actual fee schedule and the Coinbase/Kalshi contract mapping.

The CLI uses process environment. To run the check in a terminal, export those credentials privately in that shell, then run the --check command above; do not paste them into chat or GitHub. The service reads the private EnvironmentFile automatically.

Only after successful feed readiness and verified mappings:

```
cp crypto-prediction.service.example /etc/systemd/system/crypto-prediction.service
systemctl daemon-reload
systemctl enable --now crypto-prediction
systemctl status crypto-prediction --no-pager -l
journalctl -u crypto-prediction --since '5 minutes ago' --no-pager
```

Check for both reference streams, active contracts, fresh books and paper settlement replies over multiple contracts. A passed test suite does not mean the live API/account is working. No VPS commands or Telegram messages have been executed by the developer in this update.

## Remaining external inputs / research

Authorized reference credentials/entitlement; client's Coinbase contract matching; verified fees; forward paper evidence and chronological held-out strategy calibration. There is no credible win guarantee. An uncalibrated direction hypothesis remains paper-only even with working APIs.

See PREDICTION_SETUP.md for precise limits. Upload code/docs only; exclude private keys, env files, data and client-account credentials.
# Superseded for the Coinbase-only request

The instructions below describe legacy Kalshi paper research. For the user's current Coinbase-only request, use COINBASE_PREDICTION_SETUP.md. The runner now defaults to Coinbase and blocks unverified prediction feeds. To deliberately run the older research commands, add `--provider kalshi`; they are not Coinbase prediction integration. Do not install the older service for the current request.
