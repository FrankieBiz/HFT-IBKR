import copy
from dataclasses import replace
from datetime import date
from decimal import Decimal, localcontext
import unittest
from quant_research.data import Bar, Dataset
from quant_research.config import parse_config
from quant_research.serde import InputError
from test_inputs import raw_config
from quant_session.inputs import parse_schedule, parse_snapshot
from quant_session.planner import plan_session


def fixtures(closes=(100, 102), shares=0):
    sessions = ['2025-03-07', '2025-03-10', '2025-03-11']
    schedule = {'schema_version': 1, 'source': 'invented schedule', 'sessions': [
        {'session': day, 'open_at': day+'T'+opening+'Z', 'close_at': day+'T'+closing+'Z'}
        for day, opening, closing in [(sessions[0],'14:30:00','21:00:00'),
                                      (sessions[1],'13:30:00','20:00:00'),
                                      (sessions[2],'13:30:00','17:00:00')]]}
    snapshot = {'schema_version': 1, 'mode': 'offline_shadow', 'account': 'SIM',
        'symbol': 'SPY', 'currency': 'USD', 'execution_session': sessions[2],
        'now': sessions[2]+'T13:30:00Z',
        'quote': {'bid':'102','ask':'103','as_of':sessions[2]+'T13:30:00Z','data_type':'synthetic'},
        'portfolio': {'cash':'10000','settled_cash':'10000','nav':'10000','peak_nav':'10000',
            'shares': shares, 'as_of':sessions[2]+'T13:30:00Z','reconciled':True,
            'pending_orders':0,'uncertain_orders':0,'halted':False},
        'policy': {'max_quote_age_seconds':60,'max_account_age_seconds':60}}
    bars = tuple(Bar(date.fromisoformat(day), *(Decimal(str(p)),)*4, 10000, Decimal(0), None)
                 for day,p in zip(sessions,closes))
    dataset = Dataset(bars, {'kind':'synthetic'}, 'a'*64, 'b'*64)
    raw = raw_config()
    raw['lookback'] = 2
    return dataset, parse_config(raw), schedule, snapshot


def decide(dataset, config, schedule, snapshot):
    return plan_session(dataset, config, parse_schedule(schedule), parse_snapshot(snapshot))


class ShadowTests(unittest.TestCase):
    def test_buy_hold_sell_warmup(self):
        for closes, shares, expected, side in [((100,102),0,'PROPOSED','BUY'),
                ((100,102),5,'HOLD',None), ((102,100),5,'PROPOSED','SELL'),
                ((102,100),0,'HOLD',None), ((100,),0,'BLOCKED',None)]:
            data, config, schedule, snapshot = fixtures(closes, shares)
            if len(closes)==1:
                data=replace(data,bars=(replace(data.bars[0],session=date(2025,3,10)),))
            report=decide(data,config,schedule,snapshot)
            self.assertEqual(report['status'],expected)
            self.assertEqual(report['proposal']['side'] if report['proposal'] else None,side)

    def test_identity_consumes_inputs_even_when_outcome_is_unchanged(self):
        data,config,schedule,snapshot=fixtures()
        first=decide(data,config,schedule,snapshot)
        snapshot['now']='2025-03-11T13:30:01Z'
        second=decide(data,config,schedule,snapshot)
        self.assertEqual(first['proposal'],second['proposal'])
        self.assertNotEqual(first['decision_id'],second['decision_id'])

    def test_future_data_never_changes_signal_or_proposal(self):
        data,config,schedule,snapshot=fixtures()
        first=decide(data,config,schedule,snapshot)
        future=replace(data.bars[-1],session=date(2025,3,11),close=Decimal('99999'))
        second=decide(replace(data,bars=data.bars+(future,),data_sha256='c'*64),config,schedule,snapshot)
        self.assertEqual((first['signal'],first['proposal']),(second['signal'],second['proposal']))
        self.assertNotEqual(first['decision_id'],second['decision_id'])

    def test_exact_coverage(self):
        data,config,schedule,snapshot=fixtures()
        schedule['sessions'].insert(1,{'session':'2025-03-08','open_at':'2025-03-08T14:30:00Z','close_at':'2025-03-08T21:00:00Z'})
        self.assertIn('CAUSAL_COVERAGE',decide(data,config,schedule,snapshot)['blockers'])

    def test_blocking_gates_and_boundaries(self):
        data,config,schedule,base=fixtures()
        cases=[('now','2025-03-11T17:00:00Z','OUTSIDE_EXECUTION_WINDOW'),
               ('now','2025-03-11T13:29:59Z','OUTSIDE_EXECUTION_WINDOW'),
               ('now','2025-03-11T13:31:01Z','STALE_QUOTE')]
        for field,value,reason in cases:
            snapshot=copy.deepcopy(base); snapshot[field]=value
            self.assertIn(reason,decide(data,config,schedule,snapshot)['blockers'])
        for field,value,reason in [('reconciled',False,'UNRECONCILED'),('pending_orders',1,'PENDING_ORDERS'),
                ('uncertain_orders',1,'UNCERTAIN_ORDERS'),('halted',True,'HALTED'),
                ('peak_nav','20000','DRAWDOWN_LIMIT'),('cash','0','ZERO_EFFECTIVE_NAV')]:
            snapshot=copy.deepcopy(base); snapshot['portfolio'][field]=value
            if field=='cash': snapshot['portfolio']['settled_cash']='0'
            self.assertIn(reason,decide(data,config,schedule,snapshot)['blockers'])
        for value,reason in [('2025-03-11T13:30:01Z','FUTURE_QUOTE'),('2025-03-11T13:29:59Z','QUOTE_BEFORE_OPEN')]:
            snapshot=copy.deepcopy(base); snapshot['quote']['as_of']=value
            self.assertIn(reason,decide(data,config,schedule,snapshot)['blockers'])

    def test_account_age_close_coherence_and_history_boundaries(self):
        data,config,schedule,snapshot=fixtures()
        snapshot['portfolio']['as_of']='2025-03-11T13:28:59Z'
        self.assertIn('STALE_ACCOUNT',decide(data,config,schedule,snapshot)['blockers'])
        snapshot['portfolio']['as_of']='2025-03-11T13:30:01Z'
        self.assertIn('FUTURE_ACCOUNT',decide(data,config,schedule,snapshot)['blockers'])
        _,_,_,snapshot=fixtures()
        snapshot['now']='2025-03-10T19:00:00Z'
        self.assertIn('SIGNAL_NOT_COMPLETED',decide(data,config,schedule,snapshot)['blockers'])
        _,_,_,snapshot=fixtures()
        snapshot['now']='2025-03-11T13:31:00Z'
        self.assertEqual(decide(data,config,schedule,snapshot)['status'],'PROPOSED')
        # Earlier declared history need not be present; missing final causal bar blocks.
        schedule['sessions'].insert(0,{'session':'2025-03-06','open_at':'2025-03-06T14:30:00Z',
                                     'close_at':'2025-03-06T21:00:00Z'})
        self.assertEqual(decide(data,config,schedule,snapshot)['status'],'PROPOSED')
        self.assertIn('CAUSAL_COVERAGE',decide(replace(data,bars=data.bars[:-1]),config,schedule,snapshot)['blockers'])

    def test_buy_caps_exposure_notional_shares_capacity_and_fees(self):
        data,config,schedule,snapshot=fixtures()
        for changed,maximum in [(replace(config,max_shares=1),1),
                (replace(config,max_order_notional=Decimal('210')),2),
                (replace(config,participation_limit=Decimal('0.0001')),1)]:
            report=decide(data,changed,schedule,snapshot)
            self.assertEqual(report['status'],'PROPOSED')
            self.assertLessEqual(report['proposal']['quantity'],maximum)
        free=replace(config,costs=replace(config.costs,half_spread_bps=Decimal(0),slippage_bps=Decimal(0),
                impact_bps=Decimal(0),minimum_commission=Decimal(0),commission_per_share=Decimal(0),exchange_fee_bps=Decimal(0)))
        snapshot['portfolio']['settled_cash']='103'
        self.assertEqual(decide(data,free,schedule,snapshot)['proposal']['quantity'],1)
        charged=replace(free,costs=replace(free.costs,minimum_commission=Decimal('1')))
        self.assertIn('CASH_LIMIT',decide(data,charged,schedule,snapshot)['blockers'])
        snapshot['portfolio'].update(cash='1030',settled_cash='1030',nav='1030',peak_nav='1030')
        exposed=replace(charged,target_fraction=Decimal('0.5'),max_position_fraction=Decimal('0.5'),
                        costs=replace(charged.costs,slippage_bps=Decimal('100')))
        report=decide(data,exposed,schedule,snapshot)
        self.assertEqual(report['proposal']['quantity'],4)
        self.assertLessEqual(report['proposal']['estimated_notional'],Decimal('515'))

    def test_strict_inputs(self):
        _,_,schedule,snapshot=fixtures()
        for field,value in [('data_type','delayed'),('bid','104')]:
            bad=copy.deepcopy(snapshot); bad['quote'][field]=value
            with self.assertRaises(InputError): parse_snapshot(bad)
        bad=copy.deepcopy(schedule); bad['sessions'][1]['open_at']='2025-03-10T09:30:00-04:00'
        with self.assertRaises(InputError): parse_schedule(bad)
        for field,value in [('reconciled',1),('shares',True),('peak_nav','9999')]:
            bad=copy.deepcopy(snapshot); bad['portfolio'][field]=value
            with self.assertRaises(InputError): parse_snapshot(bad)

    def test_costs_cash_effective_nav_and_decimal_context(self):
        data,config,schedule,snapshot=fixtures()
        snapshot['portfolio']['settled_cash']='104'
        config=replace(config,costs=replace(config.costs,half_spread_bps=Decimal('100'),slippage_bps=Decimal(0),impact_bps=Decimal(0)))
        first=decide(data,config,schedule,snapshot)
        self.assertEqual(first['proposal']['quantity'],1)
        self.assertEqual(first['proposal']['estimated_price'],Decimal('103'))
        with localcontext() as context:
            context.prec=3
            self.assertEqual(first,decide(data,config,schedule,snapshot))
        snapshot['portfolio']['settled_cash']='1'
        self.assertIn('CASH_LIMIT',decide(data,config,schedule,snapshot)['blockers'])
        snapshot['portfolio'].update(cash='100',settled_cash='100',nav='10000',peak_nav='10000')
        self.assertEqual(decide(data,config,schedule,snapshot)['effective_nav'],Decimal('100'))

    def test_large_target_is_capped_before_bounded_sizing(self):
        data,config,schedule,snapshot=fixtures()
        snapshot['quote'].update(bid='0.000000000001',ask='0.000000000001')
        snapshot['portfolio'].update(cash='1000000000000000000',settled_cash='1000000000000000000',
                                     nav='1000000000000000000',peak_nav='1000000000000000000')
        config=replace(config,costs=replace(config.costs,minimum_commission=Decimal(0),commission_per_share=Decimal(0)))
        report=decide(data,config,schedule,snapshot)
        self.assertEqual(report['status'],'PROPOSED')
        self.assertLessEqual(report['proposal']['quantity'],config.max_shares)

    def test_sell_independent_capacity_notional_and_fees(self):
        data,config,schedule,snapshot=fixtures((102,100),5)
        for changed,reason in [(replace(config,max_order_notional=Decimal(1)),'ORDER_NOTIONAL_LIMIT'),
                (replace(config,participation_limit=Decimal('0.0001')),'CAPACITY_LIMIT'),
                (replace(config,costs=replace(config.costs,minimum_commission=Decimal(10000))),'NONPOSITIVE_PROCEEDS')]:
            self.assertIn(reason,decide(data,changed,schedule,snapshot)['blockers'])
