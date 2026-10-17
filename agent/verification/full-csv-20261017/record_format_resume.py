"""Offline triage and user-reported publication record. Never retries failed rows."""
import json
import sqlite3
from datetime import datetime, timezone

from prepare import HERE, ROOT, PRIVATE, sha


def main():
    progress = (HERE / 'live-progress.json').read_bytes()
    assert json.loads(progress)['calls_attempted'] == 81
    snapshot = HERE / 'phase2-progress.json'
    with snapshot.open('xb') as stream:
        stream.write(progress)
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    old_totals = db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone()
    decisions = json.loads((PRIVATE / 'review-decisions.json').read_bytes())
    assert '70' not in decisions and '78' not in decisions
    row70 = json.loads(db.execute('SELECT record FROM attempts WHERE source_row=70').fetchone()[0])
    wire = ROOT / row70['wire_response_file']
    assert sha(wire.read_bytes()) == row70['wire_response_sha256']
    assert row70['error'] == 'Dify returned invalid JSON'
    try:
        json.loads(json.loads(wire.read_bytes())['data']['outputs']['result'])
    except json.JSONDecodeError:
        pass
    else:
        raise AssertionError('Expected original malformed model JSON')
    decisions['70'] = dict(disposition='confirmed_invalid_model_json_kept_failed_continue_new_rows',
                          request_sha256=row70['request_sha256'], evidence_file=row70['wire_response_file'],
                          evidence_sha256=row70['wire_response_sha256'], not_fixed=True, retry_failed_row=False)
    row78 = json.loads(db.execute('SELECT record FROM attempts WHERE source_row=78').fetchone()[0])
    assert row78['cost_basis'] == 'unknown_usage_full_reservation'
    lookup_file = HERE / 'failure-inspection-row000078.json'
    lookup = json.loads(lookup_file.read_bytes())
    assert lookup['status'] == 'not_recovered' and lookup['generation_calls'] == 0
    evidence = dict(original_attempt=row78, lookup_status=lookup['status'],
                    lookup_file=lookup_file.relative_to(ROOT).as_posix(),
                    lookup_sha256=sha(lookup_file.read_bytes()), remote_execution_status='unknown',
                    interpretation='Bounded lookup found no match. This does not prove cancellation or non-execution.',
                    disposition='Keep original timeout, full reservation and call count; never resend row 78.')
    evidence_file = PRIVATE / 'timeout-000078-triage.json'
    with evidence_file.open('xb') as stream:
        stream.write((json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode())
    decisions['78'] = dict(disposition='network_unknown_no_retry_full_reservation_continue_new_rows',
                          request_sha256=row78['request_sha256'], evidence_file=evidence_file.relative_to(ROOT).as_posix(),
                          evidence_sha256=sha(evidence_file.read_bytes()), remote_execution_status='unknown',
                          retry_failed_row=False, usage='full_reservation_retained')
    (PRIVATE / 'review-decisions.json').write_bytes((json.dumps(decisions, ensure_ascii=False, indent=2) + '\n').encode())
    candidate = ROOT / 'agent/workflow.deepseek-extract.json-v4-candidate.yml'
    append = ROOT / 'agent/prompts/extract-json-v4-append.md'
    publication = dict(epoch='json-format-v4-user-reported', recorded_at=datetime.now(timezone.utc).isoformat(),
                       user_statement='已追加并发布', publication_verified_by_export=False,
                       original_attempts=81, starts_after_source_row=81,
                       candidate_dsl_file=candidate.relative_to(ROOT).as_posix(), candidate_dsl_sha256=sha(candidate.read_bytes()),
                       append_file=append.relative_to(ROOT).as_posix(), append_sha256=sha(append.read_bytes()),
                       note='User reports appending this rule and publishing. Fresh exported online DSL is not available. Historical attempts are unchanged.',
                       cumulative_budget_cny=20, cumulative_call_cap=84712,
                       retry_failed_rows=False, new_generation_calls_by_recording=0)
    with (HERE / 'publication-v4.json').open('xb') as stream:
        stream.write((json.dumps(publication, ensure_ascii=False, indent=2) + '\n').encode())
    with db:
        db.execute("INSERT INTO meta VALUES ('active_publication',?)", (json.dumps(publication, ensure_ascii=False),))
    assert db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone() == old_totals
    db.close()
    print(json.dumps(dict(recorded_publication=True, preserved_attempts=old_totals[0],
                          preserved_cost_upper_bound_cny=old_totals[1]/1e6, new_generation_calls=0)))


if __name__ == '__main__':
    main()
