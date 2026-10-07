import unittest
from unittest.mock import MagicMock, patch
from scanner.coinbase_prediction_access import check

class AccessCheckTests(unittest.TestCase):
    @patch('scanner.coinbase_prediction_access.load_env')
    def test_missing_creds(self, env):
        env.return_value = {}
        with patch.dict('os.environ', {}, clear=True):
            r = check('.env')
        self.assertFalse(r['authentication'])
        self.assertFalse(r['prediction_market_order_api'])
        self.assertFalse(r['real_order_placed'])

    @patch('scanner.coinbase_prediction_access.load_env')
    def test_auth_does_not_unlock_prediction(self, env):
        env.return_value = {'COINBASE_API_KEY':'k','COINBASE_PRIVATE_KEY':'s'}
        fake = MagicMock(); fake.get_accounts.return_value = {'accounts':[]}
        import sys, types
        coinbase = types.ModuleType('coinbase'); rest = types.ModuleType('coinbase.rest'); rest.RESTClient=lambda **kw: fake
        with patch.dict(sys.modules, {'coinbase':coinbase,'coinbase.rest':rest}):
            r = check('.env')
        self.assertTrue(r['authentication'])
        self.assertTrue(r['read_access'])
        self.assertFalse(r['prediction_market_order_api'])
        self.assertFalse(r['real_order_placed'])

if __name__=='__main__': unittest.main()
