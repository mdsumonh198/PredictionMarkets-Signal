import json, sqlite3, time
from pathlib import Path

DEFAULTS={"mode":"signal","enabled":False,"amount_usd":10.0,"btc":True,"eth":True}
class Control:
    def __init__(self,path='data/kalshi_btc_eth_15m.sqlite'):
        Path(path).parent.mkdir(parents=True,exist_ok=True); self.db=sqlite3.connect(path,timeout=10)
        self.db.execute('CREATE TABLE IF NOT EXISTS bot_settings(k TEXT PRIMARY KEY,v TEXT NOT NULL)')
        self.db.execute('''CREATE TABLE IF NOT EXISTS trade_log(id INTEGER PRIMARY KEY AUTOINCREMENT,ticker TEXT,coin TEXT,stage TEXT,action TEXT,direction TEXT,amount REAL,status TEXT,price REAL,pnl REAL,note TEXT,created REAL)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS live_positions(ticker TEXT PRIMARY KEY,coin TEXT,direction TEXT,count REAL,entry_price REAL,order_id TEXT,status TEXT,created REAL,updated REAL)'''); self.db.commit()
        for k,v in DEFAULTS.items(): self.db.execute('INSERT OR IGNORE INTO bot_settings(k,v) VALUES(?,?)',(k,json.dumps(v)))
        self.db.commit()
    def get(self):
        d=dict(DEFAULTS)
        for k,v in self.db.execute('SELECT k,v FROM bot_settings'):
            try:d[k]=json.loads(v)
            except:pass
        return d
    def set(self,**kw):
        for k,v in kw.items():
            if k in DEFAULTS:self.db.execute('INSERT OR REPLACE INTO bot_settings(k,v) VALUES(?,?)',(k,json.dumps(v)))
        self.db.commit(); return self.get()
    def log(self,**x):
        keys=['ticker','coin','stage','action','direction','amount','status','price','pnl','note','created']; x.setdefault('created',time.time())
        self.db.execute('INSERT INTO trade_log('+','.join(keys)+') VALUES('+','.join('?'*len(keys))+')',tuple(x.get(k) for k in keys));self.db.commit()

    def position(self,ticker):
        r=self.db.execute('SELECT ticker,coin,direction,count,entry_price,order_id,status,created,updated FROM live_positions WHERE ticker=?',(ticker,)).fetchone()
        return dict(zip(['ticker','coin','direction','count','entry_price','order_id','status','created','updated'],r)) if r else None
    def save_position(self,**x):
        now=time.time(); x.setdefault('created',now); x.setdefault('updated',now)
        self.db.execute('INSERT OR REPLACE INTO live_positions(ticker,coin,direction,count,entry_price,order_id,status,created,updated) VALUES(?,?,?,?,?,?,?,?,?)',(x['ticker'],x['coin'],x['direction'],x['count'],x.get('entry_price'),x.get('order_id'),x.get('status','OPEN'),x['created'],x['updated'])); self.db.commit()
    def close_position(self,ticker,status='CLOSED'):
        self.db.execute('UPDATE live_positions SET status=?,updated=? WHERE ticker=?',(status,time.time(),ticker)); self.db.commit()
