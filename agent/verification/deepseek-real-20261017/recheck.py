"""Offline replay of private minimal-excerpt evidence; never makes API calls.

The suite and responses intentionally stay in ignored local storage. A recipient
without them cannot reproduce this replay from the public status report alone.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentError, AgentService
from agent.batch_check import load_cases, semantic_checks
from agent.dify_runner import parse_object

summary = parse_object((HERE / 'summary.json').read_bytes())
suite_path = ROOT / summary['suite_file']
if not suite_path.is_file():
    raise SystemExit('Private local suite unavailable; evidence replay was not performed.')
assert hashlib.sha256(suite_path.read_bytes()).hexdigest() == summary['suite_sha256']
_, prepared = load_cases(suite_path)
cases = {c['case_id']: c for c in prepared}
assert len(cases) == summary['planned_cases'] == 7
assert summary['calls_attempted'] == len(summary['cases']) <= 7
assert summary['automatic_retries'] == 0
assert summary['full_real_records_sent'] == 0
assert len({c['case_id'] for c in summary['cases']}) == len(summary['cases'])
counts = Counter()
for record in summary['cases']:
    case = cases[record['case_id']]
    assert case['operation'] == record['operation'] == 'extract'
    assert case['data_class'] == record['data_class'] == 'minimal_anonymous_public_excerpt'
    request_raw = json.dumps(case['request'], ensure_ascii=False, sort_keys=True).encode()
    assert hashlib.sha256(request_raw).hexdigest() == record['request_sha256']
    if 'response_file' not in record:
        assert record['status'] in ('boundary_or_transport_rejected', 'local_error')
        counts['no_saved_response'] += 1
        continue
    response_path = ROOT / record['response_file']
    if not response_path.is_file():
        raise SystemExit('Private response unavailable; evidence replay was not completed.')
    response_raw = response_path.read_bytes()
    assert hashlib.sha256(response_raw).hexdigest() == record['response_sha256']
    response = parse_object(response_raw)
    service = AgentService(lambda operation, value: response)
    try:
        assert service.extract(case['request']) == response
    except AgentError as exc:
        assert record['status'] == 'boundary_or_transport_rejected'
        assert str(exc) == record['error']
        counts['recorded_boundary_rejection_reproduced'] += 1
        continue
    failures, flags = semantic_checks(case, response)
    assert failures == record['failures']
    assert flags == record['review_flags']
    expected = ('automatic_checks_failed' if failures else
                'needs_content_review' if flags else 'automatic_checks_passed')
    assert record['status'] == expected
    counts[expected] += 1
assert set(summary['unattempted_case_ids']) == set(cases) - {c['case_id'] for c in summary['cases']}
print(json.dumps({'offline_minimal_excerpt_recheck': dict(counts), 'new_api_calls': 0,
                  'raw_text_printed': False}))
