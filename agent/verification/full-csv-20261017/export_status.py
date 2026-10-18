"""Export a local per-row coverage snapshot without making model calls."""
from collections import Counter
import csv
import json
from pathlib import Path
import sqlite3
import sys

from prepare import HERE, ROOT, PRIVATE, sha


def main():
    profile = json.loads((HERE / 'input-preparation.json').read_bytes())
    inputs = ROOT / profile['private_input_file']
    if sha(inputs.read_bytes()) != profile['private_input_file_sha256']:
        raise SystemExit('Prepared input fingerprint changed.')
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    with db:
        attempts = {row: json.loads(record) | {'model_status': state}
                    for row, state, record in db.execute('SELECT source_row,status,record FROM attempts')}
    db.close()
    counts, flags, tokens, elapsed = Counter(), Counter(), 0, 0
    guard_calls, policy_applied, raw_rejections = 0, 0, 0
    output = PRIVATE / 'row-results.csv'
    temp = output.with_suffix('.tmp')
    columns = ('source_row', 'case_id', 'input_category', 'model_status',
               'response_sha256', 'total_tokens', 'elapsed_seconds', 'failure_codes', 'review_codes',
               'question_format_version', 'raw_model_contract_valid', 'question_policy_inserted_false_count')
    with inputs.open(encoding='utf-8') as stream, temp.open('w', encoding='utf-8-sig', newline='') as out:
        writer = csv.DictWriter(out, columns)
        writer.writeheader()
        for line in stream:
            case = json.loads(line)
            attempt = attempts.get(case['source_row'])
            status = attempt['model_status'] if attempt else 'held_for_local_review' if case['category'] == 'held_for_local_review' else 'not_attempted'
            counts[status] += 1
            record = dict(source_row=case['source_row'], case_id=case['case_id'],
                          input_category=case['category'], model_status=status)
            if attempt:
                for key in ('response_sha256', 'total_tokens', 'elapsed_seconds'):
                    record[key] = attempt.get(key)
                record['failure_codes'] = '|'.join(attempt.get('failures', []))
                record['review_codes'] = '|'.join(attempt.get('review_flags', []))
                record['question_format_version'] = attempt.get('question_format_version','')
                record['raw_model_contract_valid'] = attempt.get('raw_model_contract_valid','')
                record['question_policy_inserted_false_count'] = len(attempt.get('question_policy_inserted_false_paths',[]))
                guard_calls += bool(attempt.get('question_format_version'))
                policy_applied += bool(attempt.get('question_policy_inserted_false_paths'))
                raw_rejections += attempt.get('raw_model_contract_valid') is False
                flags.update(attempt.get('review_flags', []))
                tokens += attempt.get('total_tokens') or 0
                elapsed += attempt.get('elapsed_seconds') or 0
                if attempt.get('response_file'):
                    if sha((ROOT / attempt['response_file']).read_bytes()) != attempt['response_sha256']:
                        raise SystemExit('Saved response fingerprint mismatch.')
            writer.writerow(record)
    temp.replace(output)
    progress = json.loads((HERE / 'live-progress.json').read_bytes())
    report = dict(snapshot_time=progress['updated_at'], runner_status=progress['status'],
                  snapshot_attempts=len(attempts), source_rows=sum(counts.values()), row_counts=dict(counts),
                  review_flag_counts=dict(flags), dify_reported_total_tokens=tokens,
                  responses_with_verified_question_format_provenance=guard_calls,
                  question_policy_applied_calls=policy_applied,
                  raw_model_contract_rejections_recorded=raw_rejections,
                  sum_completed_call_seconds=round(elapsed, 3),
                  private_row_results=output.relative_to(ROOT).as_posix(), row_results_sha256=sha(output.read_bytes()),
                  automatic_semantic_limits='Free-text meanings are not independently annotated; partial checks are not an accuracy score.',
                  external_calls_by_this_script=0, actual_provider_bill_read=False)
    (HERE / 'coverage-snapshot.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
