"""Offline close-to-next-open research replay; results are exploratory."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .risk import DrawdownState, admit, size_entry
from .serde import InputError, fixed_decimal
from .strategy import TrendSignal, trend_signals

ZERO = Decimal(0)


@dataclass(frozen=True)
class Receivable:
    pay_date: date
    amount: Decimal


@fixed_decimal
def simulate(bars, config, evaluation_start, strategy='trend', multiplier=1):
    if config.mode != 'simulation' or config.symbol != 'SPY':
        raise InputError('only offline SPY simulation is supported')
    if strategy not in ('trend', 'buy_hold'):
        raise InputError('unknown strategy')
    if type(multiplier) is not int or multiplier not in (1, 2, 5):
        raise InputError('unknown cost scenario')
    sessions = [bar.session for bar in bars]
    if evaluation_start not in sessions:
        raise InputError('evaluation start must be a supplied session')
    start = sessions.index(evaluation_start)
    if start < config.lookback:
        raise InputError('evaluation start requires lookback prior completed sessions')
    signals = trend_signals(bars, config.lookback)
    cash = config.initial_cash
    shares = 0
    receivables = []
    drawdown = DrawdownState(config.initial_cash, ZERO, False)
    previous_nav = config.initial_cash
    trades, rejections, equity_curve = [], [], []
    fees_paid = friction_paid = ZERO
    exposure_sessions = 0

    for index in range(start, len(bars)):
        bar, previous = bars[index], bars[index - 1]
        cash += sum((r.amount for r in receivables if r.pay_date <= bar.session), ZERO)
        receivables = [r for r in receivables if r.pay_date > bar.session]
        # Entitlement belongs to inventory held before ex-date trading.
        if bar.dividend and shares:
            receivables.append(Receivable(bar.dividend_pay_date, shares * bar.dividend))
        unpaid = sum((r.amount for r in receivables), ZERO)
        open_nav = cash + shares * bar.open + unpaid
        drawdown = drawdown.mark(open_nav, config.max_drawdown)
        target = signals[index - 1] if strategy == 'trend' else TrendSignal.LONG
        side, quantity, requested = None, 0, 0
        sizing_reason = 'ACCEPTED'

        if target == TrendSignal.LONG and shares == 0:
            side = 'BUY'
            requested = int(previous_nav * config.target_fraction / previous.close)
            sized = size_entry(min(requested, config.max_shares), cash, open_nav, bar.open,
                               previous.volume, config, multiplier, drawdown.halted)
            quantity, sizing_reason = sized.quantity, sized.reason
            if quantity and quantity != requested:
                sizing_reason = 'REDUCED_TO_LIMITS'
        elif target == TrendSignal.CASH and shares:
            side, quantity, requested = 'SELL', shares, shares

        if side:
            decision = admit(side=side, quantity=quantity, cash=cash, shares=shares,
                             nav=open_nav, open_price=bar.open, previous_volume=previous.volume,
                             config=config, multiplier=multiplier, halted=drawdown.halted) if quantity else None
            if decision is None or not decision.accepted:
                rejections.append({'session': bar.session, 'signal_session': previous.session,
                                   'side': side, 'requested_quantity': requested,
                                   'reason': decision.reason if decision else sizing_reason})
            else:
                fill = decision.estimate
                if side == 'BUY':
                    cash -= fill.notional + fill.fees
                    shares += quantity
                else:
                    cash += fill.notional - fill.fees
                    shares -= quantity
                if cash < 0 or shares < 0:
                    raise RuntimeError('risk admission violated portfolio invariants')
                fees_paid += fill.fees
                friction_paid += fill.friction
                trades.append({'session': bar.session, 'signal_session': previous.session,
                               'side': side, 'requested_quantity': requested, 'quantity': quantity,
                               'fill_price': fill.price, 'reference_open': bar.open,
                               'commission': fill.commission, 'exchange_fee': fill.exchange_fee,
                               'sell_fee': fill.sell_fee, 'fees': fill.fees,
                               'price_friction': fill.friction, 'sizing_reason': sizing_reason})
                drawdown = drawdown.mark(cash + shares * bar.open + unpaid, config.max_drawdown)

        nav = cash + shares * bar.close + unpaid
        drawdown = drawdown.mark(nav, config.max_drawdown)
        # Counts close inventory plus any position held across this session's open.
        held_during_session = shares > 0 or (side == 'SELL' and requested > 0)
        exposure_sessions += int(held_during_session)
        equity_curve.append({'session': bar.session, 'open_nav': open_nav, 'nav': nav,
                             'cash': cash, 'shares': shares, 'receivables': unpaid,
                             'halted': drawdown.halted})
        previous_nav = nav

    final = equity_curve[-1]
    return {
        'strategy': f'sma_{config.lookback}_long_cash' if strategy == 'trend' else 'buy_hold_same_risk',
        'evaluation_start': evaluation_start, 'evaluation_end': bars[-1].session,
        'evaluated_sessions': len(equity_curve), 'exposure_sessions': exposure_sessions,
        'total_return': final['nav'] / config.initial_cash - 1,
        'maximum_drawdown': drawdown.maximum, 'halted': drawdown.halted,
        'fees_paid': fees_paid, 'price_friction': friction_paid,
        'modeled_execution_cost': fees_paid + friction_paid,
        'trade_count': len(trades), 'rejection_count': len(rejections),
        'trades': trades, 'rejections': rejections, 'equity_curve': equity_curve,
        'final': {key: final[key] for key in ('cash', 'shares', 'receivables', 'nav')},
        'unpaid_distributions': [{'pay_date': r.pay_date, 'amount': r.amount} for r in receivables],
        'unexecuted_last_close_target': signals[-1] if strategy == 'trend' else TrendSignal.LONG,
    }


@fixed_decimal
def run_research(dataset, config, evaluation_start):
    return {
        'mode': 'offline_research', 'strategy_validation': 'unproven',
        'data_kind': dataset.manifest['kind'], 'cash_benchmark_return': ZERO,
        'scenarios': [
            {'cost_multiplier': multiplier,
             'trend': simulate(dataset.bars, config, evaluation_start, 'trend', multiplier),
             'buy_hold': simulate(dataset.bars, config, evaluation_start, 'buy_hold', multiplier)}
            for multiplier in (1, 2, 5)
        ],
    }
