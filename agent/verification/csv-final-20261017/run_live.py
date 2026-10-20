"""At most 24 approved generation calls. Stdin credential, no retries.

Raw inputs and responses remain in ignored local storage. Existing output stops
the run rather than repeating calls. Failures/flags stop before the next case.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE)]
from agent.agent_service import AgentError, AgentService
from agent.batch_check import load_cases, save, semantic_checks
from agent.dify_runner import DifyRunner, _NoRedirect, parse_object
from prepare import PREFIX, SUFFIX, projection

PRIVATE = ROOT / 'agent/.local/csv-final-20261017'
STATUS = PRIVATE / 'live-status.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def prepared_cases():
    profile = parse_object((HERE/'preparation.json').read_bytes())
    suite_raw = (ROOT/profile['suite_file']).read_bytes()
    if sha(suite_raw) != profile['suite_sha256']:
        raise AgentError('Prepared suite fingerprint mismatch')
    suite = parse_object(suite_raw)
    if suite['source_file_sha256'] != profile['source_sha256']:
        raise AgentError('Source fingerprint mismatch')
    cases = suite['cases']
    if len(cases) != 20:
        raise AgentError('Expected exactly twenty prepared disease cells')
    for case in cases:
        req = case['request']
        description = req['user_input'].get('description', '')
        if (case['operation'] != 'extract' or case['data_class'] != 'minimal_anonymous_chinese_disease_cell'
                or set(req['user_input']) != {'description'} or req['extracted_documents']
                or req['candidate_facts'] or not description.startswith(PREFIX) or not description.endswith(SUFFIX)):
            raise AgentError('Disease-cell envelope is not the reviewed format')
        phrase = description[len(PREFIX):-len(SUFFIX)]
        match = projection(phrase)
        if match is None or match[0] != phrase:
            raise AgentError('Disease-cell input exceeds the reviewed dictionary')
        AgentService(None).validate(req, 'AgentExtractRequest')
    _, regressions = load_cases(PRIVATE/'known-content-regressions.json')
    if [c.get('historical_case_id') for c in regressions] != [
            'extract_0001','extract_0011','extract_0016','extract_0042']:
        raise AgentError('Historical regression inputs mismatch')
    ledger = parse_object((ROOT/'agent/verification/supplemental-progress.json').read_bytes())
    historical = {c['case_id']:c for c in ledger['cases']}
    for case in regressions:
        if sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode()) != historical[case['historical_case_id']]['request_sha256']:
            raise AgentError('Historical regression request fingerprint mismatch')
    combined = regressions + cases
    if len(combined) != 24 or len({c['case_id'] for c in combined}) != 24:
        raise AgentError('Expected twenty-four unique approved inputs')
    return combined, profile


def check(case, result):
    failures, flags = semantic_checks(case, result)
    if case['data_class'] == 'minimal_anonymous_chinese_disease_cell':
        for fact in result['candidate_facts']:
            if fact['field'] != 'patient.medical_summary':
                failures.append('fact_field_not_provided_by_disease_cell')
            if fact['value']['kind'] != 'text':
                failures.append('disease_cell_not_preserved_as_text')
            if fact['source_type'] != 'user_input' or fact['evidence_ids']:
                failures.append('disease_cell_not_unverified_user_statement')
    return sorted(set(failures)), sorted(set(flags))


def main():
    if STATUS.exists():
        raise SystemExit('Live report exists; calls will not be repeated.')
    cases, profile = prepared_cases()
    report = dict(started_at=datetime.now(timezone.utc).isoformat(),
        status='awaiting_stdin_credentials', transport='real_dify_service_api',
        model_configured_in_dify='deepseek-flash',
        configuration_evidence='agent/verification/deepseek-20261016/summary.json',
        planned_calls=24, approved_new_disease_cells=20, approved_historical_content_rechecks=4,
        source_file_sha256=profile['source_sha256'], suite_sha256=profile['suite_sha256'],
        calls_attempted=0, app_info_requests_attempted=0, automatic_retries=0,
        full_records_sent=0, cases=[])
    save(STATUS, report)
    runner, secret, credentials = None, None, {}
    exit_code = 1
    try:
        credentials = parse_object(sys.stdin.readline())
        secret = credentials.get('extract')
        if not isinstance(secret,str) or not secret.startswith('app-'):
            raise AgentError('Expected extraction application credential')
        req = Request('https://api.dify.ai/v1/info', headers={'Authorization':'Bearer '+secret})
        report['app_info_requests_attempted'] += 1
        save(STATUS, report)
        try:
            with build_opener(_NoRedirect()).open(req,timeout=30) as response:
                info = parse_object(response.read(65536))
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise AgentError('App info HTTP error: '+str(code)) from None
        except (URLError,OSError):
            raise AgentError('App info network request failed') from None
        if info.get('name') != 'CareFund-信息抽取与追问-修订版' or info.get('mode','workflow') != 'workflow':
            raise AgentError('App identity mismatch; no generation attempted')
        runner = DifyRunner(extract_api_key=secret, user='carefund_csv_content_recheck_20261017',timeout=90)
        secret = None
        credentials.clear()
        report['status'] = 'running'
        save(STATUS,report)
        for case in cases:
            record = {k:case[k] for k in ('case_id','operation','data_class','group')}
            if 'historical_case_id' in case:
                record['historical_case_id'] = case['historical_case_id']
            record['request_sha256'] = sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode())
            record['status'] = 'calling_real_api'
            report['cases'].append(record)
            report['calls_attempted'] += 1
            save(STATUS,report)
            started = time.monotonic()
            try:
                result = runner('extract',case['request'])
                response_raw = (json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode()
                response_file = PRIVATE/(case['case_id']+'.response.json')
                response_file.write_bytes(response_raw)
                record.update(response_file=response_file.relative_to(ROOT).as_posix(),
                              response_sha256=sha(response_raw))
                AgentService(lambda operation,request:result).extract(case['request'])
                failures,flags = check(case,result)
                record.update(failures=failures, review_flags=flags,strict_contract_and_policy='passed')
                record['status'] = ('automatic_checks_failed' if failures else 'needs_content_review'
                                    if flags else 'automatic_checks_passed')
            except AgentError as exc:
                record.update(status='boundary_or_transport_rejected',error=str(exc))
            except Exception as exc:
                record.update(status='local_error',error_type=type(exc).__name__)
            record['elapsed_seconds'] = round(time.monotonic()-started,3)
            report['counts'] = dict(Counter(c['status'] for c in report['cases']))
            save(STATUS,report)
            print(json.dumps({k:record[k] for k in ('case_id','status','elapsed_seconds')}),flush=True)
            if record['status'] != 'automatic_checks_passed':
                report['status'] = 'stopped_at_first_failure_or_review'
                break
        else:
            report['status'] = 'completed_automatic_checks_passed'
            exit_code = 0
    except AgentError as exc:
        report.update(status='preflight_or_app_info_failed',error=str(exc))
    except Exception as exc:
        report.update(status='local_error',error_type=type(exc).__name__)
    finally:
        credentials.clear()
        secret = None
        runner = None
        report['finished_at'] = datetime.now(timezone.utc).isoformat()
        attempted = {c['case_id'] for c in report['cases']}
        report['unattempted_case_ids'] = [c['case_id'] for c in cases if c['case_id'] not in attempted]
        save(STATUS,report)
        print(json.dumps({k:report[k] for k in ('status','calls_attempted','app_info_requests_attempted')}),flush=True)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
