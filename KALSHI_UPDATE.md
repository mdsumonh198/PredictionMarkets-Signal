# Kalshi BTC/ETH 15M Update

- Primary signal source changed from Coinbase spot to Kalshi production public market data.
- BTC series: `KXBTC15M`; ETH series: `KXETH15M`.
- EARLY signal around 3 minutes before market close.
- FINAL signal around 1 minute before close, sent as a Telegram reply to EARLY when available.
- WIN/LOSS uses Kalshi's official settled `result` (`yes`/`no`), fixing the prior DOWN-result price-comparison issue.
- Signal ensemble uses Kalshi YES/NO market price, recent 1-minute Kalshi contract momentum, and public orderbook depth.
- NO TRADE is allowed when evidence is weak/mixed; it is excluded from win/loss stats.
- No Kalshi account/API key is required by this code because it only reads public endpoints.
- No order placement code is used.

Accuracy is measured from settled FINAL signals. No fixed win rate is guaranteed.
