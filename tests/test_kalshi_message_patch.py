import unittest
from unittest.mock import patch
from scanner.btc_eth_15m_signal import format_signal, evaluate

class API:
    def orderbook(self,ticker): return {'yes_dollars':[['0.70','100']], 'no_dollars':[['0.30','20']]}
    def candles(self,*args,**kwargs): return []

class TestKalshiMessagePatch(unittest.TestCase):
    def test_target_current_distance_order(self):
        s={'coin':'BTC','direction':'UP','confidence':82.9,'target':85758.97,'spot':85800.0,
           'distance_pct':(85800-85758.97)/85758.97*100,'yes_mid':.815,'no_mid':.185,
           'seconds_left':180,'volume':10,'ticker':'T','reasons':['ok']}
        t=format_signal(s,'EARLY')
        self.assertLess(t.index('Target Price:'),t.index('Current BTC Price:'))
        self.assertLess(t.index('Current BTC Price:'),t.index('Above Target:'))
        self.assertIn('Above Target: +0.048%',t)
        self.assertNotIn('Above Target: +$',t)

    @patch('scanner.btc_eth_15m_signal.current_spot', return_value=90.0)
    def test_evaluate_reads_floor_strike(self,_):
        m={'ticker':'T','close_time':'2099-01-01T00:00:00Z','open_time':'2026-01-01T00:00:00Z',
           'floor_strike':100,'yes_bid_dollars':'0.60','yes_ask_dollars':'0.62','volume':12}
        s=evaluate(API(),'BTC',m,0)
        self.assertEqual(s['target'],100.0)
        self.assertEqual(s['spot'],90.0)
        self.assertAlmostEqual(s['distance_pct'],-10.0)
        self.assertIn('Below Target: -10.000%',format_signal(s,'FINAL'))

if __name__=='__main__': unittest.main()
