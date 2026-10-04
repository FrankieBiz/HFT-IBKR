"""Offline fixture replay and explicitly durable synthetic continuation."""

import argparse
import hashlib
import os
import sys
from dataclasses import asdict
from pathlib import Path

from quant_research.__main__ import publish_report, source_identity
from quant_research.serde import InputError, canonical_json, read_json_document, strict_keys
from .domain import parse_event, validate_config
from .journal import config_digest, replay_journal
from .runtime import OfflineRuntime, replay


def state_report(state):
    value=asdict(state)
    value['snapshot_parts']=[{'component':name,'event':event.raw} for name,event in state.snapshot_parts]
    return value


def main(argv=None):
    parser=argparse.ArgumentParser(description='Network-free synthetic order control.')
    commands=parser.add_subparsers(dest='command',required=True)
    for command in ('replay','continue'):
        operation=commands.add_parser(command)
        operation.add_argument('--fixture',required=True,type=Path)
        operation.add_argument('--output',required=True,type=Path)
        if command=='continue':
            operation.add_argument('--journal',required=True,type=Path)
    args=parser.parse_args(argv)
    try:
        if os.path.lexists(args.output) or not args.output.parent.is_dir():
            raise InputError('output exists or parent directory is missing')
        if args.command=='continue' and args.output.resolve()==args.journal.resolve():
            raise InputError('journal and report paths must differ')
        raw,content=read_json_document(args.fixture)
        strict_keys(raw,('schema_version','scenario_id','provenance','clock_origin','config','events'),'control fixture')
        if type(raw['schema_version']) is not int or raw['schema_version']!=1:
            raise InputError('unsupported control fixture schema')
        if raw['provenance']!='synthetic' or raw['clock_origin']!='relative_milliseconds':
            raise InputError('only synthetic relative-clock fixtures supported')
        if not isinstance(raw['scenario_id'],str) or not raw['scenario_id'].strip():
            raise InputError('scenario ID required')
        if not isinstance(raw['events'],list):
            raise InputError('events: list required')
        config=validate_config(raw['config'])
        events=tuple(parse_event(event) for event in raw['events'])
        if args.command=='continue' and args.journal.exists():
            historical=replay_journal(args.journal,config)
            expected_sequence=historical.state.last_sequence+2
            previous_time=historical.state.last_time_ms
        else:
            expected_sequence=1
            previous_time=0
        for event in events:
            if event.sequence!=expected_sequence or event.time_ms<previous_time:
                raise InputError('fixture sequence or clock regression')
            expected_sequence+=1
            previous_time=event.time_ms
        # Validate the whole sequence before creating any journal or report.
        if args.command=='replay':
            result=replay(events,config)
            state,outputs=result.state,result.outputs
        else:
            # Continuation fixtures carry absolute sequence/time after the
            # automatic durable restart. They never silently renumber inputs.
            with OfflineRuntime(args.journal,config) as runtime:
                outputs=list(runtime.startup_outputs)
                for event in events:
                    outputs.extend(runtime.process(event).outputs)
                state=runtime.state
        report={'schema_version':1,'mode':'offline_control_'+args.command,
                'scenario_id':raw['scenario_id'],'provenance':'synthetic',
                'fixture_sha256':hashlib.sha256(content).hexdigest(),
                'config':asdict(config),'config_sha256':config_digest(config),
                'code':{'control':source_identity(package='quant_control'),
                        'research':source_identity()},
                'final_state':state_report(state),'outputs':outputs}
        publish_report(args.output,canonical_json(report))
    except InputError as error:
        print(f'input error: {error}',file=sys.stderr)
        return 2
    except Exception as error:
        print(f'runtime error: {error}',file=sys.stderr)
        return 1
    print(f'Wrote synthetic control report: {args.output}')
    return 0


if __name__=='__main__':
    sys.exit(main())
