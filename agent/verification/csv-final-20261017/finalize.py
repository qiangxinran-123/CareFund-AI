"""Publish metadata only and replay accepted outputs through actual D offline."""
from collections import Counter
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE)]
from agent.agent_service import AgentService
from agent.dify_runner import parse_object
from run_live import PRIVATE, check, prepared_cases, sha


def write(path, value):
    if path.exists():
        raise SystemExit('Published evidence exists; no overwrite performed.')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    status_path = PRIVATE/'live-status.json'
    status = parse_object(status_path.read_bytes())
    if status['status'] in ('running','awaiting_stdin_credentials'):
        raise SystemExit('Live process not finished; no public result produced.')
    cases,profile = prepared_cases()
    by_id = {c['case_id']:c for c in cases}
    accepted = []
    for row in status['cases']:
        case = by_id[row['case_id']]
        assert row['request_sha256'] == sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode())
        if row['status'] == 'automatic_checks_passed':
            response_raw = (ROOT/row['response_file']).read_bytes()
            assert sha(response_raw) == row['response_sha256']
            response = parse_object(response_raw)
            assert AgentService(lambda op,req:response).extract(case['request']) == response
            failures,flags = check(case,response)
            assert not failures and not flags
            accepted.append((row,case,response))
    summary = copy.deepcopy(status)
    summary.update(local_status_sha256=sha(status_path.read_bytes()),
        public_report_contains_patient_text=False,
        runtime_code_sha256={p:sha((ROOT/p).read_bytes()) for p in
            ('agent/agent_service.py','agent/extract_policy.py')},
        counts_by_group={g:dict(Counter(c['status'] for c in status['cases'] if c['group']==g))
                        for g in {c['group'] for c in status['cases']}},
        offline_all_row_schema_checks=profile['counts']['local_request_schema_passed'],
        historical_original_60_case_ledger_unchanged=True,
        limits=['Partial rule-based automatic checks, not clinical truth or full semantic accuracy.',
                'Only short whole disease cells were sent, not complete CSV or long narratives.',
                'Regression prose cases originally used GPT; this repeat uses current DeepSeek. Causal effect of prompt versus model is not isolated.',
                'Prompt and Python safeguards cannot guarantee that future model generations never fail.',
                'No OCR, B transactions, frontend or complete export flow tested; actual billing not read.',
                'Original HTTP400 case 23 was not retried. This new authorized run is outside the old 60-case plan.'])
    # Actual teammate implementation in the existing isolated integration checkout.
    d_root = ROOT.parent/'integration_checks/AD-20261016'
    if not (d_root/'validation/fact_checker.py').is_file():
        raise SystemExit('Actual D implementation unavailable; no D replay claimed.')
    current_contracts = {p.name:sha(p.read_bytes()) for p in (ROOT/'contracts/schemas').glob('*.schema.json')}
    d_contracts = {p.name:sha(p.read_bytes()) for p in (d_root/'contracts/schemas').glob('*.schema.json')}
    # The isolated D checkout retains LF while Git checkout uses CRLF.
    # Require equal parsed contracts, recording the distinct byte fingerprints.
    current_semantics = {p.name:parse_object(p.read_bytes()) for p in (ROOT/'contracts/schemas').glob('*.schema.json')}
    d_semantics = {p.name:parse_object(p.read_bytes()) for p in (d_root/'contracts/schemas').glob('*.schema.json')}
    assert current_semantics == d_semantics
    sys.path.insert(0,str(d_root))
    from validation import validate, ValidationPolicy
    from validation.schema import check_model
    policy_path = d_root/'validation/examples/policy.demo.json'
    policy = ValidationPolicy(**parse_object(policy_path.read_bytes()))
    d_summary = dict(mode='offline_actual_D_replay_of_accepted_A_outputs',new_model_calls=0,
        policy='D demo only; not team-approved production policy',
        policy_sha256=sha(policy_path.read_bytes()),shared_contract_fingerprints_match=current_contracts==d_contracts,
        shared_contract_semantics_match=True,current_contract_sha256=current_contracts,D_contract_sha256=d_contracts,
        D_source_sha256={p.relative_to(d_root).as_posix():sha(p.read_bytes())
            for p in (d_root/'validation').rglob('*.py') if 'tests' not in p.parts},cases=[])
    replay_dir = PRIVATE/'d-replay'
    replay_dir.mkdir(exist_ok=True)
    for row,case,response in accepted:
        req = {k:case['request'][k] for k in ('schema_version','application_id','application_revision')}
        req.update(documents=[entry['document'] for entry in case['request']['extracted_documents']],
                   evidence=[ev for entry in case['request']['extracted_documents'] for ev in entry['evidence']],
                   facts=response['candidate_facts'])
        before = copy.deepcopy(req)
        check_model(req,'validation.schema.json','ValidationRequest')
        result = validate(req,policy=policy)
        check_model(result,'validation.schema.json','ValidationResult')
        assert before == req
        assert all(result[k]==req[k] for k in ('schema_version','application_id','application_revision'))
        ids = {f['fact_id'] for f in req['facts']}
        assert all(set(issue['related_fact_ids'])<=ids for issue in result['issues'])
        full = (json.dumps({'request':req,'response':result},ensure_ascii=False,indent=2)+'\n').encode()
        target = replay_dir/(case['case_id']+'.json')
        assert not target.exists()
        target.write_bytes(full)
        d_summary['cases'].append(dict(case_id=case['case_id'],input_and_output_contract='passed',
            input_unmodified=True,can_finalize=result['can_finalize'],
            issue_counts_by_type=dict(Counter(i['type'] for i in result['issues'])),
            issue_counts_by_severity=dict(Counter(i['severity'] for i in result['issues'])),
            private_replay_sha256=sha(full)))
    d_summary.update(mapped_cases=len(accepted),can_finalize_true=sum(c['can_finalize'] for c in d_summary['cases']),
                     contains_patient_text=False)
    write(HERE/'ad-replay-summary.json',d_summary)
    write(HERE/'summary.json',summary)
    print(json.dumps({'live_status':status['status'],'generation_attempts':status['calls_attempted'],
        'counts_by_group':summary['counts_by_group'],'D_offline_mapped':len(accepted),
        'D_finalizable':d_summary['can_finalize_true'],'additional_model_calls':0,'patient_text_printed':False}))
