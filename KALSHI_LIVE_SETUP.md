# Kalshi Live Auto Trade

Required API scopes: Read all data + Trade. Transfers and Accept block trades are not needed.

Recommended VPS setup:
1. Save the downloaded Kalshi private PEM as `/root/PredictionMarkets-Signal/kalshi-private-key.pem` and `chmod 600` it.
2. Add `KALSHI_API_KEY_ID=...`, `KALSHI_PRIVATE_KEY_PATH=/root/PredictionMarkets-Signal/kalshi-private-key.pem` to `.env`.
3. First keep `KALSHI_LIVE_TRADING=NO`. Authentication can be checked without orders.
4. When ready for real money, set `KALSHI_LIVE_TRADING=YES`, select Live Auto Trade in dashboard, choose a small fixed amount, then enable Auto Execution.

Logic: EARLY UP enters YES; EARLY DOWN enters NO. FINAL same direction holds to settlement. FINAL opposite or NO TRADE closes the open position using a reduce-only IOC order.
