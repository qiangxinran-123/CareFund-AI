"""Record an offline, evidence-bound disclaimer review; never regenerate a row."""
import argparse
from datetime import datetime, timezone
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import resume_review, validate_negated_warning_review
import billing_checkpoint


def main(row, warning_index):
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    db.execute('BEGIN IMMEDIATE')
    before = db.execute('SELECT COUNT(*),SUM(charge),MAX(source_row) FROM attempts').fetchone()
    ceiling, _ = billing_checkpoint.load(db)
    assert before[2] == row and before[1] < ceiling
    assert db.execute("SELECT COUNT(*) FROM attempts WHERE status='calling_or_unknown'").fetchone()[0] == 0
    progress = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    assert progress['status'] == 'paused_on_finding_no_retry'
    state, raw = db.execute('SELECT status,record FROM attempts WHERE source_row=?', (row,)).fetchone()
    record = json.loads(raw)
    assert state == record['status'] == 'needs_context_review'
    assert not record['failures']
    assert set(record['review_flags']) - {'free_text_semantics_not_independently_annotated'} == {
        'platform_reference_needs_context_review'}
    response = json.loads((ROOT / record['response_file']).read_bytes())
    warning = response['warnings'][warning_index]
    evidence = dict(original_attempt=record, classification='negated_platform_warning_false_positive',
                    warning_index=warning_index, reviewed_warning=warning,
                    reason='The warning explicitly denies a platform requirement or review conclusion. '
                           'The saved response was inspected locally; no other actionable wording is waived.')
    validate_negated_warning_review(record, evidence)
    decisions_file = PRIVATE / 'review-decisions.json'
    decisions = json.loads(decisions_file.read_bytes())
    assert str(row) not in decisions
    evidence_path = PRIVATE / f'context-{row:06d}-review.json'
    encoded = (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()
    with evidence_path.open('xb') as stream:
        stream.write(encoded)
    decisions[str(row)] = dict(
        disposition='reviewed_negated_platform_warning_keep_original_continue_new_rows',
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
        classification=evidence['classification'], warning_index=warning_index,
        reviewed_disclaimer='不代表平台要求或审核结论。',
        original_status_preserved=True, original_cost_preserved=True, generation_calls=0,
        cumulative_calls=before[0], cumulative_cost_upper_bound_cny=before[1] / 1e6,
        failed_row_retried=False, global_detector_unchanged=True,
        next_action='Continue only unattempted rows, one worker, same cumulative CNY20 cap; stop on new findings.')
    if budget_control is not None:
        report['budget_control'] = budget_control
    with (HERE / f'context-{row:06d}-resume-review.json').open('xb') as stream:
        stream.write((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--row', type=int, required=True)
    parser.add_argument('--warning-index', type=int, required=True)
    args = parser.parse_args()
    main(args.row, args.warning_index)
