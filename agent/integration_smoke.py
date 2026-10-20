"""INT-06: at most two synthetic generations through B -> A -> real Dify.

Requires the existing B/D checkout and their optional test dependencies. No
web server, OCR execution or frontend is claimed by this in-process check.
Credentials stay in memory; reports contain only explicit synthetic fixtures.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from .agent_service import AgentError, AgentService
from .batch_check import semantic_checks
from .dify_runner import DifyRunner, _NoRedirect, parse_object

ROOT = Path(__file__).resolve().parents[1]
APP_NAMES = {'CareFund-信息抽取与追问-修订版': 'extract', 'CareFund-已确认事实草稿-首版': 'draft'}


def credentials(gui):
    base = os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1')
    first, second = os.getenv('DIFY_EXTRACT_API_KEY'), os.getenv('DIFY_DRAFT_API_KEY')
    if first and second:
        return base, first, second
    if not gui:
        return base, getpass.getpass('Dify app key 1 (hidden): ').strip(), getpass.getpass('Dify app key 2 (hidden): ').strip()
    import tkinter as tk
    from tkinter import ttk
    window = tk.Tk()
    window.title('CareFund：A 最终联调 — 本地密钥输入')
    panel = ttk.Frame(window, padding=20)
    panel.grid()
    ttk.Label(panel, text='最多 2 次虚构案例生成：B → A → 真实 Dify。\n两把 Dify 应用密钥顺序不限，自动核对应用名。\n密钥仅存内存，不写文件，不发送到聊天；失败不自动重试。').grid(columnspan=2, pady=12)
    address, key1, key2, error = tk.StringVar(value=base), tk.StringVar(), tk.StringVar(), tk.StringVar()
    for row, (label, variable, masked) in enumerate([('API 地址', address, False), ('Dify 应用密钥 1', key1, True), ('Dify 应用密钥 2', key2, True)], 1):
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky='w')
        entry = ttk.Entry(panel, textvariable=variable, width=52, show='*' if masked else '')
        entry.grid(row=row, column=1, pady=6)
    values = []

    def submit():
        try:
            DifyRunner(user='synthetic_int06', base_url=address.get().strip(),
                       extract_api_key=key1.get().strip(), draft_api_key=key2.get().strip())
            if not key1.get().strip().startswith('app-') or not key2.get().strip().startswith('app-'):
                raise AgentError('请填写两把 app- 开头的 Dify 应用密钥。')
        except AgentError as exc:
            error.set(str(exc))
            return
        values.extend((address.get().strip(), key1.get().strip(), key2.get().strip()))
        key1.set('')
        key2.set('')
        window.destroy()

    ttk.Label(panel, textvariable=error).grid(row=4, columnspan=2)
    ttk.Button(panel, text='开始最多两次真实 API 验证', command=submit).grid(row=5, columnspan=2, pady=12)
    window.bind('<Return>', lambda event: submit())
    window.mainloop()
    return tuple(values) if values else (None, None, None)


def identify(base, keys):
    roles, mappings = {}, []
    for slot, key in enumerate(keys, 1):
        request = Request(base.rstrip('/') + '/info', headers={'Authorization': 'Bearer ' + key})
        try:
            with build_opener(_NoRedirect()).open(request, timeout=30) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise AgentError('Dify app metadata exceeds size limit')
            info = parse_object(raw)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise AgentError('Dify app metadata HTTP error: ' + str(status)) from None
        except (URLError, OSError):
            raise AgentError('Dify app metadata network request failed') from None
        role = APP_NAMES.get(info.get('name'))
        if role is None or role in roles or info.get('mode', 'workflow') != 'workflow':
            raise AgentError('Dify app names do not identify two distinct expected workflows')
        roles[role] = key
        mappings.append(dict(input_slot=slot, operation=role, app_name=info['name']))
    return roles, mappings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-root', type=Path, default=ROOT)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    peer_root = args.backend_root.resolve()
    out = args.output or ROOT / 'agent/.local' / ('int06-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True, exist_ok=False)
    report = dict(started_at=datetime.now(timezone.utc).isoformat(), status='preflight',
        transport='B RealAgentService -> A AgentService -> real Dify Service API',
        input_class='synthetic_only', max_generation_calls=2, calls_attempted=0,
        automatic_retries=0, cases=[], backend_root=str(peer_root),
        scope='In-process adapters only; not HTTP /analyze, frontend, OCR, persistence or end-to-end export.')
    secrets = []

    def save():
        raw = json.dumps(report, ensure_ascii=False, indent=2)
        if any(secret and secret in raw for secret in secrets):
            raise AgentError('Credential-like content cannot be saved in the smoke report')
        temporary = out / 'status.tmp'
        temporary.write_bytes(raw.encode())
        temporary.replace(out / 'status.json')

    try:
        if not (peer_root / 'backend/services/agent.py').is_file():
            raise AgentError('Provide a Backend checkout using --backend-root')
        sys.path.insert(0, str(peer_root))
        from backend.models import Application, Evidence, Fact, UploadedDocument, ValidationIssue
        from backend.services.agent import RealAgentService
        from validation import load_policy, prepare_agent_draft_request, validate_agent_draft
        policy = load_policy('demo_v1')
        # A has already been imported from this checkout; peer modules are read-only.
        report['backend_adapter_sha256'] = hashlib.sha256((peer_root / 'backend/services/agent.py').read_bytes()).hexdigest()
        report['a_runtime_sha256'] = {name: hashlib.sha256((ROOT / 'agent' / name).read_bytes()).hexdigest()
            for name in ('agent_service.py', 'draft_gate.py', 'errors.py', 'dify_runner.py')}
        report['status'] = 'awaiting_local_credentials'
        save()
        base, first, second = credentials(args.gui)
        if not first or not second:
            report['status'] = 'cancelled_before_api_call'
            save()
            return 1
        secrets.extend((first, second))
        DifyRunner(user='synthetic_int06', extract_api_key=first, draft_api_key=second, base_url=base)
        roles, report['app_info_mappings'] = identify(base, (first, second))
        first = second = None
        report['base_url'] = base
        report['status'] = 'running'
        save()

        def factory(application_id):
            runner = DifyRunner(user=application_id, extract_api_key=roles['extract'], draft_api_key=roles['draft'], base_url=base)
            return AgentService(runner), AgentError

        adapter = RealAgentService()
        # Inject only the in-memory credential factory, never mock B/A methods or HTTP.
        adapter._service = factory
        extract = json.loads((ROOT / 'agent/examples/extract_cases/03_document_evidence.json').read_bytes())
        now = '2026-10-20T12:00:00Z'

        def application(identifier, revision, description):
            return Application.model_validate(dict(schema_version='1.0', application_id=identifier, revision=revision,
                status='ready_for_draft', patient_info=dict(display_name='合成联调患者', age_group='adult', medical_summary=description),
                created_at=now, updated_at=now))

        app = application(extract['application_id'], extract['application_revision'], extract['user_input']['description'])
        documents = [UploadedDocument.model_validate(d['document']) for d in extract['extracted_documents']]
        evidence = [Evidence.model_validate(e) for d in extract['extracted_documents'] for e in d['evidence']]
        record = dict(operation='extract', status='calling')
        report['cases'].append(record)
        report['calls_attempted'] += 1
        save()
        started = time.monotonic()
        facts, questions = adapter.extract(app, documents, evidence, [], {})
        response = dict(candidate_facts=[f.model_dump(mode='json') for f in facts], questions=[q.model_dump(mode='json') for q in questions], warnings=[])
        expected = dict(money_exact={'treatment.estimated_cost': [{'currency': 'CNY', 'amount_minor': 3000000}]},
                        no_paid_cost=True, no_date_value=True, no_medical_summary=True, relationship_any=['母亲'], must_question=True)
        failures, flags = semantic_checks(dict(operation='extract', expectation=expected), response)
        if any(f['field'] in ('treatment.paid_cost', 'treatment.recorded_date') for f in response['candidate_facts']):
            failures.append('unprovided_paid_cost_or_recorded_date')
        if failures or flags:
            raise AgentError('Synthetic extraction semantic checks failed: ' + ', '.join(failures + flags))
        record.update(status='backend_A_contract_references_and_synthetic_checks_passed', elapsed_seconds=round(time.monotonic() - started, 3),
                      candidate_facts=response['candidate_facts'], questions=response['questions'])
        save()

        draft = json.loads((ROOT / 'agent/examples/draft-request.json').read_bytes())
        app = application(draft['application_id'], draft['application_revision'], '仍在检查，尚未确诊。')
        document = dict(document_id='doc_synthetic_int06', application_id=app.application_id,
            filename='synthetic-only.pdf', media_type='application/pdf', size_bytes=128, uploaded_at=now, processing_status='processed')
        ev = dict(evidence_id='ev_synthetic_draft_001', document_id=document['document_id'], source_type='document', page=1,
                  text_excerpt='【虚构材料】后续治疗预计费用人民币30000元。', extraction_method='manual')
        snapshot = {k: draft[k] for k in ('schema_version', 'application_id', 'application_revision')}
        snapshot.update(documents=[document], evidence=[ev], facts=draft['candidate_facts'])
        prepared, checked = prepare_agent_draft_request(snapshot, policy=policy,
            application=app.model_dump(mode='json'), generation_request={'expected_revision': app.revision})
        if not checked['can_finalize']:
            raise AgentError('Synthetic draft rejected by deterministic demo_v1 preflight')
        report['draft_validation'] = checked
        gate_ids = set(prepared['validation_issue_ids'])
        gate_issues = [ValidationIssue.model_validate(i) for i in checked['issues'] if i['issue_id'] in gate_ids]
        record = dict(operation='draft', status='calling')
        report['cases'].append(record)
        report['calls_attempted'] += 1
        save()
        started = time.monotonic()
        sections = adapter.draft_sections(app, [Fact.model_validate(f) for f in draft['candidate_facts']], gate_issues)
        response = {k: draft[k] for k in ('schema_version', 'application_id', 'application_revision')}
        from .draft_policy import DRAFT_WARNING
        response.update(candidate_sections=[s.model_dump(mode='json', exclude={'section_id'}) for s in sections], warnings=[DRAFT_WARNING])
        if not validate_agent_draft(snapshot, response, policy=policy)['can_finalize']:
            raise AgentError('D rejected the actual synthetic draft response')
        record.update(status='backend_A_literal_draft_and_D_candidate_checks_passed', elapsed_seconds=round(time.monotonic() - started, 3),
                      candidate_sections=response['candidate_sections'])
        report.update(status='two_real_calls_passed', finished_at=datetime.now(timezone.utc).isoformat())
        save()
        return 0
    except AgentError as exc:
        report.update(status='stopped_on_failure_no_retry', error_type=type(exc).__name__, error_code=exc.code, error=str(exc))
    except Exception as exc:
        report.update(status='stopped_on_local_or_backend_error_no_retry', error_type=type(exc).__name__)
    save()
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
