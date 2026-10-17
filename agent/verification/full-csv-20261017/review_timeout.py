"""Record a reviewed, unrecovered transport timeout; no requests or retries.

Keep the original result and its full reservation. Only a later unattempted row
may be dispatched by run_live after its own identity and budget checks.
"""
import argparse
from datetime import datetime, timezone
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import CURRENT_EXPORT, CURRENT_EXPORT_SHA, resume_review
import billing_checkpoint


def main(row, inspection):
    lookup = (HERE / inspection).resolve()
    assert lookup.parent == HERE.resolve()
    result = json.loads(lookup.read_bytes())
    assert result['generation_calls'] == 0 and result['status'] == 'not_recovered'
    assert (result.get('source_row') == row
            or lookup.name == f'failure-inspection-row{row:06d}.json')
    assert sha(CURRENT_EXPORT.read_bytes()) == CURRENT_EXPORT_SHA
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    db.execute('BEGIN IMMEDIATE')
    before = db.execute('SELECT COUNT(*),SUM(charge),MAX(source_row) FROM attempts').fetchone()
    ceiling, _ = billing_checkpoint.load(db)
    assert before[2] == row and before[1] < ceiling
    assert db.execute("SELECT COUNT(*) FROM attempts WHERE status='calling_or_unknown'").fetchone()[0] == 0
    progress = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    assert progress['status'] == 'paused_on_finding_no_retry'
    raw, charge, reserve = db.execute('SELECT record,charge,reservation FROM attempts WHERE source_row=?', (row,)).fetchone()
    record = json.loads(raw)
    assert record['status'] == 'boundary_or_transport_rejected'
    assert record['error'] == 'Dify network request failed or timed out; execution may still be running'
    assert record.get('total_tokens') is None and charge == reserve
    decisions_file = PRIVATE / 'review-decisions.json'
    decisions = json.loads(decisions_file.read_bytes())
    assert str(row) not in decisions
    triage = dict(original_attempt=record, lookup_status='not_recovered',
        lookup_file=lookup.relative_to(ROOT).as_posix(), lookup_sha256=sha(lookup.read_bytes()),
        remote_execution_status='unknown', retry_failed_row=False,
        scope='Bounded successful read-only lookup. Absence is not proof of remote non-execution or zero cost.')
    evidence = PRIVATE / f'timeout-{row:06d}-triage.json'
    encoded = (json.dumps(triage, ensure_ascii=False, indent=2)+'\n').encode()
    with evidence.open('xb') as stream:
        stream.write(encoded)
    decisions[str(row)] = dict(
        disposition='network_unknown_no_retry_full_reservation_continue_new_rows',
        request_sha256=record['request_sha256'], evidence_file=evidence.relative_to(ROOT).as_posix(),
        evidence_sha256=sha(encoded), remote_execution_status='unknown', retry_failed_row=False,
        reason='User requested continuing after this pause; bounded read-only inspection recovered no result. Retain full reservation and continue only new rows, stopping on any new finding.')
    temporary = decisions_file.with_suffix('.tmp')
    temporary.write_bytes((json.dumps(decisions, ensure_ascii=False, indent=2)+'\n').encode())
    temporary.replace(decisions_file)
    resume_review(db)
    assert db.execute('SELECT COUNT(*),SUM(charge),MAX(source_row) FROM attempts').fetchone() == before
    budget_control = billing_checkpoint.report(db, before[1])
    db.close()
    report = dict(reviewed_at=datetime.now(timezone.utc).isoformat(), source_row=row,
        remote_execution_status='unknown', lookup_file=lookup.relative_to(ROOT).as_posix(),
        original_result_and_full_reservation_preserved=True, failed_row_retried=False,
        generation_calls=0, cumulative_calls=before[0], cumulative_cost_upper_bound_cny=before[1]/1e6,
        next_action='Continue new independent rows, same cumulative cap, one worker, stop on first finding.',
        actual_bill_read=False)
    if budget_control is not None:
        report['budget_control'] = budget_control
    with (HERE / f'timeout-{row:06d}-resume-review.json').open('xb') as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode())
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--row', type=int, required=True)
    parser.add_argument('--inspection', required=True)
    args = parser.parse_args()
    main(args.row, args.inspection)
