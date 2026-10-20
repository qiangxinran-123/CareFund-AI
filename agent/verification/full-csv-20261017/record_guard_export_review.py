"""Record verified saved configuration and bounded timeout triage, without retrying."""
from datetime import datetime, timezone
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import CURRENT_EXPORT, CURRENT_EXPORT_SHA, resume_review


def main():
    verification = json.loads((HERE / 'verified-question-guard-export.json').read_bytes())
    assert verification['supplied_export_sha256'] == CURRENT_EXPORT_SHA == sha(CURRENT_EXPORT.read_bytes())
    assert verification['graph_and_three_string_outputs_verified']
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    before = db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone()
    assert before == (88, 1822656)
    snapshot = (HERE / 'live-progress.json').read_bytes()
    assert json.loads(snapshot)['calls_attempted'] == 88
    with (HERE / 'phase4-progress.json').open('xb') as stream:
        stream.write(snapshot)
    decisions = json.loads((PRIVATE / 'review-decisions.json').read_bytes())
    lookups = {87: 'failure-inspection-003.json', 88: 'failure-inspection-row000088.json'}
    for row, filename in lookups.items():
        assert str(row) not in decisions
        lookup = HERE / filename
        lookup_data = json.loads(lookup.read_bytes())
        assert lookup_data['status'] == 'not_recovered' and lookup_data['generation_calls'] == 0
        record_raw, charge, reserve = db.execute(
            'SELECT record,charge,reservation FROM attempts WHERE source_row=?', (row,)).fetchone()
        record = json.loads(record_raw)
        assert record['error'] == 'Dify network request failed or timed out; execution may still be running'
        assert record.get('total_tokens') is None and charge == reserve
        evidence = dict(original_attempt=record, lookup_status='not_recovered',
            lookup_file=lookup.relative_to(ROOT).as_posix(), lookup_sha256=sha(lookup.read_bytes()),
            scope='Bounded read-only logs and details, not proof of remote non-execution.',
            remote_execution_status='unknown', retry_failed_row=False)
        path = PRIVATE / f'timeout-{row:06d}-triage.json'
        data = (json.dumps(evidence, ensure_ascii=False, indent=2)+'\n').encode()
        with path.open('xb') as stream:
            stream.write(data)
        decisions[str(row)] = dict(
            disposition='network_unknown_no_retry_full_reservation_continue_new_rows',
            request_sha256=record['request_sha256'], evidence_file=path.relative_to(ROOT).as_posix(),
            evidence_sha256=sha(data), remote_execution_status='unknown', retry_failed_row=False,
            reason='Read-only lookup did not recover result. Retain original unknown result and full charge; only test a new source row, one at a time, stopping on first finding.')
    (PRIVATE / 'review-decisions.json').write_bytes((json.dumps(decisions, ensure_ascii=False, indent=2)+'\n').encode())
    publication = json.loads(db.execute("SELECT value FROM meta WHERE key='active_publication'").fetchone()[0])
    previous = json.dumps(publication, ensure_ascii=False)
    publication.update(saved_configuration_verified_by_export=True,
        verified_export_sha256=CURRENT_EXPORT_SHA,
        verified_export_file=CURRENT_EXPORT.relative_to(ROOT).as_posix(),
        export_verification_file=(HERE/'verified-question-guard-export.json').relative_to(ROOT).as_posix(),
        verification_observed_after_source_row=88,
        export_verified_at=verification['verified_at'])
    with db:
        db.execute("INSERT INTO meta VALUES ('publication_before_guard_export_verification',?)", (previous,))
        db.execute("UPDATE meta SET value=? WHERE key='active_publication'", (json.dumps(publication, ensure_ascii=False),))
    resume_review(db)
    assert db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone() == before
    db.close()
    report = dict(recorded_at=datetime.now(timezone.utc).isoformat(),
        saved_configuration_export_verified=True, export_sha256=CURRENT_EXPORT_SHA,
        timeout_rows_reviewed=[87,88], remote_execution_still_unknown=True,
        full_unknown_usage_reservations_preserved=True, original_results_unchanged=True,
        cumulative_calls=88, cumulative_cost_upper_bound_cny=1.822656,
        next_step='One new independent row with one worker, stop on first finding; no failed rows retried.',
        generation_calls=0, actual_bill_read=False)
    with (HERE / 'guard-export-resume-review.json').open('xb') as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode())
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
