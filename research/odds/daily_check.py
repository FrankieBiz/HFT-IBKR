"""Daily 200-day SMA vs monthly 10-month rule, 2017-07..2023-06 (before the study holdout).

FRED SP500 daily closes are price-only (no dividends) and close-only, so the daily rule
here fills at the NEXT close (the live system fills at the next open). Cash earns 0%.

Reproduce (data is downloaded, never committed):
    mkdir -p .research-output/odds && cd .research-output/odds
    curl -L -o sp500.csv https://datahub.io/core/s-and-p-500/r/data.csv
    curl -L -o fred_sp500.csv "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500"
    python3 -m venv .venv && .venv/bin/pip install numpy pandas
    .venv/bin/python ../../research/odds/base_rates.py
    .venv/bin/python ../../research/odds/daily_check.py
"""
import numpy as np, pandas as pd
d = pd.read_csv('fred_sp500.csv', parse_dates=['observation_date'], na_values='.').dropna()
d = d.rename(columns={'observation_date': 'date', 'SP500': 'px'}).set_index('date')['px']
d = d[:'2023-06-30']
sma = d.rolling(200).mean()
sig = (d > sma).astype(float)
pos = sig.shift(1)                                    # decided at close t, held from t+1
ret = d.pct_change()
start = '2017-07-01'
r, p = ret[start:], pos[start:]
cost = 0.0005 * p.diff().abs().fillna(0)
tim = r * p - cost
def summary(x, label):
    w = (1 + x).cumprod(); dd = (1 - w / w.cummax()).max()
    yrs = len(x) / 252
    print(f"  {label:28s} CAGR {w.iloc[-1] ** (1 / yrs) - 1:6.1%}  maxDD {dd:6.1%}  vol {x.std() * np.sqrt(252):5.1%}")
print('Daily 200-day SMA, 2017-07..2023-06 (price only):')
summary(r, 'buy-and-hold'); summary(tim, '200-day rule')
switches = int(p.diff().abs().sum()); print(f"  switches {switches} ({switches / (len(r) / 252):.1f}/yr), invested {p.mean():.0%}")
flips = p.diff().abs(); sw = flips[flips > 0].index
print('  switch dates:', ', '.join(f"{t:%Y-%m-%d}{'+' if p[t] > 0 else '-'}" for t in sw))

m = pd.read_csv('sp500.csv', parse_dates=['Date']).set_index('Date')['SP500']
m = m[m > 0]
msig = (m > m.rolling(10).mean()).astype(float).shift(1)
mret = m.pct_change()
mr, mp = mret['2017-07-01':'2023-06-30'], msig['2017-07-01':'2023-06-30']
mt = mr * mp - 0.0005 * mp.diff().abs().fillna(0)
def msummary(x, label):
    w = (1 + x).cumprod(); dd = (1 - w / w.cummax()).max()
    print(f"  {label:28s} CAGR {w.iloc[-1] ** (12 / len(x)) - 1:6.1%}  maxDD {dd:6.1%}")
print('Monthly-average 10-month rule, same window (price only):')
msummary(mr, 'buy-and-hold'); msummary(mt, '10-month rule')
