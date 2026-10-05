"""Apply the spy-daily-v1 pre-registered decision rule to a released holdout report.

The rule (studies/spy-daily-v1/PREREGISTRATION.md) reads only the 2x-cost column:
Dominates, Risk-reducing or Dominated, and a negative trend return blocks every
"proceed" outcome. Other cost columns are printed as sensitivities only.
"""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

PRIMARY_MULTIPLIER = 2


def _column(rows, multiplier):
    matches = [row['result'] for row in rows if row['cost_multiplier'] == multiplier]
    if len(matches) != 1:
        raise ValueError(f'expected one {multiplier}x cost result')
    return matches[0]


def verdict(report):
    if report.get('mode') != 'offline_holdout_release':
        raise ValueError('a released holdout report is required')
    trend = _column(report['scenarios'], PRIMARY_MULTIPLIER)
    hold = _column(report['benchmarks']['buy_hold'], PRIMARY_MULTIPLIER)
    t_return, t_drawdown = Decimal(trend['total_return']), Decimal(trend['maximum_drawdown'])
    b_return, b_drawdown = Decimal(hold['total_return']), Decimal(hold['maximum_drawdown'])
    if t_drawdown >= b_drawdown:
        outcome = 'DOMINATED'
    elif t_return >= b_return:
        outcome = 'DOMINATES'
    else:
        outcome = 'RISK_REDUCING'
    proceed = outcome != 'DOMINATED' and t_return >= 0
    return {'outcome': outcome, 'proceed_to_shadow': proceed,
            'selected_lookback': report['selected_lookback'],
            'trend_2x': {'total_return': str(t_return), 'maximum_drawdown': str(t_drawdown),
                         'trade_count': trend['trade_count']},
            'buy_hold_2x': {'total_return': str(b_return), 'maximum_drawdown': str(b_drawdown)},
            'sensitivities_only': {f"{row['cost_multiplier']}x": {
                'trend_return': row['result']['total_return'],
                'buy_hold_return': _column(report['benchmarks']['buy_hold'], row['cost_multiplier'])['total_return']}
                for row in report['scenarios'] if row['cost_multiplier'] != PRIMARY_MULTIPLIER}}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('holdout', type=Path)
    args = parser.parse_args(argv)
    try:
        result = verdict(json.loads(args.holdout.read_text()))
    except (OSError, ValueError, KeyError, TypeError, ArithmeticError) as error:
        print(f'verdict error: {error}', file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
