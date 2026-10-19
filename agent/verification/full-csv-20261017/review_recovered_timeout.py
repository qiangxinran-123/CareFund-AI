"""Validate read-only recovery without a generation call or ledger rewrite."""
import argparse
from datetime import datetime, timezone
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import CURRENT_EXPORT, CURRENT_EXPORT_SHA, resume_review, validate_recovered_timeout
import billing_checkpoint


def main(row, inspection):
    lookup = (HERE / inspection).resolve()
    assert lookup.parent == HERE.resolve()
    result = json.loads(lookup.read_bytes())
    assert result['generation_calls'] == 0 and result['status'] == 'recovered_exact_failed_request'
    assert result['source_row'] == row
    assert sha(CURRENT_EXPORT.read_bytes()) == CURRENT_EXPORT_SHA
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    db.execute('BEGIN IMMEDIATE')
    before = db.execute('SELECT COUNT(*),SUM(charge),MAX(source_row) FROM attempts').fetchone()
    ceiling, _ = billing_checkpoint.load(db)
    assert before[2] == row and before[1] < ceiling
    assert db.execute("SELECT COUNT(*) FROM attempts WHERE status='calling_or_unknown'").fetchone()[0] == 0
    progress = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    assert progress['status'] == 'paused_on_finding_no_retry'
    state, raw, charge, reserve = db.execute(
        'SELECT status,record,charge,reservation FROM attempts WHERE source_row=?', (row,)).fetchone()
    record = json.loads(raw)
    assert state == record['status'] == 'boundary_or_transport_rejected'
    assert record['error'] == 'Dify network request failed or timed out; execution may still be running'
    assert record.get('total_tokens') is None and charge == reserve
    evidence = dict(original_attempt=record, classification='exact_timeout_result_recovered_and_checked',
        lookup_file=lookup.relative_to(ROOT).as_posix(), lookup_sha256=sha(lookup.read_bytes()),
        detail_file=result['detail_file'], detail_sha256=result['detail_sha256'])
    evaluation = validate_recovered_timeout(record, evidence, reserve)
    evidence['recovered_evaluation'] = evaluation
    decisions_file = PRIVATE / 'review-decisions.json'
    decisions = json.loads(decisions_file.read_bytes())
    assert str(row) not in decisions
    evidence_path = PRIVATE / f'timeout-{row:06d}-recovered-review.json'
    encoded = (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()
    with evidence_path.open('xb') as stream:
        stream.write(encoded)
    decisions[str(row)] = dict(
        disposition='recovered_exact_timeout_result_reviewed_no_retry_continue_new_rows',
        request_sha256=record['request_sha256'], evidence_file=evidence_path.relative_to(ROOT).as_posix(),
        evidence_sha256=sha(encoded), retry_failed_row=False)
    temporary = decisions_file.with_suffix('.tmp')
    temporary.write_bytes((json.dumps(decisions, ensure_ascii=False, indent=2) + '\n').encode())
    temporary.replace(decisions_file)
    resume_review(db)
    assert db.execute('SELECT COUNT(*),SUM(charge),MAX(source_row) FROM attempts').fetchone() == before
    assert db.execute('SELECT record FROM attempts WHERE source_row=?', (row,)).fetchone()[0] == raw
    budget_control = billing_checkpoint.report(db, before[1])
    db.close()
    report = dict(reviewed_at=datetime.now(timezone.utc).isoformat(), source_row=row,
        inspection_file=lookup.relative_to(ROOT).as_posix(), generation_calls=0,
        remote_execution_status='succeeded', recovered_result_checks=evaluation,
        original_transport_status_and_full_reservation_preserved=True, failed_row_retried=False,
        cumulative_calls=before[0], cumulative_cost_upper_bound_cny=before[1] / 1e6,
        actual_bill_read=False,
        next_action='Continue only unattempted rows, one worker, same cumulative CNY20 cap; stop on findings.')
    if budget_control is not None:
        report['budget_control'] = budget_control
    with (HERE / f'timeout-{row:06d}-resume-review.json').open('xb') as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--row', type=int, required=True)
    parser.add_argument('--inspection', required=True)
    args = parser.parse_args()
    main(args.row, args.inspection)
