# Live Auto Trade Status

- Dashboard control UI: ready.
- Signal-only mode: ready.
- Paper auto-trade mode: ready.
- Coinbase API authentication/read check: included (`python -m scanner.coinbase_prediction_access --env .env`).
- Coinbase Prediction Markets real Buy/Sell: **safety locked**.

The Coinbase Advanced Trade order API is for Advanced Trade products. This project does not map a Kalshi prediction ticker to a Coinbase Advanced Trade product or guess an undocumented Coinbase Financial Markets order endpoint. Authentication success must never be treated as proof of Prediction Markets order capability.

When Coinbase publishes/provides an authorized Prediction Markets trading API for the account, implement that documented endpoint in `scanner/execution/coinbase.py`, add preview/read tests, then explicitly unlock live mode.
