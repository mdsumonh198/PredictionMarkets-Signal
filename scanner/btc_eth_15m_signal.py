"""Kalshi-native BTC/ETH 15-minute prediction-market Telegram signals.

Public market data only. Sends an EARLY signal near T-3m, a FINAL signal near
T-1m as a reply, then replies with the official Kalshi settlement result.
No orders are placed and no Kalshi account/API key is required for these REST reads.
"""
import argparse
import json
import logging
import math
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from scanner.notifications.telegram import Telegram
from scanner.control import Control

BASE = "https://external-api.kalshi.com/trade-api/v2"
KRAKEN_BASE = "https://api.kraken.com/0/public/Ticker"
SERIES = {"BTC": "KXBTC15M", "ETH": "KXETH15M"}
KRAKEN_PAIRS = {"BTC": "XBTUSD", "ETH": "ETHUSD"}


def _f(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default


def _ts(v):
    if not v: return 0.0
    try: return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError): return 0.0


class KalshiPublic:
    def __init__(self, base=BASE, timeout=15):
        self.base, self.timeout = base.rstrip('/'), timeout

    def get(self, path, params=None):
        url = self.base + path
        if params: url += '?' + urlencode(params)
        req = Request(url, headers={'Accept':'application/json','User-Agent':'PredictionMarkets-Signal/2.0'})
        with urlopen(req, timeout=self.timeout) as r:
            return json.load(r)

    def open_market(self, series):
        data=self.get('/markets', {'series_ticker':series,'status':'open','limit':100})
        markets=data.get('markets') or []
        now=time.time()
        # Prefer the active contract whose close is nearest in the future.
        live=[m for m in markets if _ts(m.get('close_time')) > now-5]
        if not live: return None
        return min(live, key=lambda m: _ts(m.get('close_time')) or 10**20)

    def market(self, ticker):
        return self.get('/markets/' + ticker).get('market')

    def orderbook(self, ticker):
        return self.get('/markets/' + ticker + '/orderbook').get('orderbook_fp') or {}

    def candles(self, series, ticker, start_ts, end_ts):
        return self.get(f'/series/{series}/markets/{ticker}/candlesticks', {
            'start_ts':int(start_ts),'end_ts':int(end_ts),'period_interval':1
        }).get('candlesticks') or []



def current_spot(coin, timeout=10):
    """Free public display price. Settlement still uses Kalshi official result."""
    pair = KRAKEN_PAIRS[coin]
    req = Request(KRAKEN_BASE + '?' + urlencode({'pair': pair}),
                  headers={'Accept':'application/json','User-Agent':'PredictionMarkets-Signal/2.1'})
    with urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    if data.get('error'):
        raise ValueError('Kraken ticker error: ' + ', '.join(data['error']))
    rows = data.get('result') or {}
    if not rows:
        raise ValueError('Kraken ticker returned no result')
    row = next(iter(rows.values()))
    price = _f((row.get('c') or [None])[0], math.nan)
    if not math.isfinite(price) or price <= 0:
        raise ValueError('Kraken ticker returned invalid price')
    return price


def _mid(m):
    bid=_f(m.get('yes_bid_dollars'), math.nan); ask=_f(m.get('yes_ask_dollars'), math.nan)
    if math.isfinite(bid) and math.isfinite(ask) and ask >= bid: return (bid+ask)/2
    last=_f(m.get('last_price_dollars'), math.nan)
    return last if math.isfinite(last) else 0.5


def _book_pressure(book):
    # Kalshi exposes resting YES and NO bid levels. Sum size as a simple depth-pressure feature.
    yes=sum(_f(x[1]) for x in (book.get('yes_dollars') or []) if len(x)>=2)
    no=sum(_f(x[1]) for x in (book.get('no_dollars') or []) if len(x)>=2)
    total=yes+no
    return ((yes-no)/total if total else 0.0), yes, no


def _market_momentum(candles):
    vals=[]
    for c in candles:
        p=c.get('price') or {}
        v=_f(p.get('close_dollars'), math.nan)
        if math.isfinite(v): vals.append(v)
    if len(vals)<2: return 0.0
    look=vals[-4:]  # recent ~3 minutes of prediction-price movement
    return look[-1]-look[0]


def evaluate(api, coin, market, now):
    ticker=market['ticker']; series=SERIES[coin]
    close_ts=_ts(market.get('close_time'))
    seconds_left=max(0, int(close_ts-now))
    yes_mid=_mid(market); no_mid=1.0-yes_mid
    target=_f(market.get('floor_strike'), math.nan)
    if not math.isfinite(target) or target <= 0:
        target=None
    try:
        spot=current_spot(coin)
    except Exception as exc:
        logging.warning('%s current spot unavailable: %s',coin,exc); spot=None
    distance_pct=((spot-target)/target*100.0) if (spot is not None and target is not None) else None
    try: book=api.orderbook(ticker)
    except Exception as exc:
        logging.warning('%s orderbook unavailable: %s',ticker,exc); book={}
    pressure,yes_depth,no_depth=_book_pressure(book)
    try: candles=api.candles(series,ticker,max(_ts(market.get('open_time')),now-12*60),now)
    except Exception as exc:
        logging.warning('%s candlesticks unavailable: %s',ticker,exc); candles=[]
    momentum=_market_momentum(candles)

    # Kalshi-native ensemble: market probability is primary; recent contract momentum
    # and order-book depth are confirmations. This is not a guaranteed win probability.
    edge=(yes_mid-0.5)*2.0
    score=edge*0.70 + max(-1,min(1,momentum/0.08))*0.20 + pressure*0.10
    direction='UP' if score>0 else 'DOWN'
    strength=abs(score)
    # Do not force a direction when the Kalshi market itself is near 50/50 and confirmations are weak.
    if strength < 0.08 or (0.47 <= yes_mid <= 0.53 and abs(momentum)<0.02): direction='NO TRADE'
    confidence=min(95.0, max(50.0, 50.0 + strength*50.0))
    reasons=[]
    reasons.append(f"Kalshi YES {yes_mid*100:.1f}% / NO {no_mid*100:.1f}%")
    if momentum>0.005: reasons.append('Kalshi 1m momentum favors UP')
    elif momentum<-0.005: reasons.append('Kalshi 1m momentum favors DOWN')
    if pressure>0.08: reasons.append('orderbook depth favors YES/UP')
    elif pressure<-0.08: reasons.append('orderbook depth favors NO/DOWN')
    return {'coin':coin,'series':series,'ticker':ticker,'direction':direction,'confidence':confidence,
            'yes_mid':yes_mid,'no_mid':no_mid,'momentum':momentum,'pressure':pressure,
            'yes_depth':yes_depth,'no_depth':no_depth,'close_ts':close_ts,'seconds_left':seconds_left,
            'volume':_f(market.get('volume_fp') or market.get('volume')),'reasons':reasons,
            'target':target,'spot':spot,'distance_pct':distance_pct}


def format_signal(s, stage):
    icon='🟡' if stage=='EARLY' else '🔵'
    d=s['direction']; dicon='🟢' if d=='UP' else ('🔴' if d=='DOWN' else '⚪')
    mins,secs=divmod(max(0,s['seconds_left']),60)
    price=[]
    if s.get('target') is not None: price.append(f"Target Price: ${s['target']:,.2f}")
    if s.get('spot') is not None: price.append(f"Current {s['coin']} Price: ${s['spot']:,.2f}")
    if s.get('distance_pct') is not None:
        label='Above Target' if s['distance_pct'] >= 0 else 'Below Target'; price.append(f"{label}: {s['distance_pct']:+.3f}%")
    why=[]
    if s.get('distance_pct') is not None: why.append('Current price is above the target' if s['distance_pct']>=0 else 'Current price is below the target')
    if s.get('momentum',0)>0.005: why.append('Short-term market momentum is UP')
    elif s.get('momentum',0)<-0.005: why.append('Short-term market momentum is DOWN')
    if s.get('pressure',0)>0.08: why.append('Prediction-market activity supports UP')
    elif s.get('pressure',0)<-0.08: why.append('Prediction-market activity supports DOWN')
    if not why: why=['Market signals are mixed']
    tail='⚠️ Early signal — wait for the Final Signal.' if stage=='EARLY' else ('✅ Final signal for this 15-minute market.' if d!='NO TRADE' else '⚪ Direction is unclear — skip this market.')
    return '\n'.join([f"{icon} {s['coin']} 15M {stage} SIGNAL",'',f"{dicon} Signal: {d}",f"Confidence: {s['confidence']:.1f}%",'',*price,'','Market Chance:',f"UP: {s['yes_mid']*100:.1f}%",f"DOWN: {s['no_mid']*100:.1f}%",f"Time Left: {mins}m {secs}s",'',f"Why {d}?" if d!='NO TRADE' else 'Why NO TRADE?',*[f"• {x}" for x in why],'',tail])


class Runner:
    def __init__(self, api, notifier, dbpath):
        self.api,self.notifier=api,notifier
        self.control=Control(dbpath)
        Path(dbpath).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(dbpath); self.db.row_factory=sqlite3.Row
        self.db.execute('''CREATE TABLE IF NOT EXISTS kalshi_signals(
            ticker TEXT PRIMARY KEY, coin TEXT, close_ts REAL,
            early_direction TEXT, early_message_id INTEGER, early_at REAL,
            final_direction TEXT, final_message_id INTEGER, final_at REAL,
            result TEXT, official_outcome TEXT, result_at REAL)''')
        self.db.commit()

    def row(self,ticker): return self.db.execute('SELECT * FROM kalshi_signals WHERE ticker=?',(ticker,)).fetchone()
    def ensure(self,s):
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO kalshi_signals(ticker,coin,close_ts) VALUES(?,?,?)',(s['ticker'],s['coin'],s['close_ts']))

    def send_stage(self,s,stage):
        self.ensure(s); row=self.row(s['ticker'])
        col='early_message_id' if stage=='EARLY' else 'final_message_id'
        if row[col] is not None: return False
        reply=row['early_message_id'] if stage=='FINAL' else None
        mid=self.notifier.send_text(format_signal(s,stage),reply_to_message_id=reply)
        with self.db:
            if stage=='EARLY': self.db.execute('UPDATE kalshi_signals SET early_direction=?,early_message_id=?,early_at=? WHERE ticker=?',(s['direction'],mid,time.time(),s['ticker']))
            else: self.db.execute('UPDATE kalshi_signals SET final_direction=?,final_message_id=?,final_at=? WHERE ticker=?',(s['direction'],mid,time.time(),s['ticker']))
        return True

    def stats(self):
        r=self.db.execute('''SELECT COUNT(*) total,
          SUM(CASE WHEN result IN ('WIN','LOSS') THEN 1 ELSE 0 END) closed,
          SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) wins,
          SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) losses
          FROM kalshi_signals WHERE final_direction IN ('UP','DOWN')''').fetchone()
        d={k:int(r[k] or 0) for k in ('total','closed','wins','losses')}; d['rate']=100*d['wins']/d['closed'] if d['closed'] else 0.0; return d

    def settle_due(self,now):
        rows=self.db.execute('''SELECT * FROM kalshi_signals WHERE result IS NULL AND close_ts<=?
          AND final_direction IN ('UP','DOWN') AND final_message_id IS NOT NULL ORDER BY close_ts''',(now,)).fetchall()
        for row in rows:
            try:
                m=self.api.market(row['ticker'])
                outcome=(m.get('result') or '').lower()
                status=(m.get('status') or '').lower()
                if outcome not in ('yes','no'):
                    logging.info('%s awaiting Kalshi settlement (status=%s)',row['ticker'],status); continue
                predicted='yes' if row['final_direction']=='UP' else 'no'
                result='WIN' if predicted==outcome else 'LOSS'
                with self.db:
                    self.db.execute('UPDATE kalshi_signals SET result=?,official_outcome=?,result_at=? WHERE ticker=?',(result,outcome,time.time(),row['ticker']))
                st=self.stats(); icon='✅' if result=='WIN' else '❌'; official='UP / YES' if outcome=='yes' else 'DOWN / NO'
                txt='\n'.join([f"{icon} {row['coin']} 15M RESULT: {result}",'',f"Final Signal: {row['final_direction']}",f"Kalshi official result: {official}",f"Market: {row['ticker']}",'',f"📊 Closed: {st['closed']} | Wins: {st['wins']} | Losses: {st['losses']}",f"📈 Final-signal win rate: {st['rate']:.1f}%",'', 'Result uses Kalshi official settlement, not a separate spot-price comparison.'])
                self.notifier.send_text(txt,reply_to_message_id=row['final_message_id'])
                logging.info('%s settled %s official=%s',row['ticker'],result,outcome)
            except Exception as exc: logging.warning('%s settlement pending/error: %s',row['ticker'],exc)

    def execute_mode(self,s,stage):
        cfg=self.control.get()
        if not cfg.get('enabled') or cfg.get('mode')=='signal' or s['direction']=='NO TRADE': return
        if not cfg.get(s['coin'].lower(),True): return
        amount=float(cfg.get('amount_usd',10.0))
        if cfg.get('mode')=='paper':
            action='ENTER' if stage=='EARLY' else 'KEEP/CLOSE CHECK'
            self.control.log(ticker=s['ticker'],coin=s['coin'],stage=stage,action=action,direction=s['direction'],amount=amount,status='PAPER',note='No real order placed')
            return
        # Hard safety lock: do not guess a Coinbase Prediction Markets order endpoint.
        self.control.log(ticker=s['ticker'],coin=s['coin'],stage=stage,action='BLOCKED',direction=s['direction'],amount=amount,status='LIVE_LOCKED',note='Coinbase Prediction Market programmatic order endpoint not verified')

    def cycle(self):
        now=time.time(); self.settle_due(now)
        for coin,series in SERIES.items():
            try:
                m=self.api.open_market(series)
                if not m: logging.info('%s no open Kalshi 15m market',coin); continue
                s=evaluate(self.api,coin,m,now); left=s['seconds_left']
                # Poll-safe windows: one message around T-3m, then one around T-1m.
                if 150 <= left <= 210:
                    if self.send_stage(s,'EARLY'):
                        self.execute_mode(s,'EARLY'); logging.info('%s EARLY sent %s',coin,s['direction'])
                elif 35 <= left <= 90:
                    # Ensure the 1m final can still be sent if bot started after T-3m.
                    self.ensure(s)
                    if self.send_stage(s,'FINAL'):
                        self.execute_mode(s,'FINAL'); logging.info('%s FINAL sent %s',coin,s['direction'])
                else: logging.info('%s monitoring Kalshi | %ss to close | YES %.1f%%',coin,left,s['yes_mid']*100)
            except Exception as exc: logging.exception('%s Kalshi evaluation failed: %s',coin,exc)


def load_env(path):
    env={}
    if Path(path).exists():
        for raw in Path(path).read_text(encoding='utf-8').splitlines():
            raw=raw.strip()
            if raw and not raw.startswith('#') and '=' in raw:
                k,v=raw.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    return env


def main():
    p=argparse.ArgumentParser(description='Kalshi BTC/ETH 15m public-market signal monitor; Telegram only')
    p.add_argument('--env',default='.env'); p.add_argument('--interval',type=int,default=20); args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    env=load_env(args.env); token=os.environ.get('TELEGRAM_TOKEN') or env.get('TELEGRAM_TOKEN'); chat=os.environ.get('TELEGRAM_CHAT_ID') or env.get('TELEGRAM_CHAT_ID')
    notifier=Telegram(token,chat); runner=Runner(KalshiPublic(),notifier,'data/kalshi_btc_eth_15m.sqlite')
    notifier.send_text('🟢 KALSHI BTC/ETH 15M SIGNAL BOT RUNNING\n\nPrimary source: Kalshi production public market data.\nSignals: ~3m early + ~1m final reply.\nResults: official Kalshi settlement.\nControl modes: Signal Only / Paper Auto Trade / Live Auto Trade (live remains safety-locked until verified API support).')
    logging.info('KALSHI BTC/ETH 15M BOT STARTED | interval=%ss',args.interval)
    while True:
        try: runner.cycle()
        except Exception as exc: logging.exception('cycle failed: %s',exc)
        time.sleep(max(10,args.interval))

if __name__=='__main__': main()
