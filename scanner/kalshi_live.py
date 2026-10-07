"""Authenticated Kalshi Predictions trading client.

Uses the documented production Trade API. Supports Ed25519 (recommended) and
RSA private keys. No withdrawal/transfer endpoints are implemented here.
"""
import base64, json, math, time, uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

PROD_BASE = "https://external-api.kalshi.com/trade-api/v2"
DEMO_BASE = "https://external-api.demo.kalshi.co/trade-api/v2"

class KalshiTradeError(RuntimeError): pass

def _private_key(env):
    path=(env.get('KALSHI_PRIVATE_KEY_PATH') or '').strip()
    raw=''
    if path:
        raw=Path(path).expanduser().read_text(encoding='utf-8')
    else:
        raw=(env.get('KALSHI_PRIVATE_KEY') or '').replace('\\n','\n')
    if not raw.strip(): raise KalshiTradeError('KALSHI_PRIVATE_KEY_PATH or KALSHI_PRIVATE_KEY is not set')
    return serialization.load_pem_private_key(raw.encode(),password=None)

class KalshiLive:
    def __init__(self, env, timeout=15):
        self.key_id=(env.get('KALSHI_API_KEY_ID') or env.get('KALSHI_API_KEY') or '').strip()
        if not self.key_id: raise KalshiTradeError('KALSHI_API_KEY_ID is not set')
        self.key=_private_key(env); self.timeout=timeout
        self.base=(env.get('KALSHI_API_BASE') or PROD_BASE).rstrip('/')
        self.live_confirm=(env.get('KALSHI_LIVE_TRADING') or '').upper()=='YES'

    def _signature(self, ts, method, path):
        msg=(ts+method.upper()+path.split('?',1)[0]).encode()
        if isinstance(self.key, Ed25519PrivateKey): sig=self.key.sign(msg)
        else:
            sig=self.key.sign(msg,padding.PSS(mgf=padding.MGF1(hashes.SHA256()),salt_length=padding.PSS.DIGEST_LENGTH),hashes.SHA256())
        return base64.b64encode(sig).decode()

    def request(self, method, path, body=None):
        ts=str(int(time.time()*1000)); full='/trade-api/v2'+path
        headers={'Accept':'application/json','Content-Type':'application/json','User-Agent':'PredictionMarkets-Signal/3.0',
                 'KALSHI-ACCESS-KEY':self.key_id,'KALSHI-ACCESS-TIMESTAMP':ts,
                 'KALSHI-ACCESS-SIGNATURE':self._signature(ts,method,full)}
        data=json.dumps(body,separators=(',',':')).encode() if body is not None else None
        req=Request(self.base+path,data=data,headers=headers,method=method.upper())
        try:
            with urlopen(req,timeout=self.timeout) as r: return json.load(r)
        except HTTPError as e:
            detail=e.read().decode(errors='replace')[:1000]
            raise KalshiTradeError(f'Kalshi HTTP {e.code}: {detail}') from e

    def balance(self): return self.request('GET','/portfolio/balance')

    def orderbook(self,ticker):
        req=Request(self.base+'/markets/'+ticker+'/orderbook',headers={'Accept':'application/json','User-Agent':'PredictionMarkets-Signal/3.0'})
        with urlopen(req,timeout=self.timeout) as r: return (json.load(r).get('orderbook_fp') or {})

    @staticmethod
    def _levels(book, side): return book.get(side+'_dollars') or []

    def touch(self,ticker):
        """Return best YES bid/ask inferred from Kalshi's YES/NO bid books."""
        b=self.orderbook(ticker)
        yes=[float(x[0]) for x in self._levels(b,'yes') if x]
        no=[float(x[0]) for x in self._levels(b,'no') if x]
        yes_bid=max(yes) if yes else None
        # A NO bid at n implies a YES ask at 1-n.
        yes_ask=(1-max(no)) if no else None
        if yes_bid is None or yes_ask is None: raise KalshiTradeError('No executable two-sided orderbook')
        return yes_bid,yes_ask

    def _submit(self,ticker,book_side,count,price,reduce_only=False):
        if not self.live_confirm: raise KalshiTradeError('KALSHI_LIVE_TRADING=YES is required for real orders')
        body={'ticker':ticker,'side':book_side,'count':f'{count:.2f}','price':f'{price:.4f}',
              'time_in_force':'immediate_or_cancel','self_trade_prevention_type':'taker_at_cross',
              'client_order_id':str(uuid.uuid4()),'reduce_only':bool(reduce_only)}
        return self.request('POST','/portfolio/events/orders',body)

    def enter(self,ticker,direction,amount_usd):
        bid,ask=self.touch(ticker)
        if direction=='UP': side,price,cost='bid',ask,ask
        elif direction=='DOWN': side,price,cost='ask',bid,1-bid
        else: raise KalshiTradeError('Direction must be UP or DOWN')
        if cost<=0: raise KalshiTradeError('Invalid market price')
        count=math.floor((float(amount_usd)/cost)*100)/100
        if count<0.01: raise KalshiTradeError('Amount is too small for current price')
        return self._submit(ticker,side,count,price,False),count,price

    def close(self,ticker,direction,count):
        bid,ask=self.touch(ticker)
        # Long YES closes by selling YES => ask. Long NO closes by selling NO => bid.
        side,price=('ask',bid) if direction=='UP' else ('bid',ask)
        return self._submit(ticker,side,float(count),price,True),float(count),price
