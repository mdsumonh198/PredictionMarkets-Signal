"""Separate read-only BTC/ETH prediction paper bot; never places orders."""
import argparse
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from scanner.prediction import review, number
from scanner.prediction_feeds import Kalshi, ReferenceFeed, epoch, rules_hash, rule_times
from scanner.notifications.telegram import Telegram


def settings(path):
    c=json.loads(Path(path).read_text(encoding='utf-8'))
    if c.get('mode') != 'paper': raise ValueError('Only paper prediction mode is implemented')
    if set(c['assets']) != {'BTC','ETH'}: raise ValueError('Configure exactly BTC and ETH')
    for asset, a in c['assets'].items():
        if not a['series'] or len(a['rules_sha256']) != 64 or a.get('rules_verified') is not True:
            raise ValueError(asset+': provide verified series, contract rules hash and rules_verified=true')
        expected='BRTI' if asset=='BTC' else 'ETHUSD_RTI'
        if a['reference_index'] != expected or a.get('yes_direction') != 'UP' or a.get('tie') != 'UP':
            raise ValueError(asset+': unsupported reference, YES mapping or tie rule')
        if a.get('expiry_field') != 'close_time' or a.get('target_field') != 'floor_strike':
            raise ValueError(asset+': unsupported expiry/target mapping; verify real contract first')
        if not a.get('rules_url','').startswith('https://'):
            raise ValueError('Verified HTTPS rules URL required')
        if not 0 <= number(a['fee_per_contract']) < 1: raise ValueError('Invalid fee')
    if not 0 < number(c['max_contract_ask']) < 1 or not 0 < number(c['max_contract_spread']) < 1:
        raise ValueError('Invalid contract cost limits')
    return c


def contract(m,a,asset):
    if m.get('market_type') != 'binary' or m.get('status') not in ('active','open'):
        raise ValueError('Market not open binary contract')
    if rules_hash(m) != a['rules_sha256']: raise ValueError('Contract rules changed or unverified')
    if m.get('strike_type') != 'greater_or_equal':
        raise ValueError('Contract strike must be greater_or_equal; no silent equality assumption')
    expiry=epoch(m[a['expiry_field']])
    match,rule_end,rule_start=rule_times(m)
    expected='BRTI' if asset=='BTC' else 'ETHUSDRTI'
    if match[1]!=expected or rule_end!=expiry or rule_end-rule_start!=900:
        raise ValueError('Contract rule index or actual 15-minute interval mismatch')
    target=number(m[a['target_field']])
    if target<=0: raise ValueError('Target not yet available')
    return dict(asset=asset,contract_id=m['ticker'],reference_index=a['reference_index'],
                rules_url=a['rules_url'],start=expiry-900,expiry=expiry,target=target,
                settlement='final_60_seconds_average')


def utc(stamp):
    return datetime.fromtimestamp(stamp,timezone.utc).strftime('%d %b %H:%M:%S UTC')


def format_candidate(s,r):
    icon='🟢' if r['direction']=='UP' else '🔴'
    return '\n'.join(['🧪 PAPER PREDICTION',f"🪙 {s['asset']} · 15M",f"{icon} Direction: {r['direction']}",
        f"🎯 Price to beat: ${s['target']:,.4f}",f"📊 Calculated reference 60s average: ${r['reference_average_60s']:,.4f}",
        f"💵 Kalshi contract ask: {r['contract_ask']*100:.2f}¢",f"⏰ Ends: {utc(s['expiry'])}",
        'Research signal — win probability has not been calibrated.',
        'Paper tracking only. Coinbase price/fees may differ; no order placed.'])


class PaperBot:
    def __init__(self,c,api,feed,database,notifier=None):
        self.c,self.api,self.feed,self.notifier=c,api,feed,notifier
        Path(database).parent.mkdir(parents=True,exist_ok=True) if database!=':memory:' else None
        self.db=sqlite3.connect(database)
        self.db.row_factory=sqlite3.Row
        self.db.execute('CREATE TABLE IF NOT EXISTS prediction_reviews (ticker TEXT, chat TEXT, expiry REAL, status TEXT, payload TEXT, message_id INTEGER, outcome TEXT, result_status TEXT, PRIMARY KEY(ticker,chat))')
        self.chat=str(notifier.chat_id) if notifier else 'offline'
        self.markets=[]
        self.next_discovery=self.next_results=0

    def exists(self,ticker):
        return self.db.execute('SELECT 1 FROM prediction_reviews WHERE ticker=? AND chat=?',(ticker,self.chat)).fetchone() is not None

    def record(self,s,r):
        payload=json.dumps(dict(snapshot=s,review=r),allow_nan=False)
        try:
            with self.db:
                self.db.execute('INSERT INTO prediction_reviews VALUES(?,?,?,?,?,NULL,NULL,NULL)',
                    (s['contract_id'],self.chat,s['expiry'],'recorded',payload))
        except sqlite3.IntegrityError: return False
        return True

    def process(self,m,a,asset,clock=None):
        clock=clock or time.time
        s=contract(m,a,asset)
        now=clock()
        if self.exists(s['contract_id']) or not 60 < s['expiry']-now <= 120: return
        s['ticks']=self.feed.snapshot(a['reference_index'])
        s['contract_quotes']=self.api.quotes(s['contract_id'],a['fee_per_contract'])
        s['now']=clock()
        if not 60 < s['expiry']-s['now'] <=120: raise ValueError('Entry processing delayed beyond paper window')
        r=review(s)
        if not r['direction'] and any('feed' in reason.lower() for reason in r['reasons']):
            raise ValueError('Reference warming up or unavailable; retry within decision window')
        if r['direction'] and 'contract_ask' not in r: raise ValueError('Unverified contract quote')
        if r['direction'] and (r['contract_ask']>self.c['max_contract_ask'] or r['contract_spread']>self.c['max_contract_spread']):
            r['direction']=None
            r['reasons'].append('Paper contract cost/spread limit exceeded')
        # Keep monitoring after an inconclusive review; reserve only a valid candidate.
        if not r['direction']: return
        if not self.record(s,r): return
        logging.info('Prediction paper review %s: %s',s['contract_id'],r['direction'] or 'inconclusive')
        if not r['direction'] or not self.notifier: return
        # Durable reservation before network send; ambiguous delivery never auto-retried.
        with self.db:
            self.db.execute('UPDATE prediction_reviews SET status=? WHERE ticker=? AND chat=?',('sending',s['contract_id'],self.chat))
        # Recheck feed/quote/timing after persistence and immediately before sending.
        current=clock()
        if current-s['now']>2 or current-s['contract_quotes'][r['direction']]['time']>2 or s['expiry']-current<=60:
            with self.db:
                self.db.execute('UPDATE prediction_reviews SET status=? WHERE ticker=? AND chat=?',('blocked_stale',s['contract_id'],self.chat))
            return
        mid=self.notifier.send_text(format_candidate(s,r))
        with self.db:
            self.db.execute('UPDATE prediction_reviews SET status=?,message_id=? WHERE ticker=? AND chat=?',('sent',mid,s['contract_id'],self.chat))

    def mark_missed(self,m,a,asset,now):
        s=contract(m,a,asset)
        if 0 < s['expiry']-now <=60 and not self.exists(s['contract_id']):
            r=dict(status='MISSED_WINDOW',direction=None,trade_authorized=False,
                   reasons=['No verified review before decision deadline; no late signal sent'])
            self.record(s,r)
            logging.warning('Prediction decision window missed: %s',s['contract_id'])

    def results(self,now):
        rows=self.db.execute('SELECT * FROM prediction_reviews WHERE chat=? AND expiry<=? AND outcome IS NULL',(self.chat,now)).fetchall()
        for row in rows:
            try:
                m=self.api.market(row['ticker'])
                if m.get('status') != 'settled' or m.get('is_provisional') or m.get('result') not in ('yes','no'): continue
                p=json.loads(row['payload']); r=p['review']
                actual='UP' if m['result']=='yes' else 'DOWN'
                win=r['direction']==actual if r['direction'] else None
                pnl=(1 if win else 0)-r['break_even_probability'] if win is not None else None
                with self.db:
                    self.db.execute('UPDATE prediction_reviews SET outcome=?,result_status=? WHERE ticker=? AND chat=?',
                        (actual,'sending' if row['message_id'] else 'recorded',row['ticker'],self.chat))
                if self.notifier and row['message_id']:
                    text='\n'.join(['🏁 PAPER RESULT',f"🪙 {p['snapshot']['asset']} · Result: {actual}",
                        '✅ Correct direction' if win else '❌ Incorrect direction',
                        f'💵 Indicative net per contract: ${pnl:+.4f}',
                        'Assumes one contract filled at recorded Kalshi ask; fees are configured estimates. No actual trade.'])
                    self.notifier.send_text(text,reply_to_message_id=row['message_id'])
                    with self.db:
                        self.db.execute('UPDATE prediction_reviews SET result_status=? WHERE ticker=? AND chat=?',('sent',row['ticker'],self.chat))
            except Exception:
                logging.warning('Prediction settlement pending or reply delivery uncertain: %s',row['ticker'])

    def step(self,now):
        if now >= self.next_discovery:
            new=[]
            for asset,a in self.c['assets'].items():
                try: discovered=self.api.markets(a['series'])
                except Exception:
                    new.extend(row for row in self.markets if row[2]==asset)
                    logging.warning('%s contract discovery unavailable; retaining cached markets',asset)
                    continue
                for m in discovered:
                    try:
                        s=contract(m,a,asset)
                        if now < s['expiry'] <= now+1800: new.append((m,a,asset))
                    except (ValueError,KeyError,TypeError):
                        logging.warning('Unverified prediction market skipped: %s',m.get('ticker','unknown'))
            self.markets=new; self.next_discovery=now+15
        for m,a,asset in self.markets:
            try:
                self.mark_missed(m,a,asset,time.time())
                self.process(m,a,asset)
            except Exception: logging.warning('Prediction data unavailable; retry within window: %s',m.get('ticker'))
        if now>=self.next_results:
            self.results(now); self.next_results=now+15


def public_check(c,api=None,clock=None):
    """Read-only preflight; does not open a database or send Telegram."""
    api=api or Kalshi()
    clock=clock or time.time
    report=dict(public_ready=True,reference_ready=False,signals_enabled=False,assets={})
    for asset,a in c['assets'].items():
        valid=[]
        try:
            for m in api.markets(a['series']):
                try:
                    s=contract(m,a,asset)
                    now=clock()
                    if s['start'] <= now < s['expiry']:
                        valid.append(dict(ticker=s['contract_id'],target=s['target'],expiry_utc=utc(s['expiry'])))
                except (ValueError,KeyError,TypeError): continue
            report['assets'][asset]=dict(status='VERIFIED_CURRENT_CONTRACT' if valid else 'NO_VERIFIED_CURRENT_CONTRACT',contracts=valid)
            if not valid: report['public_ready']=False
        except Exception:
            report['assets'][asset]=dict(status='PUBLIC_API_UNAVAILABLE',contracts=[])
            report['public_ready']=False
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--provider',choices=('coinbase','kalshi'),default='coinbase',
                   help='Coinbase is the default; Kalshi research requires explicit selection')
    p.add_argument('--coinbase-prices',action='store_true',help='Check Coinbase BTC/ETH SPOT quotes only; no signals or Telegram')
    p.add_argument('--public-check',action='store_true',help='Check current BTC/ETH public contracts without keys, database or Telegram')
    p.add_argument('--config',default='prediction-config.json')
    p.add_argument('--inspect-series',help='Print public market rules/IDs for manual verification; no Telegram')
    p.add_argument('--notify',action='store_true',help='Send explicitly labelled PAPER candidates')
    p.add_argument('--check',action='store_true',help='Verify authorized BTC/ETH streaming for up to 130 seconds; no Telegram')
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    if args.coinbase_prices:
        from scanner.coinbase_prediction import price_check
        print(json.dumps(price_check(),indent=2,allow_nan=False))
        return
    if args.provider=='coinbase':
        from scanner.coinbase_prediction import require_prediction_feed,PredictionFeedUnavailable
        try: require_prediction_feed()
        except PredictionFeedUnavailable as exc: p.error(str(exc))
    try:
        if args.inspect_series:
            api=Kalshi()
            print(json.dumps([dict(ticker=m['ticker'],rules_sha256=rules_hash(m),market=m) for m in api.markets(args.inspect_series)],indent=2))
            return
        c=settings(args.config)
        if args.public_check:
            report=public_check(c)
            print(json.dumps(report,indent=2))
            if not report['public_ready']: raise SystemExit(1)
            return
        api=Kalshi(os.environ.get('KALSHI_API_KEY_ID',''),os.environ.get('KALSHI_PRIVATE_KEY_PATH',''))
        username,key=os.environ.get('CFB_USERNAME',''),os.environ.get('CFB_API_KEY','')
        if not (username and key): api.headers('/trade-api/ws/v2')
        feed=ReferenceFeed(api,username,key)
        notifier=Telegram(os.environ.get('PREDICTION_TELEGRAM_TOKEN',''),os.environ.get('PREDICTION_TELEGRAM_CHAT_ID','')) if args.notify and not args.check else None
        bot=PaperBot(c,api,feed,c.get('database','data/prediction.sqlite'),notifier)
        feed.start()
    except Exception:
        p.error('Kalshi research setup incomplete. Check config, verified BTC/ETH rules, dependencies and private feed credentials. See PREDICTION_SETUP.md.')
    try:
        logging.info('BTC/ETH PREDICTION PAPER BOT STARTED; reference warm-up requires 120 seconds')
        if args.check:
            deadline=time.time()+130
            while time.time()<deadline:
                now=time.time()
                ready=[]
                for index in ('BRTI','ETHUSD_RTI'):
                    ticks=feed.snapshot(index)
                    ready.append(bool(len(ticks)>=119 and now-ticks[-1]['time']<=2 and ticks[-1]['time']-ticks[0]['time']>=118
                                      and all(b['time']-a['time']<=2 for a,b in zip(ticks,ticks[1:]))))
                if all(ready):
                    report=public_check(c,api)
                    if not report['public_ready']:
                        raise SystemExit('Reference ready, but current BTC/ETH contracts unavailable or rules unverified. No Telegram sent.')
                    print('Authorized BTC/ETH reference stream and current contracts verified. Contract mappings and paper profitability still require validation.')
                    return
                time.sleep(1)
            raise SystemExit('Reference readiness check failed: entitlement, credentials, clock or continuous data unavailable. No Telegram sent.')
        heartbeat=0
        while True:
            try: bot.step(time.time())
            except Exception: logging.warning('Prediction API unavailable; next poll will retry')
            if time.time()>=heartbeat:
                counts={i:len(feed.snapshot(i)) for i in ('BRTI','ETHUSD_RTI')}
                logging.info('Prediction paper heartbeat | reference ticks=%s | contracts=%s | feed=%s',counts,len(bot.markets),feed.error or 'receiving')
                heartbeat=time.time()+60
            time.sleep(1)
    except KeyboardInterrupt: pass
    finally:
        feed.close(); bot.db.close()


if __name__=='__main__': main()
