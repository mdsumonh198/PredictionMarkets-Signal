"""BTC/ETH 15-minute directional research signals from public Coinbase spot data.

Monitors each 15m window and sends at most one Telegram signal per asset during
minutes 13-15. Signal only; never places an order.
"""
import argparse
import json
import logging
import math
import os
import sqlite3
import time
from pathlib import Path

from scanner.market_data.coinbase import Coinbase
from scanner.notifications.telegram import Telegram

TF = 900
ASSETS = ("BTC-USD", "ETH-USD")


def ema(values, period):
    if not values:
        return math.nan
    a = 2.0 / (period + 1)
    out = values[0]
    for v in values[1:]:
        out = a * v + (1 - a) * out
    return out


def rsi(values, period=14):
    if len(values) < period + 1:
        return math.nan
    gains, losses = [], []
    for a, b in zip(values[-period-1:-1], values[-period:]):
        d = b - a
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag, al = sum(gains)/period, sum(losses)/period
    if al == 0:
        return 100.0
    return 100 - 100/(1 + ag/al)


def macd_hist(values):
    if len(values) < 35:
        return math.nan
    # MACD history sufficient for a 9-period signal EMA.
    line=[]
    for i in range(26, len(values)+1):
        xs=values[:i]
        line.append(ema(xs,12)-ema(xs,26))
    return line[-1]-ema(line[-9:],9)


def completed_history(api, symbol, now):
    end = int(now // TF) * TF
    start = end - 80 * TF
    candles = api.candles(symbol, start, end, TF)
    if len(candles) < 50 or candles[-1].time != end-TF:
        raise ValueError("completed Coinbase candle history unavailable")
    return candles


def evaluate(api, symbol, now):
    bucket = int(now // TF) * TF
    elapsed = now - bucket
    if not 780 <= elapsed < 900:
        return None
    candles = completed_history(api, symbol, now)
    closes=[c.close for c in candles]
    vols=[c.volume for c in candles]
    q=api.liquidity(symbol)
    price=(q.bid+q.ask)/2
    open_price=closes[-1]
    move=(price/open_price-1)*100
    e9=ema(closes[-40:]+[price],9); e21=ema(closes[-50:]+[price],21)
    rv=rsi(closes+[price]); mh=macd_hist(closes+[price])
    avgvol=sum(vols[-20:])/20 if vols[-20:] else 0
    vr=(vols[-1]/avgvol) if avgvol else 1.0

    up=down=0.0; reasons=[]
    if price > e9 > e21: up+=2; reasons.append("EMA bullish")
    elif price < e9 < e21: down+=2; reasons.append("EMA bearish")
    if move >= 0.08: up+=2; reasons.append("current 15m momentum up")
    elif move <= -0.08: down+=2; reasons.append("current 15m momentum down")
    if rv >= 55: up+=1.5; reasons.append("RSI supports up")
    elif rv <= 45: down+=1.5; reasons.append("RSI supports down")
    if mh > 0: up+=1.5; reasons.append("MACD positive")
    elif mh < 0: down+=1.5; reasons.append("MACD negative")
    # Previous completed candle direction and volume context.
    prev=closes[-1]/closes[-2]-1
    if prev > 0: up+=1
    elif prev < 0: down+=1
    if vr >= 1.15:
        if move > 0: up+=1
        elif move < 0: down+=1
        reasons.append("volume confirmation")

    total=max(up+down,1)
    direction="UP" if up>down else "DOWN"
    edge=abs(up-down)
    confidence=50 + 50*edge/total
    # Avoid forced guesses when evidence is mixed or current move is nearly flat.
    if edge < 2.0 or abs(move) < 0.03:
        direction="NO TRADE"
    return dict(symbol=symbol, direction=direction, confidence=min(confidence,95.0), price=price,
                window_start=bucket, window_end=bucket+TF, seconds_left=max(0,int(bucket+TF-now)),
                move=move, rsi=rv, ema9=e9, ema21=e21, macd_hist=mh, volume_ratio=vr,
                reasons=reasons)


def format_signal(s):
    coin=s['symbol'].split('-')[0]
    if s['direction']=='NO TRADE': icon='⚪'
    else: icon='🟢' if s['direction']=='UP' else '🔴'
    mins,secs=divmod(s['seconds_left'],60)
    return '\n'.join([
        f"{icon} {coin} 15M DIRECTION SIGNAL",
        '', f"Direction: {s['direction']}", f"Confidence score: {s['confidence']:.1f}/100",
        f"Coinbase spot: ${s['price']:,.2f}", f"Current-window move: {s['move']:+.3f}%",
        f"Closes in: {mins}m {secs}s", '',
        f"RSI: {s['rsi']:.1f}", f"EMA9 / EMA21: {s['ema9']:.2f} / {s['ema21']:.2f}",
        f"MACD histogram: {s['macd_hist']:.6g}",
        '', 'Signal only; probability-based research, not guaranteed. No order placed.'
    ])


class Runner:
    def __init__(self, api, notifier, dbpath):
        self.api,self.notifier=api,notifier
        Path(dbpath).parent.mkdir(parents=True,exist_ok=True)
        self.db=sqlite3.connect(dbpath)
        self.db.execute('CREATE TABLE IF NOT EXISTS sent(asset TEXT, window_start INTEGER, direction TEXT, sent_at REAL, PRIMARY KEY(asset,window_start))')

    def already(self, asset, window):
        return self.db.execute('SELECT 1 FROM sent WHERE asset=? AND window_start=?',(asset,window)).fetchone() is not None

    def reserve(self,s):
        try:
            with self.db:
                self.db.execute('INSERT INTO sent VALUES(?,?,?,?)',(s['symbol'],s['window_start'],s['direction'],time.time()))
            return True
        except sqlite3.IntegrityError:
            return False

    def cycle(self):
        now=time.time(); bucket=int(now//TF)*TF; elapsed=now-bucket
        if elapsed < 780:
            logging.info('MONITORING BTC/ETH | 15m window | decision in %dm %ds', int((780-elapsed)//60), int((780-elapsed)%60))
            return
        for symbol in ASSETS:
            if self.already(symbol,bucket): continue
            try:
                s=evaluate(self.api,symbol,time.time())
                if s and self.reserve(s):
                    self.notifier.send_text(format_signal(s))
                    logging.info('%s signal sent: %s %.1f',symbol,s['direction'],s['confidence'])
            except Exception as exc:
                logging.error('%s evaluation failed: %s',symbol,exc)


def main():
    p=argparse.ArgumentParser(description='BTC/ETH Coinbase 15m direction signal monitor; Telegram only')
    p.add_argument('--env',default='.env'); p.add_argument('--interval',type=int,default=20)
    args=p.parse_args()
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    env={}
    if Path(args.env).exists():
        for raw in Path(args.env).read_text(encoding='utf-8').splitlines():
            raw=raw.strip()
            if raw and not raw.startswith('#') and '=' in raw:
                k,v=raw.split('=',1); env[k.strip()]=v.strip().strip('"').strip("'")
    token=os.environ.get('TELEGRAM_TOKEN') or env.get('TELEGRAM_TOKEN')
    chat=os.environ.get('TELEGRAM_CHAT_ID') or env.get('TELEGRAM_CHAT_ID')
    notifier=Telegram(token,chat)
    runner=Runner(Coinbase(),notifier,'data/btc_eth_15m.sqlite')
    notifier.send_text('🟢 BTC/ETH 15M SIGNAL BOT RUNNING\n\nMonitoring Coinbase BTC-USD and ETH-USD.\nDecision window: final 2 minutes of each 15-minute interval.\nSignal only; no order placed.')
    logging.info('BTC/ETH 15M BOT STARTED | interval=%ss | final-2m decision window',args.interval)
    while True:
        try: runner.cycle()
        except Exception as exc: logging.exception('cycle failed: %s',exc)
        time.sleep(max(10,args.interval))

if __name__=='__main__': main()
