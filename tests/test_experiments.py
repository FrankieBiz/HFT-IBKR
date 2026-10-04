import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from quant_research.experiments import ExperimentRegistry
from quant_research.serde import InputError


def registered_artifact(registry):
    from test_evaluation import inputs
    from quant_research.evaluation import parse_protocol, evaluate_registered, freeze_selection
    dataset, config, raw = inputs()
    protocol = parse_protocol(raw, dataset)
    report = evaluate_registered(dataset, config, protocol, 'code-v1', registry=registry, run_id='setup')
    artifact = freeze_selection(dataset, config, protocol, 'code-v1', report)
    registry.register_freeze('setup', artifact)
    return artifact


class RegistryTests(unittest.TestCase):
    def test_completed_results_can_be_recovered_without_recomputing(self):
        from quant_research.evaluation import digest
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'registry.sqlite') as registry:
            report={'result':'synthetic','amount':'-0.18'}
            registry.reserve_validation('first',{})
            registry.complete('first',digest(report),result=report)
            self.assertEqual(registry.result('first'),report)
            with self.assertRaises(InputError):
                registry.result('missing')

    def test_persistence_unique_attempts_and_consumed_crash_release(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'registry.sqlite'
            with ExperimentRegistry(path) as registry:
                registry.reserve_validation('first', {'protocol': 'p'})
                registry.complete('first', 'a'*64)
                with self.assertRaises(InputError):
                    registry.reserve_validation('first', {})
                artifact = registered_artifact(registry)
                registry.reserve_holdout('release', artifact['integrity_digest'], artifact['identities'])
            with ExperimentRegistry(path) as registry:
                self.assertEqual([r['status'] for r in registry.records()], ['reserved','completed','reserved','completed','reserved'])
                with self.assertRaises(InputError):
                    registry.reserve_holdout('new', artifact['integrity_digest'], artifact['identities'])
                with self.assertRaises(InputError):
                    registry.fail('first', 'later')
                with self.assertRaises(sqlite3.DatabaseError):
                    registry.connection.execute("DELETE FROM events")
                with self.assertRaises(sqlite3.DatabaseError):
                    registry.connection.execute("UPDATE events SET status='failed'")

    def test_concurrent_release_has_exactly_one_winner(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp)/'registry.sqlite'
            with ExperimentRegistry(path) as registry:
                artifact = registered_artifact(registry)
            def reserve(i):
                try:
                    with ExperimentRegistry(path) as registry:
                        registry.reserve_holdout(str(i), artifact['integrity_digest'], artifact['identities'])
                    return True
                except InputError:
                    return False
            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(sum(pool.map(reserve, range(8))), 1)

    def test_storage_failure_rolls_back_and_no_computation(self):
        with TemporaryDirectory() as tmp, ExperimentRegistry(Path(tmp)/'registry.sqlite') as registry:
            registry.connection.execute('PRAGMA query_only=ON')
            with self.assertRaises(InputError):
                registry.reserve_validation('first', {})
            self.assertEqual(registry.records(), [])
            registry.connection.execute('PRAGMA query_only=OFF')
            registry.reserve_validation('first', {})
            self.assertEqual(len(registry.records()), 1)
