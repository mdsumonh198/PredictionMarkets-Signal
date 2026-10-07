# Browser control + auto-trade architecture

Dashboard: http://SERVER_IP:8787 (protect with firewall/VPN/reverse proxy; Bearer token required).
Modes: Signal Only, Paper Auto Trade, Live Auto Trade.

Live mode is intentionally locked because, as of this build, Coinbase public documentation confirms browser/app Prediction Market Buy/Sell and early selling, but the project has not verified an official retail Prediction Market order-placement API endpoint. The bot must not guess an endpoint or route Prediction Market orders through the Advanced Trade spot API.

Intended execution after official endpoint verification:
- EARLY ~T-3m: enter fixed USD amount on the signaled outcome.
- FINAL ~T-1m: if same direction, keep; if opposite or NO TRADE, sell early/close.
- Official settlement: record result and realized PnL.
- Never request withdrawal/transfer permission.
