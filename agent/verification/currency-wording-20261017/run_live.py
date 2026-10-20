"""Six synthetic calls only; stdin credential, stop on findings, no retries."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from agent.agent_service import AgentService, AgentError
from agent.batch_check import semantic_checks, save
from agent.currency_review import currency_review_flags
from agent.dify_runner import DifyRunner, _NoRedirect, parse_object
PRIVATE=ROOT/'agent/.local/currency-wording-20261017'
STATUS=PRIVATE/'live-status.json'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()


def load():
    profile=parse_object((HERE/'preparation.json').read_bytes())
    raw=(ROOT/profile['suite_file']).read_bytes();assert sha(raw)==profile['suite_sha256']
    cases=parse_object(raw)['cases'];assert len(cases)==6 and len({c['case_id'] for c in cases})==6
    for case in cases:
        assert case['data_class']=='synthetic' and case['operation']=='extract'
        AgentService(None).validate(case['request'],'AgentExtractRequest')
    return cases,profile


def check(case,result):
    failures,flags=semantic_checks(case,result)
    flags.extend(currency_review_flags(result))
    for fact in result['candidate_facts']:
        if fact['field'] not in ('treatment.paid_cost',):failures.append('fact_without_input_basis')
        if fact['source_type']!='user_input' or fact['evidence_ids']:failures.append('wrong_source_or_evidence')
    if case['case_id']=='currency_exact_eur':
        paid=[f for f in result['candidate_facts'] if f['field']=='treatment.paid_cost']
        valid=False
        if len(paid)==1:
            value=paid[0]['value']
            if value['kind']=='money':valid=value['value']=={'currency':'EUR','amount_minor':1829}
            elif value['kind']=='text':
                text=value['value']
                valid=bool(re.search(r'18\.29',text)) and bool(re.search(r'EUR|欧元',text,re.I)) and not re.search(r'CNY|人民币|RMB',text,re.I)
        if not valid:failures.append('EUR_original_currency_or_amount_not_preserved')
    return sorted(set(failures)),sorted(set(flags))


def main(resume=False):
    cases,profile=load()
    if STATUS.exists():
        if not resume:raise SystemExit('Existing live run will not be repeated.')
        report=parse_object(STATUS.read_bytes())
        assert report['suite_sha256']==profile['suite_sha256'] and report['status']=='stopped_for_review'
        last=report['cases'][-1]
        decisions=parse_object((PRIVATE/'review-decisions.json').read_bytes())
        decision=decisions.get(last['case_id'],{})
        assert not last.get('failures') and last['status']=='needs_content_review'
        assert decision.get('response_sha256')==last['response_sha256'] and decision.get('disposition')=='safe_attribution_or_negation'
        report.setdefault('review_decisions',{})[last['case_id']]=decision
    else:
        assert not resume
        report=dict(started_at=now(),status='preflight',planned_cases=6,calls_attempted=0,
            automatic_retries=0,real_medical_inputs=0,app_info_requests_attempted=0,
            suite_sha256=profile['suite_sha256'],model_configuration_basis='prior configured deepseek-flash; no fresh DSL export',
            publication_basis='user reported manual prompt change published',cases=[],segments=[])
    attempted={r['case_id'] for r in report['cases']};assert len(attempted)==len(report['cases'])==report['calls_attempted']<=6
    segment=dict(index=len(report['segments'])+1,started_at=now());report['segments'].append(segment)
    remaining=[c for c in cases if c['case_id'] not in attempted]
    assert remaining
    credentials={};runner=None;secret=None;exit_code=1
    save(STATUS,report)
    try:
        credentials=parse_object(sys.stdin.readline());secret=credentials.get('extract')
        if not isinstance(secret,str) or not secret.startswith('app-'):raise AgentError('Application credential missing')
        req=Request('https://api.dify.ai/v1/info',headers={'Authorization':'Bearer '+secret})
        report['app_info_requests_attempted']+=1;save(STATUS,report)
        try:
            with build_opener(_NoRedirect()).open(req,timeout=30) as response:info=parse_object(response.read(65536))
        except HTTPError as exc:
            status=exc.code;exc.close();raise AgentError('App info HTTP error: '+str(status)) from None
        except (URLError,OSError):raise AgentError('App info network failed') from None
        if info.get('name')!='CareFund-信息抽取与追问-修订版':raise AgentError('Application identity mismatch')
        runner=DifyRunner(extract_api_key=secret,user='carefund_currency_regression_20261017',timeout=90)
        credentials.clear();secret=None;report['status']='running';save(STATUS,report)
        for case in remaining:
            assert report['calls_attempted']<6
            row=dict(case_id=case['case_id'],operation='extract',data_class='synthetic',
                request_sha256=sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode()),
                status='calling_real_api',segment=segment['index'])
            report['cases'].append(row);report['calls_attempted']+=1;save(STATUS,report);started=time.monotonic()
            try:
                result=runner('extract',case['request'])
                raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
                target=PRIVATE/(case['case_id']+'.response.json');assert not target.exists();target.write_bytes(raw)
                row.update(response_file=target.relative_to(ROOT).as_posix(),response_sha256=sha(raw))
                AgentService(lambda op,req:result).extract(case['request'])
                failures,flags=check(case,result)
                row.update(failures=failures,review_flags=flags,
                    status='automatic_checks_failed' if failures else 'needs_content_review' if flags else 'automatic_checks_passed')
            except AgentError as exc:row.update(status='boundary_or_transport_rejected',error=str(exc))
            except Exception as exc:row.update(status='local_error',error_type=type(exc).__name__)
            row['elapsed_seconds']=round(time.monotonic()-started,3)
            report['counts']=dict(Counter(r['status'] for r in report['cases']));save(STATUS,report)
            print(json.dumps({k:row[k] for k in ('case_id','status','elapsed_seconds')}),flush=True)
            if row['status']!='automatic_checks_passed':report['status']='stopped_for_review';break
        else:
            report['status']='completed_with_reviewed_flags' if report.get('review_decisions') else 'completed_automatic_checks_passed'
            exit_code=0
    except AgentError as exc:report.update(status='preflight_failed',error=str(exc))
    except Exception as exc:report.update(status='local_error',error_type=type(exc).__name__)
    finally:
        credentials.clear();runner=None;secret=None
        segment.update(finished_at=now(),calls_after=report['calls_attempted'],status=report['status'])
        report['finished_at']=now()
        attempted={r['case_id'] for r in report['cases']};report['unattempted_case_ids']=[c['case_id'] for c in cases if c['case_id'] not in attempted]
        save(STATUS,report);snap=PRIVATE/f"segment-{segment['index']:03d}.json";assert not snap.exists();save(snap,report)
        print(json.dumps({k:report[k] for k in ('status','calls_attempted','app_info_requests_attempted')}),flush=True)
    return exit_code


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    raise SystemExit(main(args.resume))
