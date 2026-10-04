import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
from zipfile import ZipFile

from quant_data.bundle import prepare_bundle, read_bundle, inspect_bundle
from quant_research.serde import InputError

ROOT = Path(__file__).resolve().parents[1]


def inputs(folder):
    folder = Path(folder)
    prices = folder / 'prices.csv'
    prices.write_text('session,open,high,low,close,volume\n'
                      '2025-01-02,100,102,99,101,10000\n'
                      '2025-01-03,101,103,100,102,10000\n'
                      '2025-01-06,102,104,101,103,10000\n'
                      '2025-01-07,103,105,102,104,10000\n'
                      '2025-01-08,104,106,103,105,10000\n')
    dividends = folder / 'distributions.csv'
    dividends.write_text('ex_date,amount,pay_date\n2025-01-06,1.25,2025-01-09\n')
    calendar = folder / 'calendar.csv'
    calendar.write_text('session\n2025-01-02\n2025-01-03\n2025-01-06\n2025-01-07\n2025-01-08\n')
    metadata = folder / 'metadata.json'
    source = {'name': 'Invented test source', 'reference': 'synthetic fixture',
              'license_reference': 'original invented fixture; no market data',
              'retrieved_at': '2026-10-04T00:00:00Z'}
    metadata.write_text(json.dumps({'schema_version': 1, 'symbol': 'SPY', 'currency': 'USD',
        'kind': 'synthetic', 'price_policy': 'raw_unadjusted',
        'corporate_actions': 'complete_dividends_no_splits', 'splits_in_interval': False,
        'review_note': 'Invented data for software validation only.',
        'sources': {key: source.copy() for key in ('prices', 'distributions', 'calendar')}}))
    return prices, dividends, calendar, metadata


class IntakeTests(unittest.TestCase):
    def test_bundle_preserves_bars_and_consumed_source_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = inputs(folder)
            output = Path(folder) / 'data.qdata'
            prepare_bundle(*source, output)
            dataset = read_bundle(output)
            self.assertEqual(len(dataset.bars), 5)
            self.assertEqual(str(dataset.bars[2].dividend), '1.25')
            self.assertEqual(dataset.bars[2].dividend_pay_date.isoformat(), '2025-01-09')
            with ZipFile(output) as archive:
                audit = json.loads(archive.read('intake.json'))
            for name, path in zip(('prices', 'distributions', 'calendar', 'metadata'), source):
                self.assertEqual(audit['input_sha256'][name], hashlib.sha256(path.read_bytes()).hexdigest())
            report = inspect_bundle(output)
            self.assertEqual(report['kind'], 'synthetic')
            self.assertFalse(report['independently_verified'])

    def test_deterministic_bytes_and_non_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            source = inputs(folder)
            first, second = [Path(folder) / name for name in ('first.qdata', 'second.qdata')]
            prepare_bundle(*source, first)
            prepare_bundle(*source, second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with self.assertRaises(InputError):
                prepare_bundle(*source, first)

    def test_input_size_limit_and_output_symlink_preservation(self):
        with tempfile.TemporaryDirectory() as folder:
            source = inputs(folder)
            output = Path(folder) / 'data.qdata'
            with patch('quant_data.bundle.MAX_MEMBER', 8), self.assertRaises(InputError):
                prepare_bundle(*source, output)
            self.assertFalse(output.exists())
            output.symlink_to(Path(folder) / 'missing.qdata')
            with self.assertRaises(InputError):
                prepare_bundle(*source, output)
            self.assertTrue(output.is_symlink())
            self.assertFalse(output.exists())

    def test_invalid_input_never_publishes_bundle(self):
        mutations = [
            (0, lambda text: text.replace('session,open', 'date,open')),
            (0, lambda text: text.replace(',10000', ',0', 1)),
            (0, lambda text: text.replace('100,102,99,101', '100,90,99,101')),
            (1, lambda text: text + '2025-01-06,1.0,2025-01-09\n'),
            (1, lambda text: text.replace('2025-01-06', '2025-01-10')),
            (1, lambda text: text.replace('2025-01-09', '2025-01-03')),
            (1, lambda text: text.replace('1.25', 'NaN')),
            (2, lambda text: text.replace('2025-01-06\n', '')),
            (3, lambda text: text.replace('raw_unadjusted', 'adjusted')),
            (3, lambda text: text.replace('"splits_in_interval": false', '"splits_in_interval": true')),
            (3, lambda text: text.replace('original invented fixture; no market data', '')),
            (3, lambda text: text.replace('T00:00:00Z', 'T00:00:00')),
            (3, lambda text: text.replace('"schema_version": 1', '"schema_version": 1, "schema_version": 1')),
        ]
        for index, mutation in mutations:
            with self.subTest(index=index), tempfile.TemporaryDirectory() as folder:
                source = inputs(folder)
                source[index].write_text(mutation(source[index].read_text()))
                output = Path(folder) / 'bad.qdata'
                with self.assertRaises(InputError):
                    prepare_bundle(*source, output)
                self.assertFalse(output.exists())

    def test_bad_archive_members_hash_and_audit_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            good = Path(folder) / 'good.qdata'
            prepare_bundle(*inputs(folder), good)
            with ZipFile(good) as archive:
                members = {name: archive.read(name) for name in archive.namelist()}
            variants = [
                {**members, '../escape': b'bad'},
                {key: value for key, value in members.items() if key != 'intake.json'},
                {**members, 'dataset.csv': members['dataset.csv'].replace(b'10000', b'10001', 1)},
                {**members, 'intake.json': b'{}'},
            ]
            for index, values in enumerate(variants):
                path = Path(folder) / f'bad-{index}.qdata'
                with ZipFile(path, 'w') as archive:
                    for name, value in values.items():
                        archive.writestr(name, value)
                with self.subTest(index=index), self.assertRaises(InputError):
                    read_bundle(path)
            path = Path(folder) / 'not-zip.qdata'
            path.write_bytes(b'not a zip')
            with self.assertRaises(InputError):
                read_bundle(path)

    def test_corrupt_compressed_payload_is_an_input_error(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'data.qdata'
            prepare_bundle(*inputs(folder), bundle)
            with ZipFile(bundle) as archive:
                info = archive.infolist()[0]
            content = bytearray(bundle.read_bytes())
            offset = info.header_offset
            name_length = int.from_bytes(content[offset + 26:offset + 28], 'little')
            extra_length = int.from_bytes(content[offset + 28:offset + 30], 'little')
            content[offset + 30 + name_length + extra_length] = 0xff
            bundle.write_bytes(content)
            with self.assertRaises(InputError):
                read_bundle(bundle)
            result = subprocess.run([sys.executable, '-m', 'quant_data', 'inspect',
                '--bundle', str(bundle), '--output', str(Path(folder) / 'report.json')],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertNotIn('Traceback', result.stderr)

    def test_duplicate_members_and_size_limits_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / 'data.qdata'
            prepare_bundle(*inputs(folder), bundle)
            with patch('quant_data.bundle.MAX_MEMBER', 32), self.assertRaises(InputError):
                read_bundle(bundle)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with ZipFile(bundle, 'a') as archive:
                    archive.writestr('dataset.csv', b'duplicate')
            with self.assertRaises(InputError):
                read_bundle(bundle)

    def test_prepare_inspect_cli_and_replay(self):
        with tempfile.TemporaryDirectory() as folder:
            source = inputs(folder)
            bundle = Path(folder) / 'data.qdata'
            command = [sys.executable, '-m', 'quant_data', 'prepare']
            for flag, path in zip(('prices', 'distributions', 'calendar', 'metadata'), source):
                command += ['--' + flag, str(path)]
            result = subprocess.run(command + ['--output', str(bundle)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = Path(folder) / 'inspection.json'
            result = subprocess.run([sys.executable, '-m', 'quant_data', 'inspect',
                                     '--bundle', str(bundle), '--output', str(report)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(report.read_text())['sessions'], 5)
            from test_inputs import raw_config
            config = Path(folder) / 'config.json'
            config.write_text(json.dumps(raw_config()))
            output = Path(folder) / 'replay.json'
            result = subprocess.run([sys.executable, '-m', 'quant_research', 'replay',
                                     '--bundle', str(bundle), '--config', str(config), '--output', str(output)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_research_input_modes_are_exclusive_and_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'report.json'
            for arguments in [[], ['--data', 'x'], ['--manifest', 'x'],
                              ['--bundle', 'x', '--data', 'y', '--manifest', 'z']]:
                with self.subTest(arguments=arguments):
                    result = subprocess.run([sys.executable, '-m', 'quant_research', 'replay',
                        '--config', str(ROOT / 'examples/research_config.json'), '--output', str(output),
                        *arguments], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertFalse(output.exists())
