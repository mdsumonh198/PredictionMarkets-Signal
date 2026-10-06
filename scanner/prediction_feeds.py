"""Read-only Kalshi market data and entitled CF reference WebSocket adapters."""
import base64
import hashlib
import json
import re
import threading
import time
from collections import deque
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from scanner.prediction import number


def rule_times(market):
    text=market.get('rules_primary','')
    pattern=r"If the simple average of the sixty seconds of CF Benchmarks' (BRTI|ETHUSDRTI) before (.+?) is at least the simple average of the sixty seconds of CF Benchmarks' \1 before (.+?), then the market resolves to Yes\."
    match=re.fullmatch(pattern,text)
    if not match: raise ValueError('Unrecognized contract rule template')
    def parse(value):
        for fmt in ('%I:%M %p EDT on %b %d, %Y','%I:%M %p EDT on %B %d, %Y',
                    '%I:%M %p EST on %b %d, %Y','%I:%M %p EST on %B %d, %Y'):
            try:
                d=datetime.strptime(value,fmt)
                offset=-4 if 'EDT' in value else -5
                return d.replace(tzinfo=timezone(timedelta(hours=offset))).timestamp()
            except ValueError: pass
        raise ValueError('Unrecognized rule timestamp')
    return match,parse(match[2]),parse(match[3])


def rules_hash(market):
    text=market.get('rules_primary','')
    try:
        match,_,_=rule_times(market)
        # Only replace the two parsed timestamps, not targets or other rule text.
        text=text[:match.start(2)]+'<END>'+text[match.end(2):match.start(3)]+'<START>'+text[match.end(3):]
    except ValueError: pass
    return hashlib.sha256((text+'\n'+market.get('rules_secondary','')).encode()).hexdigest()


def epoch(value):
    d = datetime.fromisoformat(value.replace('Z','+00:00'))
    if d.tzinfo is None:
        raise ValueError('Contract timestamps require timezone')
    return d.timestamp()


class Kalshi:
    base = 'https://external-api.kalshi.com/trade-api/v2'

    def __init__(self, key_id='', pem_path=''):
        self.key_id, self.private_key = key_id, None
        if key_id and pem_path:
            from cryptography.hazmat.primitives.serialization import load_pem_private_key
            self.private_key = load_pem_private_key(Path(pem_path).read_bytes(), password=None)

    def headers(self, path):
        if not self.key_id or not self.private_key:
            raise ValueError('Set KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH privately')
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        stamp = str(int(time.time()*1000))
        message = (stamp+'GET'+path.split('?')[0]).encode()
        if isinstance(self.private_key, Ed25519PrivateKey):
            signature = self.private_key.sign(message)
        else:
            signature = self.private_key.sign(message, padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=32), hashes.SHA256())
        return {'KALSHI-ACCESS-KEY':self.key_id,'KALSHI-ACCESS-TIMESTAMP':stamp,
                'KALSHI-ACCESS-SIGNATURE':base64.b64encode(signature).decode()}

    def get(self, path, params=None):
        url = self.base+path+('?' + urlencode(params) if params else '')
        with urlopen(Request(url,headers={'User-Agent':'PredictionResearch/1.0'}),timeout=5) as response:
            return json.load(response)

    def market(self, ticker):
        return self.get('/markets/'+quote(ticker,safe=''))['market']

    def markets(self, series):
        result, cursor, seen = [], '', set()
        for _ in range(20):
            data = self.get('/markets', dict(series_ticker=series,status='open',limit=100,cursor=cursor))
            result.extend(data['markets'])
            cursor = data.get('cursor','')
            if not cursor: return result
            if cursor in seen: raise ValueError('Repeated market cursor')
            seen.add(cursor)
        raise ValueError('Market discovery pagination limit exceeded')

    def quotes(self, ticker, fee):
        started = time.time()
        book = self.get('/markets/'+quote(ticker,safe='')+'/orderbook')['orderbook_fp']
        def best(rows):
            levels = [(number(float(p)),number(float(size))) for p,size in rows]
            if not levels or any(not 0 < p < 1 or size <= 0 for p,size in levels):
                raise ValueError('Empty or invalid contract order book')
            return max(levels)[0]
        yes,no = best(book['yes_dollars']),best(book['no_dollars'])
        # REST has no source timestamp. Start-of-request time bounds request latency;
        # this is an observed book, never claimed to be a Coinbase executable quote.
        if time.time()-started > 2: raise ValueError('Contract book request delayed')
        return {'UP':dict(bid=yes,ask=1-no,time=started,fee_per_contract=fee),
                'DOWN':dict(bid=no,ask=1-yes,time=started,fee_per_contract=fee)}


class ReferenceFeed:
    """Thread-safe source-time tick buffer. Reconnect clears uncertain history."""
    def __init__(self, kalshi=None, cfb_username='', cfb_key=''):
        self.kalshi, self.username, self.key = kalshi, cfb_username, cfb_key
        self.lock, self.stop_event = threading.Lock(), threading.Event()
        self.ticks = {i:deque(maxlen=1000) for i in ('BRTI','ETHUSD_RTI')}
        self.error = 'Reference feed warming up'
        self.socket = None

    def ingest(self, frame, received):
        if frame.get('type') == 'cfbenchmarks_value':
            frame=json.loads(frame['msg']['data'])
        if frame.get('type') != 'value': return
        index=frame['id']
        if index not in self.ticks: return
        if frame.get('repeatOfPreviousValue') or frame.get('amendTime'):
            raise ValueError('Repeated or amended reference tick requires recovery')
        stamp,price=number(float(frame['time']))/1000,number(float(frame['value']))
        if price <= 0 or not 0 <= received-stamp <= 2:
            raise ValueError('Reference tick stale or clock skewed')
        with self.lock:
            rows=self.ticks[index]
            if rows and stamp <= rows[-1]['time']: return
            rows.append(dict(time=stamp,price=price))
            self.error=''

    def snapshot(self,index):
        with self.lock: return list(self.ticks[index])

    def start(self):
        import websocket  # optional prediction dependency, not needed by spot bot
        def loop():
            delay=1
            while not self.stop_event.is_set():
                try:
                    if self.username and self.key:
                        self.socket=websocket.create_connection('wss://www.cfbenchmarks.com/ws/v4',
                            subprotocols=['cfb',self.username,self.key],timeout=5)
                        for index in self.ticks:
                            self.socket.send(json.dumps(dict(type='subscribe',stream='value',id=index)))
                    else:
                        path='/trade-api/ws/v2'
                        self.socket=websocket.create_connection('wss://external-api-ws.kalshi.com'+path,
                            header=self.kalshi.headers(path),timeout=5)
                        self.socket.send(json.dumps(dict(id=1,cmd='subscribe',params=dict(
                            channels=['cfbenchmarks_value'],index_ids=list(self.ticks)))))
                    delay=1
                    while not self.stop_event.is_set():
                        data=json.loads(self.socket.recv())
                        if data.get('type')=='error': raise ValueError('Reference subscription not authorized')
                        self.ingest(data,time.time())
                except Exception:
                    with self.lock:
                        self.error='Reference feed disconnected, unavailable or unauthorized'
                        for rows in self.ticks.values(): rows.clear()
                finally:
                    if self.socket:
                        try: self.socket.close()
                        except Exception: pass
                self.stop_event.wait(delay)
                delay=min(delay*2,30)
        self.thread=threading.Thread(target=loop,daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.socket:
            try: self.socket.close()
            except Exception: pass
        if hasattr(self,'thread'): self.thread.join(timeout=6)
