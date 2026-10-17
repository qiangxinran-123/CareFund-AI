"""Offline checks and actual D replay; publish metadata only."""
from collections import Counter
import copy
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from agent.agent_service import AgentError,AgentService
from agent.dify_runner import parse_object
spec=importlib.util.spec_from_file_location('expanded_live_evidence',HERE/'run_live.py')
LIVE=importlib.util.module_from_spec(spec);spec.loader.exec_module(LIVE)
PRIVATE=LIVE.PRIVATE


def write(path,value):
    if path.exists():raise SystemExit('Public evidence exists; will not overwrite.')
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def verified_records(summary):
    cases,profile=LIVE.prepared_cases();by_id={c['case_id']:c for c in cases}
    assert summary['suite_sha256']==profile['suite_sha256']
    assert summary['calls_attempted']==len(summary['cases'])<=100
    assert summary['automatic_retries']==summary['full_original_records_sent']==0
    assert len({r['case_id'] for r in summary['cases']})==len(summary['cases'])
    assert set(summary['unattempted_case_ids'])==set(by_id)-{r['case_id'] for r in summary['cases']}
    accepted=[];checks=Counter()
    for row in summary['cases']:
        case=by_id[row['case_id']]
        assert row['request_sha256']==LIVE.PREP.sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode())
        if 'response_file' not in row:
            assert row['status'] in ('boundary_or_transport_rejected','local_error')
            checks['without_saved_response']+=1;continue
        raw=(ROOT/row['response_file']).read_bytes();assert LIVE.PREP.sha(raw)==row['response_sha256']
        response=parse_object(raw)
        try:getattr(AgentService(lambda op,req:response),case['operation'])(case['request'])
        except AgentError as exc:
            assert row['status']=='boundary_or_transport_rejected' and row['error']==str(exc)
            checks['recorded_boundary_rejection_reproduced']+=1;continue
        failures,flags=LIVE.check(case,response)
        assert failures==row['failures'] and flags==row['review_flags']
        expected='automatic_checks_failed' if failures else 'needs_content_review' if flags else 'automatic_checks_passed'
        assert row['status']==expected
        checks[expected]+=1
        if expected=='automatic_checks_passed':accepted.append((row,case,response))
        else:
            decision=summary.get('review_decisions',{}).get(row['case_id'],{})
            if decision.get('disposition')=='safe_false_positive':
                assert not failures and decision['response_sha256']==row['response_sha256']
                checks['safe_false_positive_reviewed']+=1
                accepted.append((row,case,response))
    return accepted,dict(checks)


if __name__=='__main__':
    status_path=PRIVATE/'live-status.json';status=parse_object(status_path.read_bytes())
    if status['status'] in ('running','preflight'):raise SystemExit('Run still active; no report produced.')
    accepted,checks=verified_records(status)
    summary=copy.deepcopy(status)
    times=[r['elapsed_seconds'] for r in summary['cases']]
    usage=[r['dify_usage_metadata']['total_tokens'] for r in summary['cases'] if 'total_tokens' in r.get('dify_usage_metadata',{})]
    summary.update(local_status_sha256=LIVE.PREP.sha(status_path.read_bytes()),offline_recheck=checks,
        counts_by_group={g:dict(Counter(r['status'] for r in summary['cases'] if r['group']==g)) for g in {r['group'] for r in summary['cases']}},
        counts_by_data_class={g:dict(Counter(r['status'] for r in summary['cases'] if r['data_class']==g)) for g in {r['data_class'] for r in summary['cases']}},
        runtime_code_sha256={p:LIVE.PREP.sha((ROOT/p).read_bytes()) for p in ('agent/agent_service.py','agent/extract_policy.py','agent/dify_runner.py')},
        elapsed_seconds_summary=dict(mean=round(statistics.mean(times),3),median=round(statistics.median(times),3),
            p95=sorted(times)[math.ceil(len(times)*0.95)-1],maximum=max(times)) if times else {},
        dify_total_tokens_reported=sum(usage),cases_with_dify_token_metadata=len(usage),actual_provider_bill_read=False,
        public_report_contains_patient_text=False,
        limits=['Partial automatic checks and contextual review, not complete semantic or clinical truth.',
                'Dictionary-selected minimal real inputs do not measure full-narrative or population accuracy.',
                'No entire real medical record, CSV, identifying metadata or project link uploaded.',
                'Dify token metadata is not a verified provider bill or monetary charge.',
                'No B transactions, real OCR, frontend or final export acceptance.'])
    d_root=ROOT.parent/'integration_checks/AD-20261016'
    current={p.name:parse_object(p.read_bytes()) for p in (ROOT/'contracts/schemas').glob('*.schema.json')}
    other={p.name:parse_object(p.read_bytes()) for p in (d_root/'contracts/schemas').glob('*.schema.json')}
    assert current==other
    sys.path.insert(0,str(d_root))
    from validation import validate,ValidationPolicy
    from validation.schema import check_model
    policy_path=d_root/'validation/examples/policy.demo.json';policy=ValidationPolicy(**parse_object(policy_path.read_bytes()))
    d_report=dict(mode='offline_actual_D_for_accepted_extract_outputs',new_model_calls=0,
        policy='D demonstration only; not team-approved production policy',policy_sha256=LIVE.PREP.sha(policy_path.read_bytes()),
        shared_schema_JSON_semantics_match=True,
        D_source_sha256={p.relative_to(d_root).as_posix():LIVE.PREP.sha(p.read_bytes()) for p in (d_root/'validation').rglob('*.py') if 'tests' not in p.parts},cases=[])
    out=PRIVATE/'d-replay';out.mkdir(exist_ok=True)
    for row,case,response in accepted:
        if case['operation']!='extract':continue
        req={k:case['request'][k] for k in ('schema_version','application_id','application_revision')}
        req.update(documents=[d['document'] for d in case['request']['extracted_documents']],
                   evidence=[e for d in case['request']['extracted_documents'] for e in d['evidence']],facts=response['candidate_facts'])
        before=copy.deepcopy(req);check_model(req,'validation.schema.json','ValidationRequest')
        result=validate(req,policy=policy);check_model(result,'validation.schema.json','ValidationResult')
        assert req==before and all(req[k]==result[k] for k in ('schema_version','application_id','application_revision'))
        ids={f['fact_id'] for f in req['facts']}
        assert all(set(i['related_fact_ids'])<=ids for i in result['issues'])
        raw=(json.dumps({'request':req,'result':result},ensure_ascii=False,indent=2)+'\n').encode()
        p=out/(case['case_id']+'.json');assert not p.exists();p.write_bytes(raw)
        d_report['cases'].append(dict(case_id=case['case_id'],contracts='passed',input_unmodified=True,
            can_finalize=result['can_finalize'],private_replay_sha256=LIVE.PREP.sha(raw),
            issue_counts_by_type=dict(Counter(i['type'] for i in result['issues'])),
            issue_counts_by_severity=dict(Counter(i['severity'] for i in result['issues']))))
    d_report.update(mapped_extract_cases=len(d_report['cases']),can_finalize_true=sum(r['can_finalize'] for r in d_report['cases']),
        accepted_draft_cases_not_mapped=sum(c['operation']=='draft' for _,c,_ in accepted),contains_patient_text=False)
    write(HERE/'summary.json',summary);write(HERE/'ad-replay-summary.json',d_report)
    print(json.dumps({'generation_calls':status['calls_attempted'],'offline_recheck':checks,'D_extract_cases':d_report['mapped_extract_cases'],
        'D_can_finalize_true':d_report['can_finalize_true'],'draft_cases_not_full_D_export':d_report['accepted_draft_cases_not_mapped'],
        'reported_tokens':summary['dify_total_tokens_reported'],'additional_model_calls':0,'patient_text_printed':False}))
