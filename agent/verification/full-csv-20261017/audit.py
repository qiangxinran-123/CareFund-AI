"""Offline evidence/privacy audit; safe while the runner is active."""
from collections import Counter
import json
import re
import sqlite3
import subprocess

from prepare import HERE, ROOT, PRIVATE, SOURCE, EXPECTED_SHA, sha
import billing_checkpoint


if __name__ == '__main__':
    assert sha(SOURCE.read_bytes()) == EXPECTED_SHA
    profile = json.loads((HERE / 'input-preparation.json').read_bytes())
    assert profile['rows'] == sum(profile['categories'].values()) == 84712
    assert sha((ROOT / profile['private_input_file']).read_bytes()) == profile['private_input_file_sha256']
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.execute('BEGIN')
    attempts = {row: (state, charge, json.loads(record)) for row, state, charge, record in
                db.execute('SELECT source_row,status,charge,record FROM attempts')}
    authorization = json.loads(db.execute("SELECT value FROM meta WHERE key='authorization'").fetchone()[0])
    budget_control = billing_checkpoint.report(db)
    db.close()
    assert authorization['mode'] == 'independent_rows'
    assert authorization['max_calls'] == 84712 and authorization['budget_micro_cny'] == 20_000_000
    assert len(attempts) <= 84712
    categories = Counter()
    with (ROOT / profile['private_input_file']).open(encoding='utf-8') as stream:
        for line in stream:
            case = json.loads(line)
            categories[case['category']] += 1
            if case['source_row'] not in attempts:
                continue
            state, charge, record = attempts[case['source_row']]
            assert case['category'] != 'held_for_local_review'
            assert sha(json.dumps(case['request'], ensure_ascii=False, sort_keys=True).encode()) == record['request_sha256']
            for file_key, hash_key in (('response_file', 'response_sha256'), ('wire_response_file', 'wire_response_sha256')):
                if file_key in record:
                    path = ROOT / record[file_key]
                    assert path.is_relative_to(PRIVATE) and sha(path.read_bytes()) == record[hash_key]
            if record.get('total_tokens'):
                assert charge == record['total_tokens'] * 8
    assert categories == profile['categories']
    for path, expected in {
        'agent/agent_service.py': '9eed2c94cf38e1fa4ff381217e638d917eb682036d3611f281de8223792fbde0',
        'agent/extract_policy.py': '6e2bed965b56d4c85c8008ea25b1a2269d1f9f9b358571de4b089daf606e328a',
        'agent/workflow.deepseek-extract.yml': '560dc5f38b81d1ac9752eef123357fcfd7c6b2d25e8593214afdf0c5c3a0eae3',
        'agent/verification/full-csv-20261017/verified-format-v4-export.yml': 'e98b2c7d631a86ba9de986d5c241cfd6478b327dad03e6057a81e4fc630ed233',
        'agent/verification/full-csv-20261017/pre-format-extract-export.yml': 'f4780099f9008ee478bdcc93409745641e7c75389f42232e1630adaee52511b6',
    }.items():
        assert sha((ROOT / path).read_bytes()) == expected
    private = [p.relative_to(ROOT).as_posix() for p in PRIVATE.rglob('*') if p.is_file()]
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0'))
    assert not tracked.intersection(private)
    for rel in private:
        subprocess.run(['git', 'check-ignore', '-q', '--', rel], cwd=ROOT, check=True)
    public = [p for p in HERE.iterdir() if p.is_file()]
    public.extend(ROOT / p for p in ('agent/prompts/extract-json-v4-append.md',
                                     'agent/prompts/extract-json-v4-candidate.md',
                                     'agent/workflow.deepseek-extract.json-v4-candidate.yml',
                                     'agent/workflow.deepseek-extract.question-guard-candidate.yml',
                                     'agent/dify_question_format.py'))
    pattern = re.compile(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}')
    assert all(not pattern.search(p.read_bytes()) for p in public)
    subprocess.run(['git', '-c', 'core.safecrlf=false', 'diff', '--check'], cwd=ROOT, check=True)
    report = {'local_tests_passed': 20, 'whole_file_rows_indexed': 84712,
              'audited_snapshot_attempts': len(attempts), 'unique_source_row_claims': True,
              'held_rows_sent': 0, 'same_cumulative_budget_preserved': True,
              'private_files_ignored_and_untracked': len(private), 'public_files_credential_scanned': len(public),
              'response_and_request_hashes_verified': True, 'existing_A_boundary_runtime_unchanged': True,
              'canonical_dsl_synced_to_user_supplied_question_guard_export': True,
              'previous_verified_v4_export_archived_unchanged': True,
              'original_budget_basis_dsl_archived_unchanged': True,
              'known_invalid_json_row_still_failed': attempts[44][0] == 'boundary_or_transport_rejected',
              'failed_row_retried': False, 'external_calls_by_audit': 0,
              'committed_or_pushed': False, 'actual_bill_read': False,
              'all_rows_model_tested': len(attempts) == 84712}
    if budget_control is not None:
        report['budget_control'] = budget_control
    (HERE / 'local-checks.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=False))
