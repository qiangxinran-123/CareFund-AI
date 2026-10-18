"""Offline publication-segment report, with original failures and cost retained."""
from collections import Counter
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import summary


def main():
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    prior = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    assert prior['status'] == 'paused_on_finding_no_retry'
    records = [json.loads(r[0]) for r in db.execute('SELECT record FROM attempts ORDER BY source_row')]
    current = [r for r in records if r.get('publication_basis', {}).get('epoch') == 'json-format-v4-user-reported']
    assert [r['source_row'] for r in current] == [82, 83, 84, 85]
    failures = []
    for record in current:
        wire = ROOT / record['wire_response_file']
        response = ROOT / record['response_file']
        assert sha(wire.read_bytes()) == record['wire_response_sha256']
        assert sha(response.read_bytes()) == record['response_sha256']
        parsed = json.loads(response.read_bytes())
        if record['status'] != 'partial_checks_passed':
            absent = [sorted({'question_id', 'field', 'question', 'reason', 'required'} - q.keys())
                      for q in parsed['questions']]
            assert absent == [['required']] * 3
            failures.append(dict(source_row=record['source_row'], json_syntax='valid',
                                 invalid_question_count=3, missing_fields=['required'],
                                 wire_sha256=record['wire_response_sha256'],
                                 response_sha256=record['response_sha256'], retried=False,
                                 required_inserted=False, original_status_retained=True))
    progress = summary(db, prior['status'], prior['started_at'])
    db.close()
    result = dict(publication_basis='user_reported_not_verified_by_fresh_dsl',
                  source_rows=[r['source_row'] for r in current], new_generation_calls=len(current),
                  new_status_counts=dict(Counter(r['status'] for r in current)),
                  valid_json_responses=4, schema_valid_partial_checks_passed=2,
                  failures=failures, historical_failures_not_retried=[44,70,78],
                  cumulative_attempts=progress['calls_attempted'],
                  cumulative_counts=progress['counts'],
                  cumulative_cost_upper_bound_cny=progress['cost_upper_bound_cny'],
                  actual_bill_read=False, all_rows_model_tested=False, held_for_local_review=61,
                  not_attempted_rows=progress['not_attempted_rows'],
                  conclusion='Two new outputs still violate the contract. Four valid JSON responses do not prove original syntax issue fixed.',
                  next_step='Verify newly published extraction DSL. Existing local candidate already specifies required=false; do not weaken response validation or retry old rows.',
                  external_calls_by_report=0)
    with (HERE / 'publication-v4-results.json').open('xb') as stream:
        stream.write((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
