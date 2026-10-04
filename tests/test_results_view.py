import copy
import json
from pathlib import Path
import tempfile
import threading
import subprocess
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from quant_view.render import render_page
from quant_view.__main__ import make_server, read_page
from quant_research.serde import InputError


def research():
    curve = [{'session': '2025-01-02', 'nav': '1000'}, {'session': '2025-01-03', 'nav': '1010'}]
    strategy = {'equity_curve': curve, 'total_return': '0.01', 'maximum_drawdown': '0.02',
                'trade_count': 1, 'rejection_count': 0, 'modeled_execution_cost': '1.25',
                'evaluation_start': '2025-01-02', 'evaluation_end': '2025-01-03',
                'final': {'cash': '500', 'shares': 5, 'nav': '1010', 'receivables': '0'}}
    return {'schema_version': 1, 'mode': 'offline_research', 'data_kind': 'synthetic',
            'strategy_validation': 'unproven', 'config': {'lookback': 200, 'initial_cash': '1000'},
            'provenance': {'source': 'Invented source'}, 'data_sha256': 'a' * 64,
            'manifest_sha256': 'b' * 64, 'assumptions': ['Invented data; not evidence of market edge.'],
            'scenarios': [{'cost_multiplier': '1', 'trend': strategy, 'buy_hold': copy.deepcopy(strategy)}]}


class ViewTests(unittest.TestCase):
    def test_render_escapes_embedded_data_without_external_assets(self):
        sample = research()
        sample['provenance']['source'] = '</script><script>alert(1)</script>'
        page = render_page(sample, [])
        self.assertIn('Offline research', page)
        self.assertIn('application/json', page)
        self.assertNotIn('</script><script>alert(1)</script>', page)
        self.assertIn('\\u003c/script\\u003e', page)
        self.assertNotIn('https://', page)
        self.assertNotIn('fetch(', page)

    def test_bad_research_or_chart_values_are_rejected(self):
        changes = [('mode', 'live'), ('data_kind', 'unknown'), ('schema_version', True),
                   ('strategy_validation', 'proven'), ('scenarios', [])]
        for key, value in changes:
            with self.subTest(key=key):
                sample = research()
                sample[key] = value
                with self.assertRaises(InputError):
                    render_page(sample, [])
        for value in ['NaN', 'Infinity', '1e100', '1e999999999', '1_000', True]:
            sample = research()
            sample['scenarios'][0]['trend']['equity_curve'][0]['nav'] = value
            with self.subTest(value=value), self.assertRaises(InputError):
                render_page(sample, [])

    def test_control_is_explicitly_simulated(self):
        control = {'schema_version': 1, 'mode': 'offline_control_replay', 'provenance': 'synthetic',
                   'scenario_id': 'A08', 'final_state': {'mode': 'READY', 'halt_reasons': [],
                   'cash': '802', 'inventory': 2, 'orders': []}}
        self.assertIn('A08', render_page(research(), [control]))
        control['mode'] = 'live'
        with self.assertRaises(InputError):
            render_page(research(), [control])

    def test_report_integer_cost_multiplier_is_supported(self):
        sample = research()
        sample['scenarios'][0]['cost_multiplier'] = 1
        self.assertIn('"cost": "1"', render_page(sample, []))

    def test_server_only_serves_page_on_loopback(self):
        server = make_server(b'<h1>Test report</h1>', port=0)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            self.assertEqual(server.server_address[0], '127.0.0.1')
            base = f'http://127.0.0.1:{server.server_address[1]}'
            self.assertIn(b'Test report', urlopen(base + '/').read())
            for path in ['/../README.md', '/report.json', '/.git/config']:
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    urlopen(base + path)
                self.assertEqual(error.exception.code, 404)
                error.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)

    def test_cli_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'research.json'
            source.write_text(json.dumps(research()))
            output = Path(folder) / 'index.html'
            command = [sys.executable, '-m', 'quant_view', 'render', '--research', str(source),
                       '--output', str(output)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            original = output.read_bytes()
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 2)
            self.assertEqual(output.read_bytes(), original)

    def test_page_reads_are_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'page.html'
            path.write_bytes(b'123456789')
            with patch('quant_view.__main__.MAX_PAGE', 8), self.assertRaises(InputError):
                read_page(path)
            with self.assertRaises(InputError):
                read_page(Path(folder))
