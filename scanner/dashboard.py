import argparse, html, json, os, secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs
from scanner.control import Control

PAGE='''<!doctype html><html><head><meta name="viewport" content="width=device-width"><title>Prediction Bot Control</title><style>body{font-family:Arial;max-width:900px;margin:30px auto;padding:0 15px;background:#0b1020;color:#eef} .card{background:#151c31;padding:18px;border-radius:14px;margin:12px 0}button,input,select{font-size:16px;padding:10px;margin:6px}table{width:100%;border-collapse:collapse}td,th{padding:8px;border-bottom:1px solid #334} .ok{color:#6fda8a}.warn{color:#ffd166}</style></head><body><h1>BTC/ETH 15M Bot Control</h1><div class=card><b>Bot:</b> {enabled}<br><b>Mode:</b> {mode}<br><b>Amount:</b> ${amount:.2f} per entry</div><form class=card method=post><h3>Settings</h3><label>Mode <select name=mode><option value=signal {s1}>Signal Only</option><option value=paper {s2}>Paper Auto Trade</option><option value=live {s3}>Live Auto Trade</option></select></label><br><label>Fixed amount $ <input name=amount type=number min=1 step=.01 value="{amount}"></label><br><label><input type=checkbox name=btc {btc}> BTC</label><label><input type=checkbox name=eth {eth}> ETH</label><br><label><input type=checkbox name=enabled {checked}> Auto execution ON</label><br><button>Save Settings</button></form><div class=card><h3>Safety</h3>{safety}</div><div class=card><h3>Recent execution report</h3><table><tr><th>Coin</th><th>Stage</th><th>Action</th><th>Direction</th><th>$</th><th>Status</th><th>PnL</th></tr>{rows}</table></div></body></html>'''
class H(BaseHTTPRequestHandler):
 def auth(self):
  tok=os.environ.get('DASHBOARD_TOKEN',''); return bool(tok) and self.headers.get('Authorization')=='Bearer '+tok
 def do_GET(self):
  if not self.auth(): self.send_response(401);self.end_headers();self.wfile.write(b'Use Authorization: Bearer <DASHBOARD_TOKEN>');return
  c=Control(self.server.db); s=c.get(); rows=''.join('<tr>'+''.join('<td>'+html.escape(str(v if v is not None else ''))+'</td>' for v in r)+'</tr>' for r in c.db.execute('SELECT coin,stage,action,direction,amount,status,pnl FROM trade_log ORDER BY id DESC LIMIT 50'))
  live=os.environ.get('COINBASE_PREDICTION_LIVE_VERIFIED')=='YES'
  safety='<span class=ok>Live connector explicitly verified.</span>' if live else '<span class=warn>Live Auto Trade is locked until Coinbase Prediction Market programmatic order access is verified. Signal/Paper modes work normally.</span>'
  b=PAGE.format(enabled='ON' if s['enabled'] else 'OFF',mode=s['mode'].upper(),amount=float(s['amount_usd']),s1='selected' if s['mode']=='signal' else '',s2='selected' if s['mode']=='paper' else '',s3='selected' if s['mode']=='live' else '',btc='checked' if s['btc'] else '',eth='checked' if s['eth'] else '',checked='checked' if s['enabled'] else '',safety=safety,rows=rows).encode();self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(b)
 def do_POST(self):
  if not self.auth(): self.send_response(401);self.end_headers();return
  n=int(self.headers.get('Content-Length','0')); q=parse_qs(self.rfile.read(n).decode()); mode=q.get('mode',['signal'])[0]
  if mode=='live' and os.environ.get('COINBASE_PREDICTION_LIVE_VERIFIED')!='YES': mode='paper'
  try: amt=max(1.0,float(q.get('amount',['10'])[0]))
  except: amt=10
  Control(self.server.db).set(mode=mode,amount_usd=amt,btc='btc' in q,eth='eth' in q,enabled='enabled' in q);self.send_response(303);self.send_header('Location','/');self.end_headers()
 def log_message(self,*a):pass

def main():
 p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=8787);p.add_argument('--db',default='data/kalshi_btc_eth_15m.sqlite');a=p.parse_args();
 if not os.environ.get('DASHBOARD_TOKEN'): raise SystemExit('Set DASHBOARD_TOKEN first')
 srv=ThreadingHTTPServer((a.host,a.port),H);srv.db=a.db;print('Dashboard',a.host,a.port);srv.serve_forever()
if __name__=='__main__':main()
