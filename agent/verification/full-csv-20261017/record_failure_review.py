"""Record offline triage of recovered row 44, preserving its failure status."""
import json
import sqlite3
from prepare import HERE, ROOT, PRIVATE, sha


if __name__ == '__main__':
    inspection = json.loads((HERE / 'failure-inspection-002.json').read_bytes())
    assert inspection['status'] == 'recovered_exact_failed_request'
    assert inspection['strict_result_json'] == 'invalid'
    evidence = ROOT / inspection['detail_file']
    assert sha(evidence.read_bytes()) == inspection['detail_sha256']
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    original = json.loads(db.execute('SELECT record FROM attempts WHERE source_row=44').fetchone()[0])
    db.close()
    assert original['error'] == 'Dify returned invalid JSON'
    decision = {'44': {'disposition': 'confirmed_invalid_model_json_kept_failed_continue_new_rows',
                       'request_sha256': original['request_sha256'],
                       'evidence_file': inspection['detail_file'], 'evidence_sha256': inspection['detail_sha256'],
                       'reason': 'Recovered exact attempted request. Model missed closing object delimiter and required fact metadata. Strict rejection is correct; no JSON repair or metadata invention permitted.',
                       'not_fixed': True, 'retry_failed_row': False,
                       'continuation_scope': 'Only unattempted rows under the same aggregate 84712-call and CNY20 authorization. Known malformed JSON stays failed; pause for new error classes or 3 invalid-JSON cases in the latest 50 attempts.'}}
    with (PRIVATE / 'review-decisions.json').open('xb') as stream:
        stream.write((json.dumps(decision, ensure_ascii=False, indent=2) + '\n').encode())
    public = dict(source_row=44, disposition=decision['44']['disposition'], not_fixed=True,
                  raw_evidence_sha256=inspection['detail_sha256'], failed_case_retried=False,
                  new_generation_calls_by_review=0, continuation_budget_cny=20,
                  continuation_call_cap=84712, previous_calls_count_toward_same_cap=45)
    with (HERE / 'failure-review.json').open('xb') as stream:
        stream.write((json.dumps(public, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(public))
