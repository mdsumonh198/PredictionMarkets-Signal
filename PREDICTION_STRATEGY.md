# BTC / ETH 15-minute prediction research

The offline evaluator now also has a separate streaming PAPER runner in scanner.prediction_bot. See PREDICTION_SETUP.md for its setup, account entitlements and limitations. It is not enabled or verified live on the VPS. The existing `scanner scan` command still runs the spot strategy. Do not restart that command expecting prediction signals.

## Research hypothesis

Evaluate each verified 900-second contract at expiry minus 120 seconds (e.g. 10:13 for 10:15 expiry). Use only BTC and ETH. Stop new evaluation once the final 60-second settlement averaging window begins. Use the actual contract times, not the computer's local quarter-hour assumption.

Use fresh observations from the reference index named in that specific contract's rules. BRTI is Bitcoin; do not assign it to ETH. The ETH index and tie/rounding rules must be verified independently. A spot price cannot silently substitute for the settlement index.

Compare three 30-second median windows from the previous 90 seconds. Rising medians suggest UP; falling medians suggest DOWN. Require the newest reference price to be on the same side of the contract target with a buffer of the larger of 1 basis point or three median one-tick absolute moves. These thresholds are provisional hypotheses, not optimized parameters or calibrated win probabilities. Reject stale, missing, future, duplicate and gapped reference observations.

Read the chosen UP/DOWN contract's executable ask, bid and per-contract fees. These are dollar-denominated contract prices, not underlying BTC/ETH entry prices. Record break-even probability as ask plus fees for a $1 winning payout; include slippage and actual fee rounding when a live adapter is designed. A trend observation alone cannot establish that this cost is worth paying. No martingale, leverage or spot ATR SL/TP is part of this prototype.

The output always states RESEARCH_ONLY and trade_authorized=false. A candidate direction may be absent. Forcing a direction when observations conflict or data is missing would manufacture a signal. No Telegram message or order is sent.

## Run

`python -m scanner.prediction --snapshot path/to/verified-contract-snapshot.json`

Snapshot fields: asset (BTC/ETH), contract_id, reference_index, rules_url, start, expiry, now (Unix seconds), target, settlement (`final_60_seconds_average`), ticks (list of time/price), contract_quotes (UP and DOWN objects with bid, ask, time, fee_per_contract). All times must use the same synchronized clock. There must be continuous recent reference samples for approximately 120 seconds with gaps no longer than two seconds.

## Required before a live adapter

1. Confirm actual Coinbase/Kalshi contract identifiers, ETH reference index, target rules, equality treatment, rounding, expiry and trading cutoff.
2. Obtain authorized real-time reference data access and contract order-book access. No CF Benchmarks credentials are present here; no unofficial website scrape or fake spot fallback has been added.
3. Record reference ticks, exact target, contract quotes, executable fees, decision time and official settlement for historical and forward paper research. Compare simple target-side, momentum and combined baselines on chronological held-out periods. Measure net expected value, drawdown, calibration, missing-data rate and entry latency. Do not choose parameters based on the test period.
4. Only a calibrated model may compare a conservative win-probability estimate with ask plus fees/slippage. No estimated probability is invented by this module.
5. The separate PAPER runner now implements a persistent contract scheduler, a decision window beginning at minus 120 seconds, durable Telegram reservations, reconnect warm-up and official settlement replies. Verify it with authorized live data before using paper messages with the client. Track resolution separately from an early contract sale; actual early exits are not implemented.

## Sources

- https://help.coinbase.com/en/coinbase/trading-and-funding/prediction-markets/intro
- https://docs.cfbenchmarks.com/api/websocket/intro/
- https://docs.cfbenchmarks.com/api/websocket/value/

Coinbase documents contract-specific rules and a final 60-second reference average. CF Benchmarks documents licensed WebSocket access. Neither source proves profitability of this proposed strategy.
