import json
import base64
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scanner.prediction_bot import PaperBot, contract, settings
from scanner.prediction_feeds import Kalshi, ReferenceFeed, rules_hash
from tests.test_prediction import snapshot


def market():
    return dict(ticker='TEST-BTC',market_type='binary',status='active',rules_primary="If the simple average of the sixty seconds of CF Benchmarks' BRTI before 7:15 PM EST on Dec 31, 1969 is at least the simple average of the sixty seconds of CF Benchmarks' BRTI before 7:00 PM EST on December 31, 1969, then the market resolves to Yes.",
                rules_secondary='',strike_type='greater_or_equal',floor_strike=100,
                close_time='1970-01-01T00:15:00Z')


def config():
    a=dict(series='TEST',rules_sha256=rules_hash(market()),rules_verified=True,
           reference_index='BRTI',yes_direction='UP',tie='UP',expiry_field='close_time',
           target_field='floor_strike',rules_url='https://example.org/rules',fee_per_contract=.01)
    return dict(mode='paper',max_contract_ask=.75,max_contract_spread=.04,
                assets=dict(BTC=a,ETH=dict(a,reference_index='ETHUSD_RTI')))


class RuntimeTests(unittest.TestCase):
    def bot(self,db=':memory:',notifier=None):
        api=Mock(); api.quotes.return_value=snapshot()['contract_quotes']
        feed=Mock(); feed.snapshot.return_value=snapshot()['ticks']
        return PaperBot(config(),api,feed,db,notifier)

    def process(self,b,now=780):
        b.process(market(),config()['assets']['BTC'],'BTC',clock=lambda:now)

    def test_persistent_review_dedup_across_restart(self):
        with tempfile.TemporaryDirectory() as d:
            path=str(Path(d)/'test.sqlite')
            b=self.bot(path); self.process(b); b.db.close()
            b=self.bot(path); self.process(b)
            b.api.quotes.assert_not_called()
            self.assertEqual(b.db.execute('SELECT COUNT(*) FROM prediction_reviews').fetchone()[0],1)
            b.db.close()

    def test_paper_message_then_official_reply(self):
        n=Mock(chat_id='test'); n.send_text.return_value=43
        b=self.bot(notifier=n); self.process(b)
        self.assertIn('PAPER',n.send_text.call_args.args[0])
        b.api.market.return_value=dict(status='settled',result='yes',is_provisional=False)
        b.results(901)
        self.assertEqual(n.send_text.call_args.kwargs['reply_to_message_id'],43)
        self.assertIn('Correct direction',n.send_text.call_args.args[0])
        b.results(902); self.assertEqual(n.send_text.call_count,2)
        b.db.close()

    def test_ambiguous_send_not_retried(self):
        n=Mock(chat_id='test'); n.send_text.side_effect=RuntimeError('uncertain')
        b=self.bot(notifier=n)
        with self.assertRaises(RuntimeError): self.process(b)
        self.process(b); self.assertEqual(n.send_text.call_count,1)
        b.db.close()

    def test_provisional_result_waits(self):
        b=self.bot(); self.process(b)
        b.api.market.return_value=dict(status='settled',result='yes',is_provisional=True)
        b.results(901)
        self.assertIsNone(b.db.execute('SELECT outcome FROM prediction_reviews').fetchone()[0])
        b.db.close()

    def test_wrong_rules_and_equality_block(self):
        for changes in (dict(rules_primary='changed'),dict(strike_type='greater')):
            m=market(); m.update(changes)
            with self.assertRaises(ValueError): contract(m,config()['assets']['BTC'],'BTC')

    def test_schedule_does_not_enter_before_two_minutes_or_late(self):
        for now in (779,840,900):
            b=self.bot(); self.process(b,now)
            b.api.quotes.assert_not_called(); b.db.close()

    def test_expensive_contract_suppresses_candidate(self):
        n=Mock(chat_id='test'); b=self.bot(notifier=n)
        b.api.quotes.return_value['UP']['ask']=.9
        self.process(b); n.send_text.assert_not_called(); b.db.close()

    def test_stale_at_send_blocked(self):
        n=Mock(chat_id='test'); b=self.bot(notifier=n)
        clock=Mock(side_effect=[780,780,783])
        b.process(market(),config()['assets']['BTC'],'BTC',clock=clock)
        n.send_text.assert_not_called()
        self.assertEqual(b.db.execute('SELECT status FROM prediction_reviews').fetchone()[0],'blocked_stale')
        b.db.close()

    def test_example_config_fails_closed(self):
        with self.assertRaises(ValueError): settings('prediction-config.example.json')

    def test_reference_wrapper_source_timestamp_and_duplicates(self):
        f=ReferenceFeed()
        frame=dict(type='cfbenchmarks_value',msg=dict(data=json.dumps(dict(type='value',id='BRTI',time=1000000,value='100'))))
        f.ingest(frame,1001); f.ingest(frame,1001)
        self.assertEqual(len(f.snapshot('BRTI')),1)
        with self.assertRaises(ValueError): f.ingest(frame,1003)

    def test_repeat_of_old_value_rejected(self):
        with self.assertRaises(ValueError):
            ReferenceFeed().ingest(dict(type='value',id='BRTI',time=1000000,value='100',repeatOfPreviousValue=True),1001)

    def test_orderbook_complement_and_latency(self):
        a=Kalshi()
        data=dict(orderbook_fp=dict(yes_dollars=[['0.5','2'],['0.6','1']],no_dollars=[['0.38','3']]))
        with patch.object(a,'get',return_value=data), patch('scanner.prediction_feeds.time.time',side_effect=[780,781]):
            q=a.quotes('TEST',.01)
        self.assertAlmostEqual(q['UP']['ask'],.62)
        self.assertAlmostEqual(q['DOWN']['ask'],.4)
        with patch.object(a,'get',return_value=data), patch('scanner.prediction_feeds.time.time',side_effect=[780,783]):
            with self.assertRaises(ValueError): a.quotes('TEST',.01)

    def test_empty_book_blocks(self):
        a=Kalshi()
        with patch.object(a,'get',return_value=dict(orderbook_fp=dict(yes_dollars=[],no_dollars=[]))):
            with self.assertRaises(ValueError): a.quotes('TEST',.01)

    def test_new_contract_time_keeps_rule_hash_but_invalid_interval_blocks(self):
        m=market(); a=config()['assets']['BTC']
        m['rules_primary']=m['rules_primary'].replace('7:15 PM','7:30 PM').replace('7:00 PM','7:15 PM')
        self.assertEqual(rules_hash(m),a['rules_sha256'])
        with self.assertRaises(ValueError): contract(m,a,'BTC')
        m['close_time']='1970-01-01T00:30:00Z'
        self.assertEqual(contract(m,a,'BTC')['expiry'],1800)

    def test_feed_warmup_retries_instead_of_recording_false_review(self):
        b=self.bot(); b.feed.snapshot.return_value=[]
        with self.assertRaises(ValueError): self.process(b)
        self.assertFalse(b.exists('TEST-BTC'))
        b.mark_missed(market(),config()['assets']['BTC'],'BTC',841)
        self.assertTrue(b.exists('TEST-BTC')); b.db.close()

    def test_kalshi_websocket_handshake_and_subscription(self):
        module=Mock(); sock=module.create_connection.return_value
        api=Mock(); api.headers.return_value={'test':'header'}
        f=ReferenceFeed(api)
        def receive():
            f.stop_event.set()
            return json.dumps(dict(type='value',id='BRTI',time=1000000,value='100'))
        sock.recv.side_effect=receive
        with patch.dict('sys.modules',{'websocket':module}),patch('scanner.prediction_feeds.time.time',return_value=1001):
            f.start(); f.thread.join(timeout=3)
        self.assertEqual(module.create_connection.call_args.args[0],'wss://external-api-ws.kalshi.com/trade-api/ws/v2')
        self.assertEqual(json.loads(sock.send.call_args.args[0])['params']['index_ids'],['BRTI','ETHUSD_RTI'])
        self.assertEqual(len(f.snapshot('BRTI')),1)

    def test_signed_request_strips_query(self):
        from cryptography.hazmat.primitives.asymmetric import rsa,padding
        from cryptography.hazmat.primitives import hashes
        a=Kalshi(); a.key_id='test'; a.private_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        with patch('scanner.prediction_feeds.time.time',return_value=1000): h=a.headers('/trade-api/ws/v2?ignored=yes')
        a.private_key.public_key().verify(base64.b64decode(h['KALSHI-ACCESS-SIGNATURE']),b'1000000GET/trade-api/ws/v2',
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32),hashes.SHA256())

    def test_failed_asset_discovery_keeps_other_asset_review(self):
        b=self.bot(); b.api.markets.side_effect=[RuntimeError('offline'),[]]
        b.markets=[(market(),config()['assets']['BTC'],'BTC')]
        with patch('scanner.prediction_bot.time.time',return_value=780): b.step(780)
        self.assertTrue(b.exists('TEST-BTC')); b.db.close()

    def test_sparse_two_second_prices_not_valid_sixty_sample_average(self):
        b=self.bot(); b.feed.snapshot.return_value=snapshot()['ticks'][::2]
        with self.assertRaises(ValueError): self.process(b)
        self.assertFalse(b.exists('TEST-BTC')); b.db.close()


class PublicPreflightTests(unittest.TestCase):
    def test_current_contracts_and_no_reference_claim(self):
        from scanner.prediction_bot import public_check
        eth=market()
        eth['rules_primary']=eth['rules_primary'].replace('BRTI','ETHUSDRTI')
        c=config(); c['assets']['ETH']['rules_sha256']=rules_hash(eth)
        api=Mock(); api.markets.side_effect=[[market()],[eth]]
        r=public_check(c,api,lambda:780)
        self.assertTrue(r['public_ready'])
        self.assertFalse(r['reference_ready'])
        self.assertFalse(r['signals_enabled'])

    def test_expired_contracts_are_not_ready(self):
        from scanner.prediction_bot import public_check
        api=Mock(); api.markets.return_value=[market()]
        self.assertFalse(public_check(config(),api,lambda:901)['public_ready'])

    def test_inconclusive_review_does_not_prevent_later_signal(self):
        b=RuntimeTests().bot()
        with patch('scanner.prediction_bot.review',return_value=dict(direction=None,reasons=['No trend'])):
            RuntimeTests().process(b)
        self.assertFalse(b.exists('TEST-BTC'))
        RuntimeTests().process(b)
        self.assertTrue(b.exists('TEST-BTC'))
        b.db.close()
