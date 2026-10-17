"""Verify saved private evidence without API calls or printing patient text."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT), str(HERE)]
from agent.agent_service import AgentError, AgentService
from agent.dify_runner import parse_object
from run_live import check, prepared_cases, sha


if __name__ == '__main__':
    path = HERE/'summary.json'
    if not path.exists():
        raise SystemExit('Public live summary unavailable; no replay performed.')
    summary = parse_object(path.read_bytes())
    cases, profile = prepared_cases()
    by_id = {c['case_id']:c for c in cases}
    assert summary['source_file_sha256'] == profile['source_sha256']
    assert summary['suite_sha256'] == profile['suite_sha256']
    assert summary['automatic_retries'] == summary['full_records_sent'] == 0
    assert summary['calls_attempted'] == len(summary['cases']) <= 24
    assert len({c['case_id'] for c in summary['cases']}) == len(summary['cases'])
    counts = Counter()
    for row in summary['cases']:
        case = by_id[row['case_id']]
        assert sha(json.dumps(case['request'],ensure_ascii=False,sort_keys=True).encode()) == row['request_sha256']
        if 'response_file' not in row:
            assert row['status'] in ('boundary_or_transport_rejected','local_error')
            counts['without_saved_response'] += 1
            continue
        raw = (ROOT/row['response_file']).read_bytes()
        assert sha(raw) == row['response_sha256']
        result = parse_object(raw)
        try:
            assert AgentService(lambda op,req:result).extract(case['request']) == result
        except AgentError as exc:
            assert row['status'] == 'boundary_or_transport_rejected'
            assert str(exc) == row['error']
            counts['recorded_boundary_rejection_reproduced'] += 1
            continue
        failures,flags = check(case,result)
        assert failures == row['failures'] and flags == row['review_flags']
        status = ('automatic_checks_failed' if failures else 'needs_content_review'
                  if flags else 'automatic_checks_passed')
        assert status == row['status']
        counts[status] += 1
    assert set(summary['unattempted_case_ids']) == set(by_id)-{c['case_id'] for c in summary['cases']}
    print(json.dumps({'offline_saved_result_checks':dict(counts),'new_api_calls':0,'patient_text_printed':False}))
