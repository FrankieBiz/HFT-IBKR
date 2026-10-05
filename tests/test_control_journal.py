import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from quant_control.domain import parse_event, validate_config
from quant_control.journal import Journal, replay_journal
from quant_control.runtime import OfflineRuntime, replay
from quant_research.serde import InputError
from test_control_domain import control_config, event_raw, intent_raw
from test_control_engine import Harness


def ready_events():
    h = Harness()
    events = []
    original = h.send
    def capture(kind, payload=None, time=0):
        result = original(kind, payload, time)
        events.append(parse_event(event_raw(kind,payload,h.sequence,time)))
        return result
    h.send = capture
    h.ready()
    h.send('intent', intent_raw())
    h.fill()
    return events, h


class ControlJournalTests(unittest.TestCase):
    def test_replay_exact_state_outputs_and_restart_preserves_reservations(self):
        events, h = ready_events()
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'events.jsonl'
            with OfflineRuntime(path, h.config) as runtime:
                outputs = []
                for event in events:
                    outputs.extend(runtime.process(event).outputs)
                self.assertEqual(runtime.state, h.state)
                self.assertEqual(outputs, h.outputs)
                self.assertEqual(runtime.startup_outputs, ())
            first = replay_journal(path,h.config)
            second = replay_journal(path,h.config)
            self.assertEqual(first,second)
            self.assertEqual(first.state,h.state)
            self.assertEqual(first.outputs,tuple(h.outputs))
            with OfflineRuntime(path,h.config) as runtime:
                self.assertEqual(runtime.state.mode,'RECONCILING')
                self.assertEqual(runtime.state.cash,h.state.cash)
                self.assertEqual(runtime.state.orders[0].remaining,4)
                self.assertEqual(runtime.state.orders[0].status,'UNKNOWN_OUTCOME')
                self.assertEqual(runtime.state.decisions,h.state.decisions)
                self.assertFalse(any(o['type']=='submit_simulated' for o in runtime.startup_outputs))
                self.assertEqual(runtime.state.last_sequence,h.state.last_sequence+1)
                duplicate=parse_event(event_raw('intent',intent_raw(),runtime.state.last_sequence+1,0))
                self.assertFalse(any(o['type']=='submit_simulated' for o in runtime.process(duplicate).outputs))

    def test_durable_input_precedes_apply_and_any_outputs(self):
        config=validate_config(control_config())
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            with OfflineRuntime(path,config) as runtime:
                from quant_control.engine import apply_event
                def inspect(state,event,cfg):
                    logged=json.loads(path.read_bytes().splitlines()[-1])
                    self.assertEqual(logged['payload'],event.raw)
                    return apply_event(state,event,cfg)
                with patch('quant_control.runtime.apply_event',side_effect=inspect):
                    runtime.process(event_raw('begin_reconciliation',seq=1))

    def test_crash_after_durable_input_before_apply_reconstructs_decision_once(self):
        events,h=ready_events()
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            with OfflineRuntime(path,h.config) as runtime:
                for event in events[:-2]:
                    runtime.process(event)
                with patch('quant_control.runtime.apply_event',side_effect=RuntimeError('crash')):
                    with self.assertRaises(RuntimeError):
                        runtime.process(events[-2])
                with self.assertRaises(InputError):
                    runtime.process(events[-1])
            recovered=replay_journal(path,h.config)
            self.assertEqual(len(recovered.state.orders),1)
            self.assertEqual(len(recovered.state.decisions),1)
            with OfflineRuntime(path,h.config) as runtime:
                self.assertEqual(runtime.state.orders[0].remaining,6)
                self.assertEqual(runtime.state.mode,'RECONCILING')
                self.assertFalse(any(o['type']=='submit_simulated' for o in runtime.startup_outputs))

    def test_event_history_is_an_immutable_snapshot(self):
        events,h=ready_events()
        with TemporaryDirectory() as tmp, Journal(Path(tmp)/'events.jsonl',h.config) as journal:
            journal.append(events[0])
            earlier=journal.events
            journal.append(events[1])
            self.assertEqual(earlier,(events[0],))
            self.assertEqual(journal.events,tuple(events[:2]))

    def test_durable_sync_requests_full_flush_and_falls_back_to_fsync(self):
        from quant_research import serde
        with patch.object(serde.fcntl,'F_FULLFSYNC',51,create=True), \
                patch.object(serde.fcntl,'fcntl') as full, patch.object(serde.os,'fsync') as fsync:
            serde.durable_sync(7)
            full.assert_called_once_with(7,51)
            fsync.assert_not_called()
            full.side_effect=OSError('unsupported by filesystem')
            serde.durable_sync(7)
            fsync.assert_called_once_with(7)
        with patch.object(serde,'fcntl',None), patch.object(serde.os,'fsync',side_effect=OSError('disk')):
            with self.assertRaises(OSError):
                serde.durable_sync(7)

    def test_fsync_failure_poisons_runtime_and_state_never_admits(self):
        events,h=ready_events()
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            with OfflineRuntime(path,h.config) as runtime:
                for event in events[:-2]:
                    runtime.process(event)
                before=runtime.state
                with patch('quant_control.journal.durable_sync',side_effect=OSError('disk failure')):
                    with self.assertRaises(InputError):
                        runtime.process(events[-2])
                self.assertEqual(runtime.state,before)
                self.assertTrue(runtime.poisoned)
                with self.assertRaises(InputError):
                    runtime.process(events[-2])

    def test_corruption_truncation_and_config_mismatch_fail_closed(self):
        events,h=ready_events()
        with TemporaryDirectory() as tmp:
            original=Path(tmp)/'original.jsonl'
            with OfflineRuntime(original,h.config) as runtime:
                for event in events:
                    runtime.process(event)
            content=original.read_bytes()
            lines=content.splitlines(keepends=True)
            first=json.loads(lines[1])
            first['payload']['kind']='kill'
            changed=json.dumps(first).encode()+b'\n'
            cases=[b''.join(lines[:-1])+lines[-1][:-1],
                   lines[0]+changed+b''.join(lines[2:]),
                   lines[0]+lines[1]+lines[1]+b''.join(lines[2:]),
                   content+b'not json\n']
            for i,corrupt in enumerate(cases):
                path=Path(tmp)/str(i)
                path.write_bytes(corrupt)
                before=path.read_bytes()
                with self.subTest(i=i),self.assertRaises(InputError):
                    OfflineRuntime(path,h.config)
                self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(InputError):
                replay_journal(original,replace(h.config,max_units=h.config.max_units+1))

    def test_exclusive_writer_and_release_after_close(self):
        config=validate_config(control_config())
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            with OfflineRuntime(path,config):
                with self.assertRaises(InputError):
                    OfflineRuntime(path,config)
            with OfflineRuntime(path,config) as runtime:
                self.assertEqual(runtime.state.mode,'RECONCILING')

    def test_replay_sequence_clock_and_schema_rejected(self):
        config=validate_config(control_config())
        with self.assertRaises(InputError):
            replay([parse_event(event_raw('kill',seq=2))],config)
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            with OfflineRuntime(path,config) as runtime:
                runtime.process(event_raw('kill',seq=1,time=10))
                before=path.read_bytes()
                for raw in [event_raw('kill',seq=1,time=10),event_raw('kill',seq=2,time=9)]:
                    with self.assertRaises(InputError):
                        runtime.process(raw)
                self.assertEqual(path.read_bytes(),before)
            lines=path.read_text().splitlines()
            header=json.loads(lines[0]); header['schema_version']=2
            path.write_text(json.dumps(header)+'\n'+'\n'.join(lines[1:])+'\n')
            with self.assertRaises(InputError):
                replay_journal(path,config)

    def test_existing_empty_file_is_not_silently_reinitialized(self):
        config=validate_config(control_config())
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            path.write_bytes(b'')
            with self.assertRaises(InputError):
                OfflineRuntime(path,config)
            self.assertEqual(path.read_bytes(),b'')

    def test_runtime_serializes_calls_from_multiple_threads(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from quant_control.engine import apply_event
        config=validate_config(control_config())
        entered=threading.Event()
        release=threading.Event()
        active=[]
        def slow(state,event,cfg):
            active.append(event.sequence)
            if event.sequence == 1:
                entered.set()
                release.wait(2)
                self.assertEqual(active,[1])
            return apply_event(state,event,cfg)
        with TemporaryDirectory() as tmp, OfflineRuntime(Path(tmp)/'journal',config) as runtime:
            with patch('quant_control.runtime.apply_event',side_effect=slow), ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(runtime.process,event_raw('kill',seq=1))
                self.assertTrue(entered.wait(2))
                second=pool.submit(runtime.process,event_raw('kill',seq=2))
                release.set()
                first.result()
                second.result()
            self.assertEqual(runtime.state.last_sequence,2)

    def test_partial_storage_write_leaves_corruption_and_poisoned_runtime(self):
        config=validate_config(control_config())
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'events.jsonl'
            with OfflineRuntime(path,config) as runtime:
                write=runtime.journal._file.write
                def partial(line):
                    return write(line[:len(line)//2])
                with patch.object(runtime.journal._file,'write',side_effect=partial):
                    with self.assertRaises(InputError):
                        runtime.process(event_raw('kill',seq=1))
                self.assertTrue(runtime.poisoned)
                self.assertEqual(runtime.state.last_sequence,0)
            with self.assertRaises(InputError):
                OfflineRuntime(path,config)
            with self.assertRaises(InputError):
                replay_journal(path,config)
