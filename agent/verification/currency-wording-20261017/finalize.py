"""Offline response replay, contextual adjudication and actual D mapping."""
from collections import Counter
import copy
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('currency_live_evidence',HERE/'run_live.py')
LIVE=importlib.util.module_from_spec(spec);spec.loader.exec_module(LIVE)
PRIVATE=LIVE.PRIVATE


def verify(report):
    cases,profile=LIVE.load();by_id={c['case_id']:c for c in cases}
    assert report['suite_sha256']==profile['suite_sha256']
    assert report['calls_attempted']==len(report['cases'])<=6
    assert len({r['case_id'] for r in report['cases']})==len(report['cases'])
    assert report['automatic_retries']==report['real_medical_inputs']==0
    accepted=[]
    decisions=report.get('review_decisions',{})
    for row in report['cases']:
        case=by_id[row['case_id']]
        assert LIVE.sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode())==row['request_sha256']
        if 'response_file' not in row:continue
        raw=(ROOT/row['response_file']).read_bytes();assert LIVE.sha(raw)==row['response_sha256']
        result=LIVE.parse_object(raw)
        LIVE.AgentService(lambda op,req:result).extract(case['request'])
        failures,flags=LIVE.check(case,result)
        assert failures==row['failures'] and flags==row['review_flags']
        expected='automatic_checks_failed' if failures else 'needs_content_review' if flags else 'automatic_checks_passed'
        assert row['status']==expected
        decision=decisions.get(row['case_id'],{})
        if flags and decision:
            assert not failures and decision['response_sha256']==row['response_sha256']
            assert decision['disposition']=='safe_attribution_or_negation'
        if not failures and (not flags or decision):accepted.append((row,case,result))
    return accepted


def write(p,value):
    assert not p.exists()
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':
    status=LIVE.parse_object((PRIVATE/'live-status.json').read_bytes())
    assert status['status'] not in ('running','preflight')
    report=copy.deepcopy(status)
    decisions_path=PRIVATE/'review-decisions.json'
    if decisions_path.exists():report.setdefault('review_decisions',{}).update(LIVE.parse_object(decisions_path.read_bytes()))
    accepted=verify(report)
    report.update(overall_status='all_six_passed_partial_checks_and_context_review' if len(accepted)==6 else 'incomplete_or_findings',
        accepted_after_context_review=len(accepted),offline_saved_response_checks='passed',new_model_calls_by_finalization=0,
        local_status_sha256=LIVE.sha((PRIVATE/'live-status.json').read_bytes()),
        original_USD_request_retested_unchanged=True,
        publication_verification='User reported manual publication; exact current UI prompt and fresh DSL export not inspected.',
        runtime_sha256={p:LIVE.sha((ROOT/p).read_bytes()) for p in ('agent/agent_service.py','agent/extract_policy.py','agent/currency_review.py','agent/batch_check.py')},
        actual_bill_read=False,limits=['Six synthetic runs are partial regression, not a guarantee against future hallucination.',
        'Platform currency phrase matches require contextual review, including attributed or negated text.',
        'No production AgentService guard added for ambiguous prose; the new scan is an evaluation helper.',
        'Existing raw DSL exports predate the manually published change; a separate candidate is not an online export.',
        'No B transactions, OCR or final export acceptance.'])
    d_root=ROOT.parent/'integration_checks/AD-20261016'
    current={p.name:json.loads(p.read_bytes()) for p in (ROOT/'contracts/schemas').glob('*.schema.json')}
    other={p.name:json.loads(p.read_bytes()) for p in (d_root/'contracts/schemas').glob('*.schema.json')}
    assert current==other
    sys.path.insert(0,str(d_root))
    from validation import validate,ValidationPolicy
    from validation.schema import check_model
    policy_path=d_root/'validation/examples/policy.demo.json'
    policy=ValidationPolicy(**json.loads(policy_path.read_bytes()))
    replay=dict(new_model_calls=0,mode='offline_actual_D',policy='D demonstration, not approved production policy',
        policy_sha256=LIVE.sha(policy_path.read_bytes()),contract_JSON_semantics_match=True,cases=[])
    out=PRIVATE/'d-replay';out.mkdir(exist_ok=True)
    for row,case,result in accepted:
        req={k:case['request'][k] for k in ('schema_version','application_id','application_revision')}
        req.update(documents=[],evidence=[],facts=result['candidate_facts']);before=copy.deepcopy(req)
        check_model(req,'validation.schema.json','ValidationRequest');checked=validate(req,policy=policy)
        check_model(checked,'validation.schema.json','ValidationResult')
        assert req==before and all(req[k]==checked[k] for k in ('schema_version','application_id','application_revision'))
        assert all(set(i['related_fact_ids'])<={f['fact_id'] for f in req['facts']} for i in checked['issues'])
        raw=(json.dumps(dict(request=req,result=checked),ensure_ascii=False,indent=2)+'\n').encode()
        p=out/(case['case_id']+'.json');assert not p.exists();p.write_bytes(raw)
        replay['cases'].append(dict(case_id=case['case_id'],contracts='passed',input_unchanged=True,
            can_finalize=checked['can_finalize'],private_replay_sha256=LIVE.sha(raw),
            issue_types=dict(Counter(i['type'] for i in checked['issues']))))
    replay.update(mapped_extract_cases=len(replay['cases']),can_finalize_true=sum(r['can_finalize'] for r in replay['cases']))
    write(HERE/'summary.json',report);write(HERE/'ad-replay-summary.json',replay)
    print(json.dumps(dict(generation_calls=report['calls_attempted'],accepted_after_context_review=len(accepted),
        counts=report['counts'],D_extract_cases=replay['mapped_extract_cases'],D_can_finalize_true=replay['can_finalize_true'],new_model_calls=0)))
