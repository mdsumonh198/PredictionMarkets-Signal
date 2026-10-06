# Current handover

Use VPS_PREDICTION_RUN.md and deploy-prediction.sh for the current BTC/ETH paper deployment. Public contract checks need no key; live official reference checks need authorized credentials. 127 automated tests pass; current BTC/ETH public contracts were verified. Credentialed streaming and end-to-end Telegram remain unverified.

# BTC / ETH prediction paper bot: setup and verification

The separate runner, read-only market discovery, reference feed adapters, two-minute scheduler, persistent paper review storage, Telegram paper messages and official-settlement replies are implemented. No automatic order placement or real-money mode exists. No live end-to-end validation has been performed without credentials and verified contract mappings. The strategy remains uncalibrated.

## Data access

The Kalshi CF Benchmarks WebSocket feed is authenticated. Kalshi also documents entitled REST passthrough access without a separate CF key. Entitlement and permission to use data in a client Telegram service must be confirmed with the provider. This is not a promise of free access. Alternatively provide licensed CFB_USERNAME/CFB_API_KEY directly. BTC subscribes to BRTI, ETH to ETHUSD_RTI, but each contract's own rules must confirm its index.

The read-only REST adapter uses Kalshi public markets and dollar-precision YES/NO order books. YES bid implies NO ask = 1 - YES bid, and conversely. These prices are Kalshi observed quotes, not verified Coinbase executable quotes. Coinbase customer fees/quotes may differ. The paper model assumes one contract, a fixed configured fee allowance and ask fill; it does not claim actual fills. It rejects books taking over two seconds, but REST has no exchange quote timestamp so source freshness cannot be independently proven.

## Configure before starting

`prediction-config.kalshi-paper.json` is a supplied paper preset using publicly inspected KXBTC15M/KXETH15M series. Their rules, greater-or-equal strike, 900-second interval and target mapping were checked through the official public REST API; evidence is in PREDICTION_PUBLIC_DATA_CHECK.json. It is not proof of an active feed or of the client's exact Coinbase contract mapping. Example fees remain estimates. Use this preset for Kalshi-data paper evaluation, or independently verify the Coinbase instrument first. BTC and ETH have distinct real-time indices.

1. Install `python -m pip install -r requirements-prediction.txt` in the VPS virtual environment.
2. Copy `prediction-config.example.json` to a private config path. Obtain the actual BTC and ETH 15-minute series identifiers from the client's contract Full Rules. Do not guess them or substitute a crypto-leader/spot/futures market.
3. Inspect each series using `python -m scanner.prediction_bot --provider kalshi --inspect-series ACTUAL_SERIES`. Compare its rules, target, expiry, YES/NO labels and settlement with the Coinbase contract. The command prints a rules SHA-256 for verification. Only the two explicitly parsed contract timestamps are replaced by placeholders for the hash; the actual dates are independently checked against expiry and the 900-second interval for each new contract. Changes to the remaining rule text require reapproval.
4. This initial adapter supports only verified YES=UP, equal=UP, final-60-second-average contracts with target in floor_strike, expiry in close_time and strike_type=greater_or_equal. Other schemas are deliberately blocked pending an explicit adapter. Verify that expiry is exactly the end of the 900-second reference interval, not an early trading cutoff. The interval start is derived from that verified expiry; open_time is not assumed to be interval start.
5. Replace example fee_per_contract=0.02 with the client's verified one-contract fee/slippage allowance. max_contract_ask=0.75 and spread=0.04 are provisional paper filters, not profitable settings. Required break-even probability is ask plus the allowance; the bot does not estimate or claim a calibrated win probability.
6. Save credentials privately using prediction.env.example. The CLI reads process environment, not .env automatically. With systemd, EnvironmentFile loads them. Use a dedicated paper Telegram chat. Never upload credentials or PEM files to GitHub.

## Paper runner and VPS

Start without Telegram first with `python -m scanner.prediction_bot --provider kalshi --config /path/to/config.json`. An invalid/incomplete setup exits with a useful error. Allow 120 seconds of continuous reference history to warm up. Logs show reviews/inconclusive data; no forced UP/DOWN messages are generated. Add --notify only for explicitly labelled paper candidates and replies. It polls for candidate decisions from expiry minus 120 through minus 60 seconds, tolerating short data delays, and records at most one valid candidate per contract and chat; inconclusive reviews retry. No initial catch-up trade at expiry is sent. Contract discovery refreshes every 15 seconds; official settlement checks every 15 seconds. Reference disconnect clears uncertain tick history and waits for warm-up again.

Use `python -m scanner.prediction_bot --provider kalshi --config prediction-config.kalshi-paper.json --check` after privately supplying credentials. It verifies continuous BTC/ETH reference streams for up to 130 seconds and never sends Telegram. Missing readiness exits unsuccessfully. The normal runner logs feed health once a minute and stores a missed-window audit row when reference data could not be verified by the entry deadline. Tests use mocks; the credentialed stream check has not yet been run here.

`crypto-prediction.service.example` is a separate optional service template for the existing VPS path. Correct paths, credentials and config before installing it as `/etc/systemd/system/crypto-prediction.service`. Then run `sudo systemctl daemon-reload` and `sudo systemctl enable --now crypto-prediction`. Verify with `sudo systemctl status crypto-prediction --no-pager -l` and `sudo journalctl -u crypto-prediction --since "5 minutes ago" --no-pager`. This does not replace or reconfigure crypto-scanner. No service was installed or started by this update.

## Tracking and delivery limits

Paper candidate messages include asset, UP/DOWN, target, trailing average, Kalshi contract ask and expiry. Settlement replies use the exchange's final yes/no result, never local estimated average; provisional/unknown results wait. SQLite uniquely reserves each contract/chat before sending. An ambiguous Telegram send is not automatically retried, including result replies. A crash between send and recording its returned message ID can leave an uncertain delivery without a reply; inspect the database/logs rather than retrying blindly. Inconclusive reviews are retried; unmet entry deadlines stay in the database and logs and do not spam the client.

No guarantee of a signal every contract or of wins. Missing reference entitlement, changed rules or unavailable contracts prevent candidates. Persistent records support audit, but full raw tick history, account-specific execution simulation, calibration and chronological out-of-sample profitability evaluation remain future research, not completed validation. Keep this in paper mode.

## Official documentation

- https://docs.kalshi.com/websockets/cfbenchmarks-value
- https://docs.kalshi.com/cfbenchmarks/rest-passthrough
- https://docs.kalshi.com/getting_started/quick_start_authenticated_requests
- https://docs.kalshi.com/api-reference/market/get-market-orderbook
- https://docs.cfbenchmarks.com/api/websocket/intro/

Direct CF licensing is not the only potential route: appropriately entitled Kalshi access may provide the reference data. Coinbase login by itself is not a Kalshi API key.
# Current provider requirement: Coinbase only

This page is legacy Kalshi research setup. Coinbase-only status and next steps are in COINBASE_PREDICTION_SETUP.md. Earlier runner commands on this page now require explicit `--provider kalshi`; no automatic Kalshi fallback exists. Coinbase spot prices alone do not enable prediction signals.
