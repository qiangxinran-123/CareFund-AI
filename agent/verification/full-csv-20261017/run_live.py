"""Independent per-row evaluation, append-only attempts, conservative cost stop.

No retries. Held privacy cases are never sent. Credentials arrive only on stdin.
An interrupted/unknown attempt remains charged at its reservation and is not repeated.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime, timezone
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError

from prepare import HERE, ROOT, PRIVATE, SOURCE, EXPECTED_SHA, sha

sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService, AgentError
from agent.batch_check import semantic_checks
from agent.currency_review import currency_review_flags
from agent.dify_runner import DifyRunner, _NoRedirect, parse_object
from agent.dify_question_format import main as question_format, VERSION as QUESTION_FORMAT_VERSION
import billing_checkpoint

MICROYUAN_PER_TOKEN = 8  # Highest current official Flash rate: CNY 8 / million tokens.
MAX_CALLS = 84712
# Preserve the original authorization/reservation fingerprint after later exports.
DSL = HERE / 'pre-format-extract-export.yml'
DSL_SHA = 'f4780099f9008ee478bdcc93409745641e7c75389f42232e1630adaee52511b6'
CURRENT_EXPORT = ROOT / 'agent/workflow.deepseek-extract.yml'
CURRENT_EXPORT_SHA = '560dc5f38b81d1ac9752eef123357fcfd7c6b2d25e8593214afdf0c5c3a0eae3'
DB = PRIVATE / 'attempts.sqlite3'
STOP = PRIVATE / 'STOP'


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    data = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()
    temporary = path.with_suffix('.tmp')
    temporary.write_bytes(data)
    temporary.replace(path)


def reservation(request):
    # Byte-based overestimate for this pinned one-LLM workflow, plus ample wrapper margin.
    # This is a local planning bound, not an upstream account spending limit.
    input_bound = len(DSL.read_bytes()) + len(json.dumps(request, ensure_ascii=False).encode()) + 32768
    return 2 * input_bound + 8192 * 8


class UsageResponse:
    def __init__(self, response, metadata, wire_path=None):
        self.response, self.metadata, self.wire_path = response, metadata, wire_path

    def __enter__(self):
        self.response.__enter__()
        return self

    def __exit__(self, *args):
        return self.response.__exit__(*args)

    def read(self, size):
        raw = self.response.read(size)
        if self.wire_path is not None:
            # Save HTTP-success bytes before interpreting inner model JSON.
            with self.wire_path.open('xb') as stream:
                stream.write(raw)
        try:
            data = parse_object(raw).get('data', {})
            tokens = data.get('total_tokens') if isinstance(data, dict) else None
            if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens > 0:
                self.metadata['total_tokens'] = tokens
        except AgentError:
            pass
        return raw


class UsageOpener:
    def __init__(self, opener, metadata, wire_path=None):
        self.opener, self.metadata, self.wire_path = opener, metadata, wire_path

    def open(self, *args, **kwargs):
        return UsageResponse(self.opener.open(*args, **kwargs), self.metadata, self.wire_path)


def check(case, result):
    item = dict(case, operation='extract')
    failures, flags = semantic_checks(item, result)
    flags.extend(currency_review_flags(result))
    if case['category'] in ('strict_minimal', 'empty'):
        for fact in result['candidate_facts']:
            if fact['field'] != 'patient.medical_summary' or fact['value']['kind'] != 'text':
                failures.append('fact_without_minimal_input_basis')
        if case['category'] == 'empty' and result['candidate_facts']:
            failures.append('fact_without_any_input')
    else:
        # Free text has no independent annotation; do not pretend this is content accuracy.
        flags.append('free_text_semantics_not_independently_annotated')
    for fact in result['candidate_facts']:
        if fact['source_type'] != 'user_input' or fact['evidence_ids']:
            failures.append('source_or_evidence_mismatch')
    return sorted(set(failures)), sorted(set(flags))


def inspect_question_format(wire, required_version=None):
    """Verify processing provenance; never label a policy-filled raw output valid."""
    body = parse_object(wire)
    outputs = body.get('data', {}).get('outputs', {})
    has_provenance = 'raw_result' in outputs or 'normalization_report' in outputs
    if not has_provenance:
        if required_version:
            raise AgentError('Expected question format provenance is missing')
        return {}
    if required_version not in (None, QUESTION_FORMAT_VERSION):
        raise AgentError('Unexpected question format policy version')
    raw = outputs.get('raw_result')
    if not isinstance(raw, str) or not isinstance(outputs.get('normalization_report'), str):
        raise AgentError('Question format provenance is incomplete')
    try:
        expected = question_format(raw)
    except ValueError:
        raise AgentError('Question format raw output is not eligible for normalization') from None
    report = parse_object(outputs['normalization_report'])
    if (report != parse_object(expected['normalization_report'])
            or outputs.get('result') != expected['result']):
        raise AgentError('Question format provenance or result mismatch')
    try:
        AgentService(None).validate(parse_object(raw), 'AgentExtractResponse')
        raw_valid = True
    except AgentError:
        raw_valid = False
    return {'question_format_version': report['version'],
            'question_policy_inserted_false_paths': report['inserted_false_paths'],
            'raw_model_contract_valid': raw_valid}


def call(case, key):
    started, metadata = time.monotonic(), {}
    result = {'case_id': case['case_id'], 'source_row': case['source_row']}
    runner = DifyRunner(extract_api_key=key, user='carefund_fullcsv_20261017', timeout=90)
    wire = PRIVATE / 'responses' / (case['case_id'] + '.wire.json')
    runner._opener = UsageOpener(runner._opener, metadata, wire)
    try:
        response = runner('extract', case['request'])
        raw = (json.dumps(response, ensure_ascii=False, indent=2) + '\n').encode()
        path = PRIVATE / 'responses' / (case['case_id'] + '.json')
        with path.open('xb') as stream:
            stream.write(raw)
        result.update(response_file=path.relative_to(ROOT).as_posix(), response_sha256=sha(raw))
        AgentService(lambda op, req: response).extract(case['request'])
        result.update(inspect_question_format(wire.read_bytes(), case.get('required_question_format_version')))
        failures, flags = check(case, response)
        result.update(failures=failures, review_flags=flags,
                      status='automatic_checks_failed' if failures else 'partial_checks_passed')
        actionable = [f for f in flags if f != 'free_text_semantics_not_independently_annotated']
        if actionable and not failures:
            result['status'] = 'needs_context_review'
    except AgentError as exc:
        result.update(status='boundary_or_transport_rejected', error=str(exc))
    except Exception as exc:
        result.update(status='local_error', error_type=type(exc).__name__)
    if wire.exists():
        result.update(wire_response_file=wire.relative_to(ROOT).as_posix(), wire_response_sha256=sha(wire.read_bytes()))
    result.update(total_tokens=metadata.get('total_tokens'), elapsed_seconds=round(time.monotonic() - started, 3))
    return result


def connect(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA synchronous=FULL')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS attempts (source_row INTEGER PRIMARY KEY, case_id TEXT UNIQUE NOT NULL, '
               'status TEXT NOT NULL, reservation INTEGER NOT NULL, charge INTEGER NOT NULL, record TEXT NOT NULL)')
    db.commit()
    return db


def claim(db, case, budget_micro):
    amount = reservation(case['request'])
    with db:
        used = db.execute('SELECT COALESCE(SUM(charge),0) FROM attempts').fetchone()[0]
        count = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
        if used + amount > budget_micro or count >= MAX_CALLS:
            return False
        record = {'case_id': case['case_id'], 'source_row': case['source_row'],
                  'request_sha256': sha(json.dumps(case['request'], ensure_ascii=False, sort_keys=True).encode()),
                  'category': case['category'], 'started_at': now()}
        epoch = db.execute("SELECT value FROM meta WHERE key='active_publication'").fetchone()
        if epoch:
            record['publication_basis'] = json.loads(epoch[0])
        # UNIQUE row claim is committed before dispatch: crashes never imply safe retry.
        db.execute('INSERT INTO attempts VALUES (?,?,?,?,?,?)',
                   (case['source_row'], case['case_id'], 'calling_or_unknown', amount, amount, json.dumps(record)))
    return True


def settle(db, result):
    old = db.execute('SELECT reservation,record FROM attempts WHERE source_row=?', (result['source_row'],)).fetchone()
    record = json.loads(old[1])
    record.update(result, finished_at=now())
    tokens = result.get('total_tokens')
    charge = tokens * MICROYUAN_PER_TOKEN if isinstance(tokens, int) and tokens > 0 else old[0]
    record['cost_upper_bound_micro_cny'] = charge
    record['cost_basis'] = 'reported_total_tokens_times_highest_rate' if tokens else 'unknown_usage_full_reservation'
    with db:
        db.execute('UPDATE attempts SET status=?,charge=?,record=? WHERE source_row=?',
                   (result['status'], charge, json.dumps(record, ensure_ascii=False), result['source_row']))
    return charge <= old[0]


def summary(db, state, started, mode='independent_rows'):
    rows = db.execute('SELECT status,COUNT(*) FROM attempts GROUP BY status').fetchall()
    counts = dict(rows)
    charge, attempted = db.execute('SELECT COALESCE(SUM(charge),0),COUNT(*) FROM attempts').fetchone()
    records = [json.loads(r[0]) for r in db.execute('SELECT record FROM attempts')]
    report = {'started_at': started, 'updated_at': now(), 'status': state, 'mode': mode,
              'authorized_max_generation_calls': MAX_CALLS, 'authorized_budget_cny': 20,
              'calls_attempted': attempted, 'counts': counts,
              'cost_upper_bound_cny': charge / 1000000,
              'automatic_retries': 0, 'actual_platform_bill_read': False,
              'question_policy_applied_calls': sum(bool(r.get('question_policy_inserted_false_paths')) for r in records),
              'raw_model_contract_rejections_recorded': sum(r.get('raw_model_contract_valid') is False for r in records),
              'all_source_rows': MAX_CALLS, 'held_for_local_review': 61,
              'not_attempted_rows': MAX_CALLS - attempted - 61,
              'unattempted_including_held_rows': MAX_CALLS - attempted,
              'all_rows_model_tested': attempted == MAX_CALLS and 'calling_or_unknown' not in counts,
              'scope': 'Only disease field, excluding other 22 columns. No draft calls. No clinical ground truth.',
              'budget_caveat': 'Conservative planning bound uses Dify total_tokens and pinned single-LLM DSL; not an upstream billing hard limit.'}
    control = billing_checkpoint.report(db, charge)
    if control is not None:
        report['budget_control'] = control
        report['budget_caveat'] = ('cost_upper_bound_cny preserves the historical all-token ledger estimate. '
            'Dispatch uses budget_control: user-reported bill baseline plus prior unknown usage allowance '
            'and conservative new-call reservations. This is not a machine-read bill or a provider hard limit.')
    with db:
        db.execute("INSERT OR REPLACE INTO meta VALUES ('last_progress',?)", (json.dumps(report),))
    save(HERE / 'live-progress.json', report)
    save(PRIVATE / 'live-status.json', report)
    return report


def resume_review(db):
    prior = db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()
    if not prior and (PRIVATE / 'live-status.json').exists():
        prior = ((PRIVATE / 'live-status.json').read_text(encoding='utf-8'),)
    prior_state = json.loads(prior[0])['status'] if prior else None
    if prior_state == 'paused_before_budget_or_call_limit':
        ceiling, checkpoint = billing_checkpoint.load(db)
        used, count = db.execute('SELECT COALESCE(SUM(charge),0),COUNT(*) FROM attempts').fetchone()
        if checkpoint is None or used >= ceiling or count >= MAX_CALLS:
            raise AgentError('Budget stop requires a valid bill checkpoint with remaining authorization.')
    elif prior and prior_state not in ('paused_on_finding_no_retry', 'paused_by_stop_file', 'paused_after_requested_segment'):
        raise AgentError('Previous stop state does not permit reviewed resume.')
    if db.execute("SELECT COUNT(*) FROM attempts WHERE status='calling_or_unknown'").fetchone()[0]:
        raise AgentError('Unknown in-flight attempt must be reconciled before resume.')
    decisions = parse_object((PRIVATE / 'review-decisions.json').read_bytes())
    publication = db.execute("SELECT value FROM meta WHERE key='active_publication'").fetchone()
    publication = json.loads(publication[0]) if publication else {}
    for row, state, raw, charge, reserve in db.execute("SELECT source_row,status,record,charge,reservation FROM attempts WHERE status!='partial_checks_passed'"):
        record = parse_object(raw)
        decision = decisions.get(str(row), {})
        invalid_json = (record.get('error') == 'Dify returned invalid JSON'
                        and decision.get('disposition') == 'confirmed_invalid_model_json_kept_failed_continue_new_rows')
        unknown_timeout = (record.get('error') == 'Dify network request failed or timed out; execution may still be running'
                           and decision.get('disposition') == 'network_unknown_no_retry_full_reservation_continue_new_rows'
                           and record.get('total_tokens') is None and charge == reserve
                           and decision.get('remote_execution_status') == 'unknown'
                           and decision.get('retry_failed_row') is False)
        recovered_timeout = (
            record.get('error') == 'Dify network request failed or timed out; execution may still be running'
            and decision.get('disposition') == 'recovered_exact_timeout_result_reviewed_no_retry_continue_new_rows'
            and record.get('total_tokens') is None and charge == reserve
            and decision.get('retry_failed_row') is False)
        missing_question_flag = (
            record.get('error') == 'Schema validation failed: AgentExtractResponse (required at schema properties/questions/items/required; missing required)'
            and decision.get('disposition') == 'confirmed_missing_question_required_kept_failed_continue_new_rows'
            and decision.get('retry_failed_row') is False
            and publication.get('question_format_version') == QUESTION_FORMAT_VERSION)
        reviewed_negation = (
            state == 'needs_context_review'
            and decision.get('disposition') == 'reviewed_negated_platform_warning_keep_original_continue_new_rows'
            and decision.get('retry_failed_row') is False
            and not record.get('failures')
            and set(record.get('review_flags', [])) - {'free_text_semantics_not_independently_annotated'}
                == {'platform_reference_needs_context_review'})
        if ((not reviewed_negation and (state != 'boundary_or_transport_rejected'
                or not (invalid_json or unknown_timeout or recovered_timeout or missing_question_flag)))
                or decision.get('request_sha256') != record['request_sha256']):
            raise AgentError('Unreviewed failure; no further calls.')
        path = (ROOT / decision['evidence_file']).resolve()
        if not path.is_relative_to(PRIVATE.resolve()) or sha(path.read_bytes()) != decision['evidence_sha256']:
            raise AgentError('Reviewed failure evidence changed.')
        if unknown_timeout:
            evidence = parse_object(path.read_bytes())
            if (evidence.get('original_attempt') != record
                    or evidence.get('lookup_status') != 'not_recovered'):
                raise AgentError('Unknown timeout triage does not match original attempt.')
        if recovered_timeout:
            validate_recovered_timeout(record, parse_object(path.read_bytes()), reserve)
        if missing_question_flag:
            normalized = question_format(path.read_text(encoding='utf-8'))
            if not parse_object(normalized['normalization_report'])['inserted_false_paths']:
                raise AgentError('Reviewed question failure does not need the specified policy.')
            AgentService(None).validate(parse_object(normalized['result']), 'AgentExtractResponse')
        if reviewed_negation:
            validate_negated_warning_review(record, parse_object(path.read_bytes()))
    if prior:
        return json.loads(prior[0])['started_at']
    raise AgentError('Previous run start/state not found.')


def validate_negated_warning_review(record, evidence):
    """Accept only an explicitly reviewed disclaimer; retain the original ledger result."""
    if (evidence.get('original_attempt') != record
            or evidence.get('classification') != 'negated_platform_warning_false_positive'):
        raise AgentError('Context review does not match original attempt.')
    response_path = (ROOT / record['response_file']).resolve()
    if (not response_path.is_relative_to(PRIVATE.resolve())
            or sha(response_path.read_bytes()) != record['response_sha256']):
        raise AgentError('Context review response changed.')
    response = parse_object(response_path.read_bytes())
    AgentService(None).validate(response, 'AgentExtractResponse')
    reviewed = evidence.get('reviewed_warning')
    index = evidence.get('warning_index')
    disclaimer = '不代表平台要求或审核结论。'
    if (type(index) is not int or not 0 <= index < len(response['warnings'])
            or not isinstance(reviewed, str) or response['warnings'][index] != reviewed
            or not reviewed.endswith(disclaimer)):
        raise AgentError('Reviewed warning is not the saved negative disclaimer.')
    # Remove only that reviewed disclaimer when checking for other actionable wording.
    # The original response, broad detector and all future stop behavior stay intact.
    response['warnings'][index] = reviewed[:-len(disclaimer)]
    failures, flags = semantic_checks({'operation': 'extract', 'expectation': {}}, response)
    if failures or flags:
        raise AgentError('Additional actionable wording still requires review.')


def validate_recovered_timeout(record, evidence, reserve):
    """Check the exact read-only recovery; keep the transport result and reservation."""
    if (evidence.get('original_attempt') != record
            or evidence.get('classification') != 'exact_timeout_result_recovered_and_checked'):
        raise AgentError('Recovered timeout review differs from original attempt.')
    path = (ROOT / evidence['detail_file']).resolve()
    if not path.is_relative_to(PRIVATE.resolve()) or sha(path.read_bytes()) != evidence['detail_sha256']:
        raise AgentError('Recovered timeout detail changed.')
    detail = parse_object(path.read_bytes())
    tokens = detail.get('total_tokens')
    if (detail.get('status') != 'succeeded' or type(tokens) is not int or tokens <= 0
            or tokens * MICROYUAN_PER_TOKEN > reserve):
        raise AgentError('Recovered execution failed or exceeds its original reservation.')
    inputs = detail.get('inputs')
    inputs = parse_object(inputs) if isinstance(inputs, str) else inputs
    request = parse_object(inputs['request_json'])
    if (request.get('application_id') != f"app_fullcsv_{record['source_row']:06d}"
            or sha(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()) != record['request_sha256']):
        raise AgentError('Recovered request does not match the attempted row.')
    outputs = detail.get('outputs')
    outputs = parse_object(outputs) if isinstance(outputs, str) else outputs
    response = parse_object(outputs['result'])
    AgentService(lambda op, req: response).extract(request)
    provenance = inspect_question_format(json.dumps({'data': {'outputs': outputs}}).encode(),
        record.get('publication_basis', {}).get('question_format_version'))
    # Use the original prepared expectations, never derive a weaker oracle from the output.
    with (PRIVATE / 'prepared-inputs.jsonl').open(encoding='utf-8') as stream:
        case = next((parse_object(line) for line in stream
                     if json.loads(line)['source_row'] == record['source_row']), None)
    if (not case or case['category'] == 'held_for_local_review' or case['request'] != request
            or case['category'] != record['category']):
        raise AgentError('Recovered row differs from prepared input.')
    failures, flags = check(case, response)
    if failures or set(flags) - {'free_text_semantics_not_independently_annotated'}:
        raise AgentError('Recovered result has an actionable validation finding.')
    return dict(total_tokens=tokens, recovered_status='partial_checks_passed',
                failures=failures, review_flags=flags, **provenance)


def identify(credentials):
    candidates = credentials.pop('candidates', [])
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 2:
        raise AgentError('One or two local Dify app credentials required')
    for key in candidates:
        if not isinstance(key, str) or not key.startswith('app-'):
            raise AgentError('Dify app credential format invalid')
        request = Request('https://api.dify.ai/v1/info', headers={'Authorization': 'Bearer ' + key})
        try:
            with build_opener(_NoRedirect()).open(request, timeout=30) as response:
                info = parse_object(response.read(65536))
        except HTTPError as exc:
            code = exc.code
            exc.close()
            raise AgentError('App identity HTTP error: ' + str(code)) from None
        except (URLError, OSError):
            raise AgentError('App identity network error') from None
        if info.get('name') == 'CareFund-信息抽取与追问-修订版' and info.get('mode', 'workflow') == 'workflow':
            return key
    raise AgentError('No matching extraction app credential')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=int, choices=(1, 2), default=2)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--segment-calls', type=int)
    args = parser.parse_args()
    if args.segment_calls is not None and not 1 <= args.segment_calls <= MAX_CALLS:
        raise SystemExit('Segment call limit must be within the aggregate call cap.')
    profile = parse_object((HERE / 'input-preparation.json').read_bytes())
    prepared = ROOT / profile['private_input_file']
    if sha(SOURCE.read_bytes()) != EXPECTED_SHA or sha(prepared.read_bytes()) != profile['private_input_file_sha256']:
        raise SystemExit('Input fingerprint changed; no calls made.')
    if sha(DSL.read_bytes()) != DSL_SHA:
        raise SystemExit('Pinned workflow changed; no calls made.')
    if sha(CURRENT_EXPORT.read_bytes()) != CURRENT_EXPORT_SHA:
        raise SystemExit('Verified local export changed; review configuration before calls.')
    budget_micro = 20_000_000
    approved = {'mode': 'independent_rows', 'max_calls': MAX_CALLS, 'budget_micro_cny': budget_micro,
                'input_sha256': profile['private_input_file_sha256'], 'dsl_sha256': DSL_SHA,
                'user_authorization': '2026-10-17: independent rows, at most 84712 calls, CNY20 cap'}
    db = connect(DB)
    previous = db.execute("SELECT value FROM meta WHERE key='authorization'").fetchone()
    if previous and json.loads(previous[0]) != approved:
        raise SystemExit('Authorization or prepared scope changed.')
    # An explicit bill checkpoint changes only the prospective accounting basis.
    # The original authorization, historical ledger and aggregate call cap remain intact.
    budget_micro, _ = billing_checkpoint.load(db)
    existing_count = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
    if existing_count and not args.resume:
        raise SystemExit('Existing attempts preserved. Resume requires inspecting previous stop reason; no automatic retries.')
    if args.resume and not existing_count:
        raise SystemExit('No previous attempts to resume.')
    reviewed_started = resume_review(db) if args.resume else now()
    publication = db.execute("SELECT value FROM meta WHERE key='active_publication'").fetchone()
    if publication:
        publication = json.loads(publication[0])
        for file_key, hash_key in (('candidate_dsl_file', 'candidate_dsl_sha256'), ('append_file', 'append_sha256')):
            if sha((ROOT / publication[file_key]).read_bytes()) != publication[hash_key]:
                raise SystemExit('Publication candidate fingerprint changed; no calls made.')
        if publication.get('question_format_version'):
            if sha((ROOT / publication['code_file']).read_bytes()) != publication['code_sha256']:
                raise SystemExit('Question format code fingerprint changed; no calls made.')
        if (ROOT / publication['candidate_dsl_file']).stat().st_size > DSL.stat().st_size + 32768:
            raise SystemExit('Publication candidate exceeds reserved input margin.')
    with db:
        db.execute("INSERT OR IGNORE INTO meta VALUES ('authorization',?)", (json.dumps(approved),))
    (PRIVATE / 'responses').mkdir(exist_ok=True)
    credentials = parse_object(sys.stdin.readline())
    started, state = reviewed_started, 'preflight'
    key, pending = None, {}
    attempted_rows = {row[0] for row in db.execute('SELECT source_row FROM attempts')}
    # A newly reported prompt publication gets a fresh stop-on-first-finding check.
    known_bad_json = bool(args.resume) and not publication
    summary(db, state, started)
    try:
        key = identify(credentials)
        credentials.clear()
        state = 'running'
        with prepared.open(encoding='utf-8') as stream, ThreadPoolExecutor(max_workers=args.workers) as pool:
            exhausted, stop_dispatch, segment_dispatched = False, False, 0
            while pending or not exhausted and not stop_dispatch:
                while len(pending) < args.workers and not exhausted and not stop_dispatch:
                    if args.segment_calls is not None and segment_dispatched >= args.segment_calls:
                        state, stop_dispatch = 'paused_after_requested_segment', True
                        break
                    if STOP.exists():
                        state, stop_dispatch = 'paused_by_stop_file', True
                        break
                    line = stream.readline()
                    if not line:
                        exhausted = True
                        break
                    case = parse_object(line)
                    if case['source_row'] in attempted_rows:
                        continue
                    if case['category'] == 'held_for_local_review':
                        continue
                    if not claim(db, case, budget_micro):
                        state, stop_dispatch = 'paused_before_budget_or_call_limit', True
                        break
                    if publication and publication.get('question_format_version'):
                        case['required_question_format_version'] = publication['question_format_version']
                    pending[pool.submit(call, case, key)] = case['source_row']
                    segment_dispatched += 1
                if not pending:
                    break
                done, _ = wait(pending, timeout=15, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    result = future.result()
                    if not settle(db, result):
                        state, stop_dispatch = 'paused_usage_exceeded_reservation_assumption', True
                    if result['status'] != 'partial_checks_passed':
                        known_failure = known_bad_json and result.get('error') == 'Dify returned invalid JSON'
                        recent = db.execute('SELECT record FROM attempts ORDER BY source_row DESC LIMIT 50').fetchall()
                        recent_invalid = sum(json.loads(r[0]).get('error') == 'Dify returned invalid JSON' for r in recent)
                        if not known_failure or recent_invalid >= 3:
                            state, stop_dispatch = 'paused_on_finding_no_retry', True
                report = summary(db, state, started)
                if done:
                    print(json.dumps({'status': state, 'calls_attempted': report['calls_attempted'],
                                      'counts': report['counts'], 'cost_upper_bound_cny': report['cost_upper_bound_cny']}), flush=True)
            if not stop_dispatch:
                state = 'finished_sendable_rows_with_privacy_holds'
    except AgentError as exc:
        state = 'preflight_or_transport_failed'
        print(json.dumps({'error': str(exc)}), flush=True)
    except Exception as exc:
        state = 'local_error'
        print(json.dumps({'error_type': type(exc).__name__}), flush=True)
    finally:
        credentials.clear()
        key = None
        report = summary(db, state, started)
        db.close()
        print(json.dumps(report), flush=True)
    return 0 if state == 'finished_sendable_rows_with_privacy_holds' else 1


if __name__ == '__main__':
    raise SystemExit(main())
