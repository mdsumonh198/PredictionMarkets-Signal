"""Non-trading Coinbase access verifier.

This module deliberately DOES NOT place orders. Coinbase Advanced Trade API
credentials can authenticate Coinbase brokerage APIs, but that alone does not
prove Coinbase Financial Markets Prediction Markets order routing is exposed
through the documented API.
"""
import argparse
import os
from pathlib import Path


def load_env(path='.env'):
    out = {}
    p = Path(path)
    if p.exists():
        for raw in p.read_text(encoding='utf-8').splitlines():
            raw = raw.strip()
            if raw and not raw.startswith('#') and '=' in raw:
                k, v = raw.split('=', 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def check(env_path='.env'):
    env = load_env(env_path)
    key = os.environ.get('COINBASE_API_KEY') or env.get('COINBASE_API_KEY')
    secret = os.environ.get('COINBASE_PRIVATE_KEY') or env.get('COINBASE_PRIVATE_KEY')
    result = {
        'authentication': False,
        'read_access': False,
        'prediction_market_order_api': False,
        'real_order_placed': False,
        'detail': '',
    }
    if not key or not secret:
        result['detail'] = 'COINBASE_API_KEY / COINBASE_PRIVATE_KEY missing'
        return result
    try:
        from coinbase.rest import RESTClient
        client = RESTClient(api_key=key, api_secret=secret)
        client.get_accounts(limit=1)
        result['authentication'] = True
        result['read_access'] = True
        result['detail'] = ('Coinbase API authentication/read access works. '
                            'No documented Coinbase Prediction Markets order endpoint is configured in this bot.')
    except Exception as exc:
        result['detail'] = 'Coinbase API check failed: ' + str(exc)[:300]
    return result


def main():
    p = argparse.ArgumentParser(description='Safe Coinbase API capability check; never places an order')
    p.add_argument('--env', default='.env')
    args = p.parse_args()
    r = check(args.env)
    print('Coinbase Authentication:', 'PASS' if r['authentication'] else 'FAIL')
    print('Read Access:', 'PASS' if r['read_access'] else 'FAIL')
    print('Prediction Market Buy/Sell API:', 'PASS' if r['prediction_market_order_api'] else 'NOT VERIFIED / NOT CONFIGURED')
    print('Real Order Placed: NO')
    print('Detail:', r['detail'])

if __name__ == '__main__':
    main()
