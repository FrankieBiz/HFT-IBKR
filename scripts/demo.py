"""Build and run every offline workflow into a fresh local artifact directory."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from build import ROOT, build


def demo(folder):
    artifact=folder/'quant-system.pyz'
    build(artifact)
    def run(*args,expected=0):
        result=subprocess.run([sys.executable,str(artifact),*map(str,args)],cwd=folder,env={},
                              capture_output=True,text=True)
        if result.returncode!=expected:
            raise RuntimeError(f'{args}: exit {result.returncode}: {result.stderr}')
    shared=['--data',ROOT/'examples/synthetic_spy_daily.csv',
            '--manifest',ROOT/'examples/synthetic_spy_manifest.json',
            '--config',ROOT/'examples/research_config.json']
    run('research','replay',*shared,'--output',folder/'replay.json')
    evaluation=[*shared,'--protocol',ROOT/'examples/synthetic_protocol.json',
                '--registry',folder/'experiments.sqlite']
    run('research','evaluate',*evaluation,'--run-id','validation',
        '--selection',folder/'selection.json','--output',folder/'validation.json')
    run('research','holdout',*evaluation,'--run-id','holdout',
        '--selection',folder/'selection.json','--output',folder/'holdout.json')
    run('research','recover','--registry',folder/'experiments.sqlite','--run-id','holdout',
        '--output',folder/'recovered-holdout.json')
    if (folder/'holdout.json').read_bytes()!=(folder/'recovered-holdout.json').read_bytes():
        raise RuntimeError('persisted holdout recovery mismatch')
    run('research','holdout',*evaluation,'--run-id','repeat',
        '--selection',folder/'selection.json','--output',folder/'repeat.json',expected=2)
    for number in range(1,15):
        scenario=f'A{number:02}'
        run('control','replay','--fixture',ROOT/'examples/control'/f'{scenario}.json',
            '--output',folder/f'{scenario}.json',expected=2 if scenario=='A03' else 0)
    run('control','replay','--fixture',ROOT/'examples/control/A12.json','--output',folder/'A12-repeat.json')
    if (folder/'A12.json').read_bytes()!=(folder/'A12-repeat.json').read_bytes():
        raise RuntimeError('control deterministic replay mismatch')
    run('control','continue','--fixture',ROOT/'examples/control/A12.json',
        '--journal',folder/'control.jsonl','--output',folder/'durable-first.json')
    restart=json.loads((ROOT/'examples/control/A12.json').read_text())
    restart['events']=[]
    restart['scenario_id']='restart-with-reservation'
    (folder/'restart-fixture.json').write_text(json.dumps(restart,indent=2)+'\n')
    run('control','continue','--fixture',folder/'restart-fixture.json',
        '--journal',folder/'control.jsonl','--output',folder/'durable-restart.json')
    state=json.loads((folder/'durable-restart.json').read_text())['final_state']
    if state['mode']!='RECONCILING' or state['orders'][0]['status']!='UNKNOWN_OUTCOME' or state['cash']!='802':
        raise RuntimeError('durable restart did not preserve uncertain exposure')
    summary={'status':'offline_workflows_passed','data_kind':'synthetic',
             'strategy_validation':'unproven','control_scenarios':14,
             'holdout_repeat':'rejected','holdout_recovery':'byte_identical',
             'control_replay':'byte_identical','durable_restart':'reconciliation_required',
             'broker_connection':'not_implemented','artifacts':str(folder)}
    (folder/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output-dir',type=Path)
    args=parser.parse_args()
    if args.output_dir:
        folder=args.output_dir.resolve()
        folder.mkdir(parents=True,exist_ok=False)
    else:
        parent=ROOT/'.research-output'
        parent.mkdir(exist_ok=True)
        folder=Path(tempfile.mkdtemp(prefix='demo-',dir=parent))
    print(json.dumps(demo(folder),indent=2))
