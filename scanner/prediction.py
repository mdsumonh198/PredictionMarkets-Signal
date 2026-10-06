"""Offline BTC/ETH final-two-minute research. Never emits live trade advice.

Input must contain the contract's own reference ticks, not substitute spot ticks.
Thresholds are research hypotheses, not fitted probabilities or profitable rules.
"""
import argparse
import json
import math
from pathlib import Path
from statistics import median


def number(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError('Expected finite numeric data')
    return float(value)


def review(snapshot):
    asset = snapshot['asset']
    if asset not in ('BTC', 'ETH'):
        raise ValueError('Prediction research supports BTC and ETH only')
    now, start, expiry = (number(snapshot[k]) for k in ('now', 'start', 'expiry'))
    if expiry - start != 900:
        raise ValueError('A verified 15-minute contract is required')
    target = number(snapshot['target'])
    if target <= 0 or not snapshot['contract_id'] or not snapshot['reference_index'] or not snapshot['rules_url']:
        raise ValueError('Contract ID, positive target, reference index and rules URL required')
    if snapshot['settlement'] != 'final_60_seconds_average':
        raise ValueError('Unsupported settlement rule; verify the actual contract')
    remaining = expiry - now
    result = dict(asset=asset, contract_id=snapshot['contract_id'], seconds_remaining=remaining,
                  status='RESEARCH_ONLY', trade_authorized=False, direction=None, reasons=[])
    # Trigger once at expiry minus 120s; late entry into the averaging minute is excluded.
    if not 60 < remaining <= 120:
        result['reasons'].append('Outside final-two-minute evaluation window')
        return result
    ticks = [(number(t['time']), number(t['price'])) for t in snapshot['ticks']]
    if any(p <= 0 or t > now for t, p in ticks):
        raise ValueError('Positive reference prices and no future observations required')
    if any(b[0] <= a[0] for a, b in zip(ticks, ticks[1:])):
        raise ValueError('Reference ticks must have unique increasing timestamps')
    ticks = [(t, p) for t, p in ticks if now - 120 <= t <= now]
    if len(ticks) < 119 or len({int(t) for t,_ in ticks}) != len(ticks) or ticks[0][0] > now - 118 or now - ticks[-1][0] > 2 or any(b[0]-a[0] > 2 for a,b in zip(ticks,ticks[1:])):
        result['reasons'].append('Reference feed stale, sparse or incomplete')
        return result
    prices = [p for _, p in ticks]
    recent = [p for t,p in ticks if t >= now-30]
    previous = [p for t,p in ticks if now-60 <= t < now-30]
    earlier = [p for t,p in ticks if now-90 <= t < now-60]
    if not recent or not previous or not earlier:
        result['reasons'].append('Insufficient trend windows')
        return result
    # Robust windows reduce sensitivity to one isolated price spike.
    a,b,c = map(median, (earlier, previous, recent))
    trend = 'UP' if a < b < c else 'DOWN' if a > b > c else None
    noise = median(abs(y-x) for x,y in zip(prices,prices[1:]))
    margin = max(target * 0.0001, noise * 3)
    # The display is a trailing average, not an exchange last-trade price.
    source_end=ticks[-1][0]
    average_prices = [p for t,p in ticks if source_end-60 <= t < source_end]
    if len(average_prices)<59:
        result['reasons'].append('Reference feed incomplete for trailing average')
        return result
    reference_average = sum(average_prices)/len(average_prices)
    distance = reference_average-target
    target_side = 'UP' if distance > margin else 'DOWN' if distance < -margin else None
    result.update(trend=trend, target_side=target_side, reference_price=prices[-1], reference_average_60s=reference_average,
                  target=target, target_distance=distance, research_buffer=margin)
    if trend is None or target_side != trend:
        result['reasons'].append('Trend and buffered target side do not agree')
        return result
    # Direction is an observation only; no fabricated confidence or win percentage.
    result['direction'] = trend
    quote = snapshot['contract_quotes'][trend]
    bid, ask, observed, fee = (number(quote[k]) for k in ('bid','ask','time','fee_per_contract'))
    if not 0 <= bid <= ask < 1 or ask <= 0 or fee < 0 or fee+ask >= 1:
        raise ValueError('Invalid executable contract quote or fee')
    if not 0 <= now-observed <= 2:
        result['reasons'].append('Contract quote stale or from future')
        return result
    result.update(contract_ask=ask, contract_spread=ask-bid,
                  break_even_probability=ask+fee, maximum_loss_per_contract=ask+fee,
                  profit_if_correct=1-ask-fee)
    result['reasons'].append('Direction requires historical calibration against actual settlement and net costs before live use')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, help='Verified contract/reference snapshot JSON')
    args = parser.parse_args()
    try:
        result = review(json.loads(Path(args.snapshot).read_text(encoding='utf-8')))
    except (ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
