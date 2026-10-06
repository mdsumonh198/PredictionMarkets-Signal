"""Coinbase-only readiness check. Spot prices are not prediction reference data."""
import json
import time
from scanner.market_data.coinbase import Coinbase


class PredictionFeedUnavailable(RuntimeError):
    pass


def require_prediction_feed():
    raise PredictionFeedUnavailable(
        'Coinbase prediction contract/reference API is not yet verified. '
        'Kalshi is disabled in Coinbase mode. See COINBASE_PREDICTION_SETUP.md. '
        'Use --coinbase-prices only to check public spot data; it sends no prediction signals.')


def price_check(provider=None,clock=None):
    provider=provider or Coinbase()
    clock=clock or time.time
    report=dict(provider='Coinbase',prediction_ready=False,signals_enabled=False,
        prediction_contract_feed='UNVERIFIED',prediction_reference_feed='UNVERIFIED',
        note='These are spot order-book prices, not BRTI/ETH reference or UP/DOWN contract prices.',
        spot_prices={})
    for symbol in ('BTC-USD','ETH-USD'):
        try:
            q=provider.liquidity(symbol)
            q.validate_freshness(clock(),15)
            report['spot_prices'][symbol]=dict(status='VERIFIED_SPOT_QUOTE',bid=q.bid,ask=q.ask,
                source='Coinbase Exchange spot order book level 1',observed_at=q.observed_at,
                book_time=q.quote_time)
        except Exception:
            report['spot_prices'][symbol]=dict(status='UNAVAILABLE_OR_STALE')
    return report


def main():
    print(json.dumps(price_check(),indent=2,allow_nan=False))


if __name__=='__main__': main()
