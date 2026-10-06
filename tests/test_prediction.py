import unittest
from scanner.prediction import review


def snapshot():
    return dict(asset='BTC', now=780, start=0, expiry=900, target=100,
                contract_id='test-only', reference_index='BRTI', rules_url='https://example.org/rules',
                settlement='final_60_seconds_average',
                ticks=[dict(time=t, price=100+(t-660)*.01) for t in range(660,781)],
                contract_quotes={d:dict(bid=.6,ask=.62,time=780,fee_per_contract=.01) for d in ('UP','DOWN')})


class PredictionTests(unittest.TestCase):
    def test_candidate_is_never_live_authorized(self):
        r=review(snapshot())
        self.assertEqual(r['direction'],'UP')
        self.assertFalse(r['trade_authorized'])
        self.assertAlmostEqual(r['break_even_probability'],.63)

    def test_down(self):
        s=snapshot()
        for t in s['ticks']: t['price']=200-t['price']
        self.assertEqual(review(s)['direction'],'DOWN')

    def test_rising_below_target_is_not_up_signal(self):
        s=snapshot(); s['target']=110
        self.assertIsNone(review(s)['direction'])

    def test_expiry_and_averaging_minute_excluded(self):
        for now in (779,840,900):
            s=snapshot(); s['now']=now
            self.assertIsNone(review(s)['direction'])

    def test_missing_reference_ticks(self):
        s=snapshot(); s['ticks']=s['ticks'][:-5]
        self.assertIsNone(review(s)['direction'])

    def test_future_and_duplicate_rejected(self):
        for time in (781,779):
            s=snapshot(); s['ticks'][-1]['time']=time
            with self.assertRaises(ValueError): review(s)

    def test_contract_quotes_must_be_fresh(self):
        s=snapshot(); s['contract_quotes']['UP']['time']=770
        self.assertIn('Contract quote stale or from future',review(s)['reasons'])

    def test_invalid_price_and_unknown_product_rejected(self):
        for field,value in [('asset','SOL'),('target',float('nan')),('settlement','spot_close')]:
            s=snapshot(); s[field]=value
            with self.assertRaises(ValueError): review(s)
