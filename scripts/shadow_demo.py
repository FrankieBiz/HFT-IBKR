"""Exercise independent invented shadow snapshots with the portable archive."""

import json
from decimal import Decimal


def shadow_workflows(run, root, folder, bundle):
    fixtures = root / 'examples/shadow'
    shared = ['--bundle', bundle, '--config', root / 'examples/research_config.json',
              '--schedule', fixtures / 'schedule.json']
    observed = []
    for scenario in ('buy', 'hold', 'sell', 'blocked'):
        output = folder / f'shadow-{scenario}.json'
        run('session', 'plan', *shared, '--snapshot', fixtures / f'{scenario}.json',
            '--ledger', folder / f'shadow-{scenario}.sqlite', '--output', output)
        report = json.loads(output.read_text())
        if report['mode'] != 'offline_shadow' or report['strategy_validation'] != 'unproven':
            raise RuntimeError('shadow report lost its offline/unproven scope')
        action = report['proposal']['side'] if report['status'] == 'PROPOSED' else report['status']
        observed.append(action)
    if observed != ['BUY', 'HOLD', 'SELL', 'BLOCKED']:
        raise RuntimeError(f'shadow snapshot actions differ: {observed}')

    run('session', 'plan', *shared, '--snapshot', fixtures / 'buy.json',
        '--ledger', folder / 'shadow-buy.sqlite', '--output', folder / 'shadow-buy-repeat.json')
    if (folder / 'shadow-buy.json').read_bytes() != (folder / 'shadow-buy-repeat.json').read_bytes():
        raise RuntimeError('shadow retry produced a different decision')

    changed = json.loads((fixtures / 'buy.json').read_text())
    for key in ('cash', 'settled_cash', 'nav', 'peak_nav'):
        changed['portfolio'][key] = format(Decimal(changed['portfolio'][key]) + 1, 'f')
    (folder / 'shadow-changed.json').write_text(json.dumps(changed, indent=2) + '\n')
    run('session', 'plan', *shared, '--snapshot', folder / 'shadow-changed.json',
        '--ledger', folder / 'shadow-buy.sqlite', '--output', folder / 'shadow-conflict.json', expected=2)
    if (folder / 'shadow-conflict.json').exists():
        raise RuntimeError('a conflicting shadow decision was published')
    return {'shadow_session_actions': observed, 'shadow_session_retry': 'byte_identical',
            'shadow_session_conflict': 'rejected'}
