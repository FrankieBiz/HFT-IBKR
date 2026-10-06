#!/usr/bin/env python3
"""Run from an independent scheduler to check the local shadow runner offline."""

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quant_research.serde import canonical_json
from quant_session.health import check_health


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--heartbeat', type=Path, default=Path('.research-output/shadow/heartbeat.json'))
    parser.add_argument('--ledger', type=Path, default=Path('.research-output/shadow/ledger.sqlite'))
    parser.add_argument('--session')
    parser.add_argument('--deadline')
    parser.add_argument('--max-age-seconds', type=int, default=120)
    args = parser.parse_args(argv)
    report = check_health(args.heartbeat, args.ledger, session=args.session, deadline=args.deadline,
                          max_age_seconds=args.max_age_seconds)
    print(canonical_json(report), end='')
    return 0 if report['healthy'] else 2


if __name__ == '__main__':
    sys.exit(main())
