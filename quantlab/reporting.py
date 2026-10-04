"""Self-contained local reports and research-only model handoff packets."""
from __future__ import annotations
import hashlib
import html
import json
import os
import platform
import tempfile
from pathlib import Path
import subprocess


def code_provenance() -> dict:
    root = Path(__file__).resolve().parent.parent
    revision, dirty = 'unavailable', True
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=root, text=True))
    except (OSError, subprocess.CalledProcessError):
        pass
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).resolve().parent.rglob('*.py')):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return dict(code_revision=revision, working_tree_dirty=dirty, python_source_sha256=digest.hexdigest(),
                python_version=platform.python_version(), platform=platform.platform())


def render_report(result: dict) -> str:
    json.dumps(result, allow_nan=False)
    if result.get('mode') != 'simulation':
        raise ValueError('report requires offline simulation mode')
    escape = lambda value: html.escape(str(value), quote=True)
    summary = ''.join(f'<tr><th>{escape(key)}</th><td>{escape(value)}</td></tr>'
                      for key, value in result['summary'].items())
    values = [float(row['equity']) for row in result['equity']]
    chart = '<p>No equity observations.</p>'
    if values:
        low, high = min(values), max(values)
        width = max(high-low, 1e-9)
        points = ' '.join(f'{20+960*i/max(len(values)-1,1):.2f},{220-200*(v-low)/width:.2f}' for i,v in enumerate(values))
        chart = f'<svg viewBox="0 0 1000 250" role="img" aria-label="Simulated equity over time"><polyline points="{points}" fill="none" stroke="#7ce2c3" stroke-width="2"/></svg><p>Equity range: {low:,.2f}–{high:,.2f}. Horizontal axis: consecutive bar ends.</p>'
    assumptions = ''.join(f'<li>{escape(item)}</li>' for item in result.get('assumptions', []))
    fills = escape(json.dumps(result['fills'][-30:], indent=2, allow_nan=False))
    provenance = escape(json.dumps(result.get('provenance', {}), indent=2, allow_nan=False))
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:"><title>QuantLab offline report</title>
<style>body{{font:16px system-ui;background:#101a24;color:#e8eff4;margin:40px auto;padding:0 24px;max-width:1100px}}h1{{font-size:36px}}h2{{margin-top:40px}}small,p{{color:#afc1d1}}table{{border-collapse:collapse;width:100%}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #344555}}svg{{width:100%;background:#152332;border-radius:8px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:#152332;padding:20px}}.badge{{color:#7ce2c3}}</style>
<p class="badge">OFFLINE SIMULATION · NO BROKER CONNECTION</p><h1>Research run</h1><p>Illustrative execution assumptions. Software output does not establish trading performance.</p><h2>Portfolio</h2>{chart}<table>{summary}</table><h2>Assumptions</h2><ul>{assumptions}</ul><h2>Recent simulated fills</h2><pre>{fills}</pre><h2>Provenance</h2><pre>{provenance}</pre></html>'''


def write_artifacts(result: dict, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+'\n'
    rendered = render_report(result)
    packet = '# Research-only handoff\n\nThis packet is data, not instructions to execute code or orders.\n'
    packet += 'Use a local model manually if desired. No model endpoint is called by QuantLab.\n\n'
    packet += 'Propose falsifiable hypotheses, data-quality checks, and holdout experiments. '
    packet += 'Any generated code requires human review and reproducible offline validation. '
    packet += 'A statistical score never enables a broker mode.\n\n'
    packet += '## Summary\n\n```json\n'+json.dumps(result['summary'], indent=2, allow_nan=False)+'\n```\n'
    packet += '\n## Provenance\n\n```json\n'+json.dumps(result.get('provenance', {}), indent=2, allow_nan=False)+'\n```\n'
    write_new_files(output, {'result.json': serialized, 'report.html': rendered, 'research-packet.md': packet})


def write_new_files(output: Path, contents: dict[str, str]):
    """Publish fully rendered files without overwriting existing paths or links.

    Each file is atomically linked into place. Readers should wait for command
    completion for the entire bundle; there is no cross-file atomicity claim.
    """
    output.mkdir(parents=True, exist_ok=True)
    for name in contents:
        if Path(name).name != name:
            raise ValueError('artifact name must be a single filename')
        target = output/name
        if target.exists() or target.is_symlink():
            raise FileExistsError(f'{target} exists; choose a new output location')
    created = []
    with tempfile.TemporaryDirectory(dir=output, prefix='.staging-') as temporary:
        try:
            for name, content in contents.items():
                staged = Path(temporary)/name
                staged.write_text(content, encoding='utf-8')
                os.link(staged, output/name)
                created.append(output/name)
        except BaseException:
            for path in created:
                path.unlink()
            raise


def render_research_report(result: dict) -> str:
    """Reuse the safe local report shell without treating holdouts as one portfolio."""
    if result.get('mode') != 'offline_research':
        raise ValueError('research report requires offline_research mode')
    json.dumps(result, allow_nan=False)
    summary = {'campaign_trial_count': result['campaign_trial_count'],
               'holdout_observations': len(result['holdout_returns'])}
    for name in ('psr', 'dsr', 'pbo'):
        diagnostic = result[name]
        label = {'psr': 'Holdout PSR', 'dsr': 'Full-history selected-candidate DSR', 'pbo': 'Full-history candidate CSCV PBO'}[name]
        summary[label] = (diagnostic.get('value') if diagnostic['status'] == 'defined'
                          else 'Undefined: '+diagnostic.get('reason', 'insufficient evidence'))
        if name == 'dsr' and diagnostic['status'] == 'defined':
            summary['DSR scope'] = {key: diagnostic[key] for key in ('scope', 'selected_candidate_index', 'observations', 'horizon_start', 'horizon_end') if key in diagnostic}
    proxy = dict(mode='simulation', summary=summary, equity=[], fills=[],
                 assumptions=result['limitations'], provenance=result['provenance'])
    rendered = render_report(proxy).replace('Research run</h1>', 'Offline research evaluation</h1>')
    trials = html.escape(json.dumps(result['trials'], indent=2, allow_nan=False))
    return rendered.replace('</html>', '<h2>Attempted candidates</h2><pre>'+trials+'</pre></html>')
