"""Bounded, reviewed evaluation. Credentials via stdin; no automatic retries."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import re
import sys
import time
from urllib.error import HTTPError,URLError
from urllib.request import Request,build_opener

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from agent.agent_service import AgentError,AgentService
from agent.batch_check import EXCERPT_PREFIX,EXCERPT_SUFFIX,save,semantic_checks
from agent.dify_runner import DifyRunner,_NoRedirect,parse_object
from agent.mdcc_prepare import CLAUSE

spec=importlib.util.spec_from_file_location('expanded_preparation',HERE/'prepare.py')
PREP=importlib.util.module_from_spec(spec);spec.loader.exec_module(PREP)
PRIVATE=PREP.PRIVATE
STATUS=PRIVATE/'live-status.json'


def now():return datetime.now(timezone.utc).isoformat()


def prepared_cases():
    profile=parse_object((HERE/'preparation.json').read_bytes())
    raw=(ROOT/profile['suite_file']).read_bytes()
    if PREP.sha(raw)!=profile['suite_sha256']:raise AgentError('Suite fingerprint mismatch')
    cases=parse_object(raw)['cases']
    if len(cases)!=100 or len({c['case_id'] for c in cases})!=100:raise AgentError('Expected one hundred unique prepared cases')
    service=AgentService(None)
    for case in cases:
        req=case['request'];kind=case['data_class']
        if kind in ('minimal_anonymous_chinese_disease_cell','minimal_anonymous_public_excerpt'):
            if set(req['user_input'])!={'description'} or req['candidate_facts'] or req['extracted_documents']:
                raise AgentError('Real excerpt envelope exceeded')
            text=req['user_input']['description']
            if kind=='minimal_anonymous_chinese_disease_cell':
                prefix,suffix=PREP.CN.PREFIX,PREP.CN.SUFFIX
                if not text.startswith(prefix) or not text.endswith(suffix):raise AgentError('CN envelope mismatch')
                phrase=text[len(prefix):-len(suffix)]
                projected=PREP.CN.projection(phrase)
                if not projected or projected[0]!=phrase:raise AgentError('CN dictionary exceeded')
            else:
                if not text.startswith(EXCERPT_PREFIX) or not text.endswith(EXCERPT_SUFFIX):raise AgentError('EN envelope mismatch')
                if not CLAUSE.fullmatch(text[len(EXCERPT_PREFIX):-len(EXCERPT_SUFFIX)]):raise AgentError('EN dictionary exceeded')
        elif kind!='synthetic':raise AgentError('Unreviewed input class rejected')
        if case['operation']=='extract':service.validate(req,'AgentExtractRequest')
        elif case['operation']=='draft':service.validate_draft_request(req)
        else:raise AgentError('Unknown operation')
    assert Counter(c['data_class'] for c in cases)=={'minimal_anonymous_chinese_disease_cell':60,
        'minimal_anonymous_public_excerpt':19,'synthetic':21}
    return cases,profile


def check(case,result):
    failures,flags=semantic_checks(case,result)
    if case['data_class']!='synthetic':
        fields={'patient.medical_summary'}
        if case['data_class']=='minimal_anonymous_public_excerpt':
            text=case['request']['user_input']['description'][len(EXCERPT_PREFIX):-len(EXCERPT_SUFFIX)]
            if 'relationship_any' in case['expectation'] or text.lower().startswith('i '):
                fields.add('patient.relationship_to_applicant')
        for fact in result['candidate_facts']:
            if fact['field'] not in fields:failures.append('fact_field_not_supplied_by_minimal_input')
            if fact['value']['kind']!='text':failures.append('minimal_input_not_preserved_as_text')
            if fact['source_type']!='user_input' or fact['evidence_ids']:
                failures.append('minimal_input_source_or_evidence_mismatch')
    if case['expectation'].get('no_reask_estimate_document'):
        for q in result['questions']:
            if re.search(r'(?:是否|有没有|有无).{0,12}(?:预估单|费用预估)|(?:预估单|费用预估).{0,8}(?:有吗|是否已有|有没有)',q['question']):
                flags.append('possible_reask_of_explicitly_absent_estimate_document')
    return sorted(set(failures)),sorted(set(flags))


class MeteredResponse:
    def __init__(self,response,owner):self.response,self.owner=response,owner
    def __enter__(self):self.response.__enter__();return self
    def __exit__(self,*args):return self.response.__exit__(*args)
    def read(self,length):
        raw=self.response.read(length)
        try:
            data=parse_object(raw).get('data',{})
            if isinstance(data,dict):
                for key in ('total_tokens','elapsed_time','total_steps'):
                    value=data.get(key)
                    if isinstance(value,(int,float)) and not isinstance(value,bool) and value>=0:
                        self.owner.metadata[key]=value
        except AgentError:pass
        return raw


class MeteredOpener:
    def __init__(self,base):self.base,self.metadata=base,{}
    def open(self,*args,**kwargs):return MeteredResponse(self.base.open(*args,**kwargs),self)


def main(resume=False):
    cases,profile=prepared_cases()
    if STATUS.exists():
        if not resume:raise SystemExit('Live status exists; explicit reviewed resume required.')
        report=parse_object(STATUS.read_bytes())
        if report['suite_sha256']!=profile['suite_sha256']:raise SystemExit('Cannot resume changed suite.')
        if report['status']!='stopped_for_review':raise SystemExit('This run is not pending a review.')
        decisions_path=PRIVATE/'review-decisions.json'
        decisions=parse_object(decisions_path.read_bytes()) if decisions_path.exists() else {}
        last=report['cases'][-1]
        decision=decisions.get(last['case_id'],{})
        if (decision.get('response_sha256')!=last.get('response_sha256') or
                decision.get('disposition')!='safe_false_positive'):
            raise SystemExit('Unresolved failure: no further calls.')
        report.setdefault('review_decisions',{})[last['case_id']]=decision
    else:
        if resume:raise SystemExit('No prior run to resume.')
        report=dict(started_at=now(),status='preflight',transport='real_dify_service_api',
            model_configured_in_dify='deepseek-flash',planned_cases=100,calls_attempted=0,
            authorized_scope='60 CN cells, 19 EN clauses, 21 synthetic cases; at most 100 generations',
            suite_sha256=profile['suite_sha256'],suite_file=profile['suite_file'],automatic_retries=0,
            full_original_records_sent=0,app_info_requests_attempted=0,cases=[],segments=[])
    attempted={r['case_id'] for r in report['cases']}
    assert len(attempted)==len(report['cases'])==report['calls_attempted']<=100
    assert attempted<={c['case_id'] for c in cases}
    remaining=[c for c in cases if c['case_id'] not in attempted]
    if not remaining:raise SystemExit('All approved cases already attempted; no calls made.')
    segment=dict(segment=len(report['segments'])+1,started_at=now(),calls_before=report['calls_attempted'])
    report['segments'].append(segment)
    save(STATUS,report)
    credentials={};runner=None;code=1
    try:
        credentials=parse_object(sys.stdin.readline())
        for operation,name in [('extract','CareFund-信息抽取与追问-修订版'),('draft','CareFund-已确认事实草稿-首版')]:
            secret=credentials.get(operation)
            if not isinstance(secret,str) or not secret.startswith('app-'):raise AgentError('Missing application credential')
            req=Request('https://api.dify.ai/v1/info',headers={'Authorization':'Bearer '+secret})
            report['app_info_requests_attempted']+=1;save(STATUS,report)
            try:
                with build_opener(_NoRedirect()).open(req,timeout=30) as response:info=parse_object(response.read(65536))
            except HTTPError as exc:
                status=exc.code;exc.close();raise AgentError('App info HTTP error: '+str(status)) from None
            except (URLError,OSError):raise AgentError('App info network failed') from None
            if info.get('name')!=name or info.get('mode','workflow')!='workflow':raise AgentError('Application identity mismatch')
        secret=None
        runner=DifyRunner(extract_api_key=credentials['extract'],draft_api_key=credentials['draft'],
                          user='carefund_expanded_evaluation_20261017',timeout=90)
        credentials.clear()
        meter=MeteredOpener(runner._opener);runner._opener=meter
        report['status']='running';save(STATUS,report)
        for case in remaining:
            if report['calls_attempted']>=100:raise AgentError('Approved call limit reached')
            record={k:case[k] for k in ('case_id','operation','group','data_class')}
            record.update(request_sha256=PREP.sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode()),
                          status='calling_real_api',segment=segment['segment'])
            report['cases'].append(record);report['calls_attempted']+=1;save(STATUS,report)
            started=time.monotonic();meter.metadata={}
            try:
                result=runner(case['operation'],case['request'])
                raw=(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
                p=PRIVATE/(case['case_id']+'.response.json')
                assert not p.exists();p.write_bytes(raw)
                record.update(response_file=p.relative_to(ROOT).as_posix(),response_sha256=PREP.sha(raw))
                getattr(AgentService(lambda op,req:result),case['operation'])(case['request'])
                failures,flags=check(case,result)
                record.update(strict_contract_and_policy='passed',failures=failures,review_flags=flags,
                    status='automatic_checks_failed' if failures else 'needs_content_review' if flags else 'automatic_checks_passed')
            except AgentError as exc:record.update(status='boundary_or_transport_rejected',error=str(exc))
            except Exception as exc:record.update(status='local_error',error_type=type(exc).__name__)
            record.update(elapsed_seconds=round(time.monotonic()-started,3),dify_usage_metadata=dict(meter.metadata))
            report['counts']=dict(Counter(r['status'] for r in report['cases']));save(STATUS,report)
            print(json.dumps({k:record[k] for k in ('case_id','status','elapsed_seconds')}),flush=True)
            if record['status']!='automatic_checks_passed':
                report['status']='stopped_for_review';break
        else:report['status']='completed_automatic_checks_passed';code=0
    except AgentError as exc:report.update(status='preflight_or_limit_failed',error=str(exc))
    except Exception as exc:report.update(status='local_error',error_type=type(exc).__name__)
    finally:
        credentials.clear();runner=None;secret=None
        segment.update(finished_at=now(),calls_after=report['calls_attempted'],status=report['status'])
        report['finished_at']=now()
        attempted={r['case_id'] for r in report['cases']}
        report['unattempted_case_ids']=[c['case_id'] for c in cases if c['case_id'] not in attempted]
        save(STATUS,report)
        snapshot=PRIVATE/f"segment-{segment['segment']:03d}.json"
        assert not snapshot.exists();save(snapshot,report)
        print(json.dumps({k:report[k] for k in ('status','calls_attempted','app_info_requests_attempted')}),flush=True)
    return code


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    raise SystemExit(main(args.resume))
