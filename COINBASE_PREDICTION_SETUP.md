# Coinbase-only prediction integration status — 6 October 2026

Coinbase is now the prediction runner's default provider. It does not require a Kalshi account or silently call Kalshi. There is no verified Coinbase-only live prediction integration yet.

Verification: 124 automated tests passed. A live read-only public price check returned fresh BTC-USD and ETH-USD spot book quotes. No prediction target, contract quote, reference feed, authenticated Coinbase prediction API or Telegram delivery was verified by that check.

## What is available

Coinbase's documented public Exchange APIs provide BTC-USD and ETH-USD spot order books. Run:

```
python -m scanner.prediction_bot --coinbase-prices
```

This checks fresh Coinbase spot quotes and emits a JSON readiness report. It requires no Kalshi credentials and sends no Telegram messages or orders. Its prediction_ready and signals_enabled fields remain false, even when both spot feeds work. Spot quotes cannot substitute for CF reference prices, contract targets or the cent-denominated UP/DOWN contract order book.

## What blocks the requested live bot

The official Coinbase developer documentation index, Advanced Trade product documentation and prediction-market help pages were checked. No supported public Coinbase prediction API for the requested contract data was located. This does not establish that a private/partner API is unavailable. An ordinary Advanced Trade API key is not proof of prediction-market access.

For a Coinbase-only bot we still need documented, permitted access to:

1. BTC/ETH 15-minute prediction contract IDs, actual start/expiry times, target and contract rules.
2. Coinbase-displayed reference-index values / 60-second average with source timestamps, including the distinct ETH index.
3. Executable Coinbase UP/OVER and DOWN/UNDER bid/ask, available size and customer fees.
4. Official final settlement and any provisional/corrected-result indicators.

Until verified, `python -m scanner.prediction_bot --provider coinbase` exits before opening a feed, reading private keys, creating a database or sending Telegram. No endpoint has been guessed, and no Coinbase session token, cookies or private website API has been embedded.

## Request to Coinbase developer support

The user/client can send the following. It has not been sent by the developer:

> We are building a read-only Telegram signal and paper-testing application for Coinbase's BTC and ETH 15-minute prediction markets. We need supported API access to contract IDs, start/expiry timestamps, price-to-beat, settlement rules, timestamped reference-index/60-second-average data, executable UP/OVER and DOWN/UNDER quotes, fees, and final settlement. Does Coinbase offer an official public or partner API for these products? Please provide the endpoint documentation, authentication and eligibility requirements, streaming capabilities, rate limits, pricing and data-use permissions. We do not need automatic order placement at this stage.

Use Coinbase's official help/developer support. Share documentation/access requirements with the developer; do not share passwords, cookies, private keys or tokens in chat.

## Existing service warning

Do not run the previous Kalshi setup instructions for a Coinbase-only deployment. The legacy Kalshi research runner is preserved only behind explicit `--provider kalshi`; it has not been converted into a Coinbase prediction feed. The existing spot crypto-scanner remains a separate bot. No VPS deployment was performed.

## Sources checked

- https://docs.cdp.coinbase.com/llms.txt
- https://docs.cdp.coinbase.com/_llms/api-reference.md
- https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/public/list-public-products
- https://docs.cdp.coinbase.com/exchange/websocket-feed/channels
- https://help.coinbase.com/en/coinbase/trading-and-funding/prediction-markets/intro

Coinbase's help page identifies the contract's reference average as the settlement source rather than ordinary Coinbase spot price. No profitability claim follows from a working spot feed.
