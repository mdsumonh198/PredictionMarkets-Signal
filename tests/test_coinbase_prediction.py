import contextlib
import io
import unittest
from unittest.mock import Mock,patch
from scanner.coinbase_prediction import price_check,require_prediction_feed,PredictionFeedUnavailable


class CoinbasePredictionTests(unittest.TestCase):
    def test_live_spot_does_not_authorize_prediction(self):
        q=Mock(bid=100,ask=101,observed_at=1000,quote_time=999)
        api=Mock(); api.liquidity.return_value=q
        r=price_check(api,lambda:1001)
        self.assertFalse(r['prediction_ready'])
        self.assertFalse(r['signals_enabled'])
        self.assertEqual(set(r['spot_prices']),{'BTC-USD','ETH-USD'})
        self.assertEqual(q.validate_freshness.call_count,2)

    def test_stale_spot_does_not_look_valid(self):
        api=Mock(); api.liquidity.return_value.validate_freshness.side_effect=ValueError('old')
        r=price_check(api,lambda:1001)
        self.assertEqual(r['spot_prices']['BTC-USD']['status'],'UNAVAILABLE_OR_STALE')

    def test_missing_prediction_feed_fails_explicitly(self):
        with self.assertRaises(PredictionFeedUnavailable): require_prediction_feed()

    def test_default_runner_never_opens_kalshi_or_sends_telegram(self):
        from scanner.prediction_bot import main
        with patch('sys.argv',['prediction_bot','--notify']),patch('scanner.prediction_bot.Kalshi') as api,patch('scanner.prediction_bot.Telegram') as telegram,contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as exc: main()
            self.assertEqual(exc.exception.code,2)
            api.assert_not_called(); telegram.assert_not_called()
