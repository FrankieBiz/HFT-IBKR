"""Base rates for a 10-month SMA long/cash rule on the S&P 500 total-return index.

Shiller monthly data (prices are monthly AVERAGES of daily closes, which smooths
returns and flatters trend rules; treat results as an upper bound for timing).
Cash earns 0% to match the shadow system. Cost: 5 bp per side on each switch.

Reproduce (data is downloaded, never committed):
    mkdir -p .research-output/odds && cd .research-output/odds
    curl -L -o sp500.csv https://datahub.io/core/s-and-p-500/r/data.csv
    curl -L -o fred_sp500.csv "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"
    python3 -m venv .venv && .venv/bin/pip install numpy pandas
    .venv/bin/python ../../research/odds/base_rates.py
    .venv/bin/python ../../research/odds/daily_check.py
"""
import numpy as np, pandas as pd

df = pd.read_csv('sp500.csv', parse_dates=['Date'])
df = df[df['SP500'] > 0].copy()
last_div = df.loc[df['Dividend'] > 0, 'Date'].max()
df.loc[df['Date'] > last_div, 'Dividend'] = np.nan
df['Dividend'] = df['Dividend'].ffill()
p, d = df['SP500'].to_numpy(), df['Dividend'].to_numpy()
r = np.r_[np.nan, (p[1:] + d[1:] / 12) / p[:-1] - 1]          # monthly total return
tr = np.nancumprod(np.r_[1.0, 1 + r[1:]])                        # total-return index
sma = pd.Series(tr).rolling(10).mean().to_numpy()
signal = tr > sma                                                # known at month-end t
pos = np.r_[False, signal[:-1]]                                  # held during month t+1
pos[:10] = False
switch = np.r_[False, pos[1:] != pos[:-1]]
COST = 0.0005
rt = np.where(pos, r, 0.0) - np.where(switch, COST, 0.0)
dates = df['Date'].to_numpy()
valid = np.arange(len(r)) >= 11                                  # after warmup

def stats(ret):
    ret = ret[~np.isnan(ret)]
    w = np.cumprod(1 + ret); dd = 1 - w / np.maximum.accumulate(w)
    yrs = len(ret) / 12
    return dict(cagr=w[-1] ** (1 / yrs) - 1, vol=ret.std() * np.sqrt(12),
                sharpe0=ret.mean() / ret.std() * np.sqrt(12), maxdd=dd.max())

def window_rates(start_year, horizon):
    idx = np.where(valid & (pd.DatetimeIndex(dates).year >= start_year))[0]
    out = {'n': 0, 'tim_pos': 0, 'bh_pos': 0, 'beat_ret': 0, 'lower_dd': 0, 'better_sr': 0, 'alpha_pos': 0}
    for s in idx:
        e = s + horizon
        if e > len(r):
            break
        a, b = rt[s:e], r[s:e]
        wa, wb = np.prod(1 + a), np.prod(1 + b)
        dda = (1 - np.cumprod(1 + a) / np.maximum.accumulate(np.cumprod(1 + a))).max()
        ddb = (1 - np.cumprod(1 + b) / np.maximum.accumulate(np.cumprod(1 + b))).max()
        sra = a.mean() / a.std() if a.std() > 0 else 0
        srb = b.mean() / b.std()
        beta = np.cov(a, b)[0, 1] / b.var(ddof=1)
        alpha = a.mean() - beta * b.mean()
        out['n'] += 1; out['tim_pos'] += wa > 1; out['bh_pos'] += wb > 1
        out['beat_ret'] += wa > wb; out['lower_dd'] += dda < ddb - 1e-12
        out['better_sr'] += sra > srb; out['alpha_pos'] += alpha > 0
    n = out.pop('n')
    return {k: round(100 * v / n) for k, v in out.items()} | {'windows': n}

print('Data', pd.Timestamp(dates[0]).date(), 'to', pd.Timestamp(dates[-1]).date(), '| dividends forward-filled after', last_div.date())
for start in (1881, 1950, 1990, 2010):
    m = valid & (pd.DatetimeIndex(dates).year >= start)
    t, b = stats(rt[m]), stats(r[m])
    inv = pos[m].mean(); sw = switch[m].sum() / (m.sum() / 12)
    print(f"\n== {start}-2026 full period: timing CAGR {t['cagr']:.1%} vol {t['vol']:.1%} Sharpe(0%) {t['sharpe0']:.2f} maxDD {t['maxdd']:.1%} "
          f"| B&H CAGR {b['cagr']:.1%} vol {b['vol']:.1%} Sharpe(0%) {b['sharpe0']:.2f} maxDD {b['maxdd']:.1%} | invested {inv:.0%}, switches/yr {sw:.1f}")
    for h in (12, 36, 60, 120):
        print(f"   {h//12:>2}y windows: {window_rates(start, h)}")
