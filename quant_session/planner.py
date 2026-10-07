"""Causal shadow planning joined to independent research admission."""
import hashlib
from dataclasses import asdict, replace
from decimal import Decimal

from quant_research.risk import admit, size_entry
from quant_research.serde import canonical_json, fixed_decimal
from quant_research.strategy import trend_signals

LIMITATIONS = [
    'Non-binding offline rehearsal; no orders, broker connection or execution authority.',
    'Strategy validation is unproven; illustrative costs are not calibrated fills.',
    'Portfolio, reconciliation and schedule are declarations, not broker-verified; a live IEX quote is one venue, not the NBBO.',
    'Historical source declarations remain unreviewed; schedule is not exchange-certified.',
    'Effective NAV excludes unpaid dividends and other assets; no broker balance-sheet equivalence.',
    'A declared halt blocks every proposal; ledger-backed drawdown memory latches entry halts across restarts.',
    'Neither forces liquidation or partial exits.',
    'One frozen decision per session is not order reservation or an adaptive execution journal.',
]


def decision_digest(report):
    return hashlib.sha256(canonical_json({key: value for key,value in report.items()
                                          if key != 'decision_id'}).encode()).hexdigest()


@fixed_decimal
def plan_session(dataset, config, schedule, snapshot, source_hashes=None, risk_memory=None):
    quote, portfolio, policy = snapshot['quote'], snapshot['portfolio'], snapshot['policy']
    now = snapshot['now']
    effective_nav = min(portfolio['nav'], portfolio['cash'] + portfolio['shares'] * quote['bid'])
    previous_risk = risk_memory or {'peak_nav': Decimal(0), 'maximum_drawdown': Decimal(0),
                                    'entry_halted': False, 'previous_session': None}
    peak = max(portfolio['peak_nav'], previous_risk['peak_nav'], effective_nav)
    drawdown = (peak - effective_nav) / peak
    input_digest = hashlib.sha256(canonical_json({
        'config':asdict(config), 'schedule':schedule, 'snapshot':snapshot}).encode()).hexdigest()
    report = {'schema_version':1, 'mode':'offline_shadow', 'account':'SIM','symbol':'SPY','currency':'USD',
        'snapshot_scope':'declared', 'quote_scope':quote['data_type'], 'data_kind':dataset.manifest['kind'],
        'strategy_validation':'unproven', 'execution_session':snapshot['execution_session'],
        'signal_session':None, 'signal':None, 'status':'BLOCKED', 'proposal':None,
        'blockers':[], 'consumed_causal_bars':0, 'declared_nav':portfolio['nav'],
        'effective_nav':effective_nav, 'drawdown':drawdown,
        'source_hashes':{'data':dataset.data_sha256,'manifest':dataset.manifest_sha256, **(source_hashes or {})},
        'decision_inputs_sha256':input_digest, 'limitations':LIMITATIONS}
    blockers = report['blockers']
    sessions = schedule['sessions']
    execution_index = next((i for i,item in enumerate(sessions)
                            if item['session'] == snapshot['execution_session']), None)
    causal = ()
    if execution_index is None:
        blockers.append('MISSING_EXECUTION_SESSION')
    else:
        execution = sessions[execution_index]
        if not execution['open_at'] <= now < execution['close_at']:
            blockers.append('OUTSIDE_EXECUTION_WINDOW')
        if quote['as_of'] < execution['open_at']:
            blockers.append('QUOTE_BEFORE_OPEN')
        if execution_index == 0:
            blockers.append('MISSING_SIGNAL_SESSION')
        else:
            previous = sessions[execution_index - 1]
            report['signal_session'] = previous['session']
            if previous['close_at'] > now:
                blockers.append('SIGNAL_NOT_COMPLETED')
            causal = tuple(bar for bar in dataset.bars if bar.session <= previous['session'])
            report['consumed_causal_bars'] = len(causal)
            expected = tuple(item['session'] for item in sessions[:execution_index]
                             if causal and item['session'] >= causal[0].session)
            if not causal or tuple(bar.session for bar in causal) != expected or causal[-1].session != previous['session']:
                blockers.append('CAUSAL_COVERAGE')
            else:
                report['signal'] = trend_signals(causal,config.lookback)[-1].value
                if report['signal'] == 'WARMUP':
                    blockers.append('WARMUP')
    for name,instant,maximum in [('QUOTE',quote['as_of'],policy['max_quote_age_seconds']),
                                ('ACCOUNT',portfolio['as_of'],policy['max_account_age_seconds'])]:
        age = (now-instant).total_seconds()
        if age < 0:
            blockers.append('FUTURE_'+name)
        elif age > maximum:
            blockers.append('STALE_'+name)
    for condition,reason in [(not portfolio['reconciled'],'UNRECONCILED'),
            (portfolio['pending_orders']>0,'PENDING_ORDERS'),
            (portfolio['uncertain_orders']>0,'UNCERTAIN_ORDERS'),(portfolio['halted'],'HALTED'),
            (effective_nav == 0,'ZERO_EFFECTIVE_NAV')]:
        if condition:
            blockers.append(reason)
    # Invalid marks must not permanently poison the observed peak or latch.
    invalid_marks = {'STALE_QUOTE', 'FUTURE_QUOTE', 'STALE_ACCOUNT', 'FUTURE_ACCOUNT',
                     'UNRECONCILED', 'PENDING_ORDERS', 'UNCERTAIN_ORDERS', 'ZERO_EFFECTIVE_NAV',
                     'OUTSIDE_EXECUTION_WINDOW', 'QUOTE_BEFORE_OPEN', 'MISSING_EXECUTION_SESSION'}
    # A manual trading halt or missing strategy history does not invalidate a
    # fresh, reconciled portfolio mark. Losses must still latch during a halt.
    mark_valid = not invalid_marks.intersection(blockers)
    maximum_drawdown = previous_risk['maximum_drawdown']
    entry_halted = previous_risk['entry_halted']
    if mark_valid:
        maximum_drawdown = max(maximum_drawdown, drawdown)
        entry_halted = entry_halted or maximum_drawdown >= config.max_drawdown
    report['risk_memory'] = {
        'peak_nav': peak if mark_valid else previous_risk['peak_nav'],
        'maximum_drawdown': maximum_drawdown, 'entry_halted': entry_halted,
        'mark_valid': mark_valid, 'previous_session': previous_risk['previous_session'],
    }
    if not blockers:
        side = ('BUY' if report['signal']=='LONG' and portfolio['shares']==0 else
                'SELL' if report['signal']=='CASH' and portfolio['shares']>0 else None)
        # Like the backtest's drawdown halt, a breach stops new exposure but never an exit.
        if side == 'BUY' and entry_halted:
            blockers.append('DRAWDOWN_LIMIT')
        elif side is None:
            report['status'] = 'HOLD'
        else:
            reference = quote['ask' if side=='BUY' else 'bid']
            execution_config = replace(config,costs=replace(config.costs,half_spread_bps=Decimal(0)))
            quantity = portfolio['shares']
            if side == 'BUY':
                desired = min(config.max_shares, int(effective_nav*config.target_fraction/reference))
                sizing = size_entry(desired,portfolio['settled_cash'],effective_nav,reference,
                                    causal[-1].volume,execution_config,1,False)
                quantity = sizing.quantity
                if quantity == 0:
                    blockers.append(sizing.reason)
            if quantity:
                admission = admit(side=side,quantity=quantity,cash=portfolio['settled_cash'],
                    shares=portfolio['shares'],nav=effective_nav,open_price=reference,
                    previous_volume=causal[-1].volume,config=execution_config,multiplier=1,halted=False)
                if not admission.accepted:
                    blockers.append(admission.reason)
                else:
                    estimate = admission.estimate
                    report['status'] = 'PROPOSED'
                    report['proposal'] = {'side':side,'quantity':quantity,'reference_price':reference,
                        'estimated_price':estimate.price,'estimated_notional':estimate.notional,
                        'estimated_fees':estimate.fees,'estimated_friction':estimate.friction}
    report['decision_id'] = decision_digest(report)
    return report
