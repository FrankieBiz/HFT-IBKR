"""Optional Playwright integration check using invented temporary local state only.

Run: python3 scripts/check_app_browser.py [--browser-executable PATH]
Playwright is a developer check dependency, never an app runtime dependency.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
from contextlib import closing
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from quant_app.jobs import JobManager
from quant_app.server import make_server
from quant_app.service import Service
from quant_research.serde import canonical_json
from quant_session.inputs import parse_schedule,parse_snapshot
from quant_session.ledger import DecisionLedger
from quant_session.planner import plan_session
from test_shadow_readiness import evidence
from test_shadow_session import fixtures


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser-executable')
    parser.add_argument('--screenshots',type=Path,default=Path(tempfile.gettempdir())/'quant-app-browser')
    args=parser.parse_args()
    from playwright.sync_api import sync_playwright,expect
    args.screenshots.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='quant-app-invented-') as folder:
        root=Path(folder)/'checkout'
        scripts=root/'scripts'
        scripts.mkdir(parents=True)
        for name in ('run_daily.sh','run_study.sh','daily_shadow.sh'):
            (scripts/name).write_text('#!/usr/bin/env bash\necho "Invented offline job. FAKE_BROWSER_KEY FAKE_BROWSER_SECRET"\ntrap "exit 0" TERM INT\nsleep 60 &\nwait\n')
        output=root/'.research-output/spy-trend-v2'
        output.mkdir(parents=True)
        _,paths=evidence(output,real_bundle=True,feed='sip')
        study=root/'studies/spy-trend-v2'
        study.mkdir(parents=True)
        for name in ('config.json','protocol.json'):
            shutil.copyfile(paths[name],study/name)
        shared=root/'.research-output/spy-daily-v1'
        shared.mkdir()
        shutil.move(paths['registry.sqlite'],shared/'experiments.sqlite')
        home=Path(folder)/'config'
        service=Service(root,home)
        jobs=JobManager(root,home)
        server=make_server(service,jobs,port=0)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                options={'headless':True}
                if args.browser_executable:options['executable_path']=args.browser_executable
                browser=playwright.chromium.launch(**options)
                context=browser.new_context(viewport={'width':1440,'height':1000})
                page=context.new_page()
                errors=[]
                requests=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.on('console',lambda message:errors.append(message.text) if message.type=='error' else None)
                page.on('request',lambda request:requests.append(request.url))
                page.goto(f'http://127.0.0.1:{server.server_address[1]}',wait_until='networkidle')
                expect(page.locator('#study-metric')).to_have_text('Verified')
                expect(page.locator('#decision-metric')).to_have_text('None yet')
                page.locator('[data-page="setup"]').click()
                expect(page.locator('#strategy-evidence')).to_be_visible()
                expect(page.locator('#strategy-rule')).to_contain_text('selected SMA 2 sessions')
                expect(page.locator('#strategy-results tr')).to_have_count(3)
                expect(page.locator('#strategy-results')).to_contain_text('not recorded')
                expect(page.locator('[data-action="study"]')).to_be_disabled()
                page.locator('[name="key_id"]').fill('FAKE_BROWSER_KEY')
                page.locator('[name="secret_key"]').fill('FAKE_BROWSER_SECRET')
                page.get_by_role('button',name='Save keys locally').click()
                expect(page.locator('#keys-tag')).to_have_text('File found')
                expect(page.locator('[name="secret_key"]')).to_have_value('')
                page.locator('[name="cash"]').fill('10000')
                page.get_by_role('button',name='Create simulated book').click()
                expect(page.locator('#book-tag')).to_have_text('Ready')
                expect(page.locator('#book-form')).to_be_hidden()
                dataset,config,schedule,snapshot=fixtures()
                day=service.shadow/snapshot['execution_session']
                day.mkdir()
                content=canonical_json(snapshot).encode()
                (day/'snapshot.json').write_bytes(content)
                report=plan_session(dataset,config,parse_schedule(schedule),parse_snapshot(snapshot),{'snapshot':hashlib.sha256(content).hexdigest()})
                DecisionLedger(service.ledger_path).record(report,'invented-browser-fixture')
                page.locator('#refresh').click()
                expect(page.locator('#decision-metric')).to_have_text('BUY')
                page.locator('[data-page="decisions"]').click()
                expect(page.locator('#history-body tr')).to_have_count(1)
                page.get_by_role('button',name='View decision 2025-03-11').click()
                expect(page.locator('#decision-dialog')).to_be_visible()
                page.locator('#close-dialog').click()
                page.locator('[data-page="portfolio"]').click()
                expect(page.locator('#fill-form')).to_be_visible()
                page.locator('#fill-form [name="price"]').fill('103')
                page.locator('#fill-form [name="fees"]').fill('1')
                page.on('dialog',lambda dialog:dialog.accept())
                page.get_by_role('button',name='Record this simulated fill').click()
                expect(page.locator('#fill-form')).to_be_hidden()
                expect(page.locator('#book-shares')).to_have_text(str(report['proposal']['quantity']))
                page.screenshot(path=str(args.screenshots/'portfolio-desktop.png'),full_page=True)
                # Invent the crash-after-book-write state without changing the book.
                with closing(sqlite3.connect(service.journal_path)) as connection,connection:
                    connection.execute('UPDATE fill_intents SET status="pending"')
                before_recovery=service.portfolio_path.read_bytes()
                page.locator('#refresh').click()
                expect(page.get_by_role('button',name='Recover pending accounting')).to_be_visible()
                page.get_by_role('button',name='Recover pending accounting').click()
                expect(page.get_by_role('button',name='Recover pending accounting')).to_be_hidden()
                assert service.portfolio_path.read_bytes()==before_recovery

                page.locator('[data-page="overview"]').click()
                page.get_by_role('button',name='Start runner').click()
                expect(page.locator('#job-tag')).to_have_text('Shadow runner active')
                expect(page.locator('#job-output')).to_contain_text('Invented offline job')
                assert 'FAKE_BROWSER_KEY' not in page.locator('#job-output').inner_text()
                assert 'FAKE_BROWSER_SECRET' not in page.locator('#job-output').inner_text()
                page.locator('[data-page="setup"]').click()
                expect(page.get_by_role('button',name='Save keys locally')).to_be_disabled()
                page.locator('[data-page="overview"]').click()
                page.get_by_role('button',name='Stop',exact=True).click()
                expect(page.get_by_role('button',name='Stop',exact=True)).to_be_disabled()
                page.screenshot(path=str(args.screenshots/'overview-desktop.png'),full_page=True)
                page.set_viewport_size({'width':390,'height':844})
                page.locator('[data-page="setup"]').click()
                expect(page.get_by_role('heading',name='Get ready to run.')).to_be_visible()
                page.screenshot(path=str(args.screenshots/'setup-mobile.png'),full_page=True)
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), page.evaluate('[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth).map(e=>[e.tagName,e.id,e.className,e.getBoundingClientRect().right])')
                page.screenshot(path=str(args.screenshots/'setup-mobile.png'),full_page=True)
                page.locator('[data-page="activity"]').click()
                expect(page.locator('#job-output')).to_contain_text('Job finished')
                with closing(sqlite3.connect(service.ledger_path)) as connection,connection:
                    connection.execute('UPDATE decisions SET report=?',(b'invented corruption',))
                page.locator('#refresh').click()
                page.locator('[data-page="decisions"]').click()
                expect(page.locator('#history-error')).to_contain_text('corrupt ledger')
                expect(page.locator('#history-body tr')).to_have_count(0)
                assert not errors,errors
                assert all(url.startswith(f'http://127.0.0.1:{server.server_address[1]}/') for url in requests),requests
                context.close()
                browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=3)
            server.server_close()
            jobs.close()
    print(json.dumps({'status':'passed','scope':'invented offline fixture / fake keys only','screenshots':str(args.screenshots)}))


if __name__=='__main__':
    main()
