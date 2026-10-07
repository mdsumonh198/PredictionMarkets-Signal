import argparse, hashlib, hmac, html, os
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs
from scanner.control import Control

CSS='''*{box-sizing:border-box}body{font-family:Arial,sans-serif;max-width:1050px;margin:28px auto;padding:0 16px;background:#0b1020;color:#eef}h1{margin-bottom:6px}.sub{color:#9aa7c7;margin-bottom:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.card{background:#151c31;padding:18px;border-radius:14px;margin:12px 0;border:1px solid #25304d}.metric{font-size:25px;font-weight:700;margin-top:8px}.pill{display:inline-block;padding:5px 10px;border-radius:999px;background:#25304d}button,input,select{font-size:16px;padding:10px;margin:6px 4px;border-radius:8px;border:1px solid #3a4768;background:#0f1629;color:#fff}button{cursor:pointer;background:#315efb;border:0;font-weight:700}table{width:100%;border-collapse:collapse;overflow:auto}td,th{padding:9px;border-bottom:1px solid #334;text-align:left}.ok{color:#6fda8a}.warn{color:#ffd166}.bad{color:#ff7b7b}.login{max-width:420px;margin:14vh auto}.small{font-size:13px;color:#9aa7c7}.logout{float:right;background:#2a334b}'''

def session_value(token):
    return hmac.new(token.encode(), b'prediction-dashboard-session-v1', hashlib.sha256).hexdigest()

def login_page(error=''):
    msg=f'<p class="bad">{html.escape(error)}</p>' if error else ''
    return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Bot Dashboard Login</title><style>{CSS}</style></head><body><div class="card login"><h2>Prediction Bot Dashboard</h2><p class="sub">Enter your dashboard token to continue.</p>{msg}<form method="post" action="/login"><input style="width:100%;margin:8px 0" name="token" type="password" placeholder="Dashboard token" required autofocus><button style="width:100%;margin:8px 0">Login</button></form><p class="small">Keep this token private. For production use, put the dashboard behind HTTPS.</p></div></body></html>'''

def page(s, rows, live):
    safety='<span class="ok">Live connector explicitly verified.</span>' if live else '<span class="warn">Live Auto Trade is LOCKED. Coinbase Prediction Market programmatic Buy/Sell access has not been verified. Signal and Paper modes are available.</span>'
    total=sum(1 for _ in rows); paper=sum(1 for r in rows if str(r[5])=='PAPER'); pnl=sum(float(r[6] or 0) for r in rows)
    trs=''.join('<tr>'+''.join('<td>'+html.escape(str(v if v is not None else ''))+'</td>' for v in r)+'</tr>' for r in rows) or '<tr><td colspan="7" class="small">No execution records yet.</td></tr>'
    return f'''<!doctype html><html><head><meta name="viewport" content="width=device-width"><meta http-equiv="refresh" content="30"><title>Prediction Bot Control</title><style>{CSS}</style></head><body><form method="post" action="/logout"><button class="logout">Logout</button></form><h1>BTC/ETH 15M Bot Control</h1><div class="sub">Prediction Market signal & execution dashboard · auto refresh 30s</div><div class="grid"><div class="card"><div>Auto Execution</div><div class="metric {'ok' if s['enabled'] else 'warn'}">{'ON' if s['enabled'] else 'OFF'}</div></div><div class="card"><div>Mode</div><div class="metric">{html.escape(str(s['mode']).upper())}</div></div><div class="card"><div>Entry Amount</div><div class="metric">${float(s['amount_usd']):.2f}</div></div><div class="card"><div>Recent Records</div><div class="metric">{total}</div><div class="small">Paper: {paper} · PnL: ${pnl:.2f}</div></div></div><form class="card" method="post" action="/settings"><h3>Settings</h3><label>Mode <select name="mode"><option value="signal" {'selected' if s['mode']=='signal' else ''}>Signal Only</option><option value="paper" {'selected' if s['mode']=='paper' else ''}>Paper Auto Trade</option><option value="live" {'selected' if s['mode']=='live' else ''}>Live Auto Trade</option></select></label><label>Fixed amount $ <input name="amount" type="number" min="1" step="0.01" value="{float(s['amount_usd']):.2f}"></label><br><label><input type="checkbox" name="btc" {'checked' if s['btc'] else ''}> BTC</label><label><input type="checkbox" name="eth" {'checked' if s['eth'] else ''}> ETH</label><label><input type="checkbox" name="enabled" {'checked' if s['enabled'] else ''}> Auto execution ON</label><br><button>Save Settings</button></form><div class="card"><h3>Safety</h3>{safety}</div><div class="card"><h3>Recent execution report</h3><div style="overflow-x:auto"><table><tr><th>Coin</th><th>Stage</th><th>Action</th><th>Direction</th><th>$</th><th>Status</th><th>PnL</th></tr>{trs}</table></div></div></body></html>'''

class H(BaseHTTPRequestHandler):
    def token(self): return os.environ.get('DASHBOARD_TOKEN','')
    def authed(self):
        raw=self.headers.get('Cookie',''); jar=cookies.SimpleCookie();
        try: jar.load(raw)
        except: return False
        got=jar.get('dash_session'); tok=self.token()
        return bool(tok and got and hmac.compare_digest(got.value,session_value(tok)))
    def send_html(self,body,status=200,extra=None):
        b=body.encode(); self.send_response(status); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.send_header('Cache-Control','no-store')
        if extra:
            for k,v in extra:self.send_header(k,v)
        self.end_headers(); self.wfile.write(b)
    def form(self):
        n=int(self.headers.get('Content-Length','0')); return parse_qs(self.rfile.read(n).decode(errors='replace'))
    def redirect(self,path,extra=None):
        self.send_response(303); self.send_header('Location',path)
        if extra:
            for k,v in extra:self.send_header(k,v)
        self.end_headers()
    def do_GET(self):
        if self.path.startswith('/health'):
            self.send_html('OK'); return
        if not self.authed(): self.send_html(login_page()); return
        c=Control(self.server.db); s=c.get(); rows=list(c.db.execute('SELECT coin,stage,action,direction,amount,status,pnl FROM trade_log ORDER BY id DESC LIMIT 50'))
        live=os.environ.get('COINBASE_PREDICTION_LIVE_VERIFIED')=='YES'; self.send_html(page(s,rows,live))
    def do_POST(self):
        if self.path=='/login':
            q=self.form(); supplied=q.get('token',[''])[0]; tok=self.token()
            if tok and hmac.compare_digest(supplied,tok):
                ck=f'dash_session={session_value(tok)}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200'; self.redirect('/', [('Set-Cookie',ck)]); return
            self.send_html(login_page('Invalid dashboard token.'),401); return
        if self.path=='/logout':
            self.redirect('/', [('Set-Cookie','dash_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')]); return
        if not self.authed(): self.send_html(login_page('Please log in first.'),401); return
        if self.path=='/settings':
            q=self.form(); mode=q.get('mode',['signal'])[0]
            if mode not in ('signal','paper','live'): mode='signal'
            if mode=='live' and os.environ.get('COINBASE_PREDICTION_LIVE_VERIFIED')!='YES': mode='paper'
            try: amt=max(1.0,float(q.get('amount',['10'])[0]))
            except: amt=10.0
            Control(self.server.db).set(mode=mode,amount_usd=amt,btc='btc' in q,eth='eth' in q,enabled='enabled' in q); self.redirect('/'); return
        self.send_error(404)
    def log_message(self,*a): pass

def main():
    p=argparse.ArgumentParser(); p.add_argument('--host',default='127.0.0.1'); p.add_argument('--port',type=int,default=8787); p.add_argument('--db',default='data/kalshi_btc_eth_15m.sqlite'); a=p.parse_args()
    if not os.environ.get('DASHBOARD_TOKEN'): raise SystemExit('Set DASHBOARD_TOKEN first')
    srv=ThreadingHTTPServer((a.host,a.port),H); srv.db=a.db; print('Dashboard',a.host,a.port,flush=True); srv.serve_forever()
if __name__=='__main__': main()
