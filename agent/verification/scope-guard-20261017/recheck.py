"""Replay saved synthetic model outputs through the current A boundary, offline."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentError, AgentService
from agent.dify_runner import parse_object

summary = parse_object((HERE / 'summary.json').read_bytes())
counts = Counter()
groups = {}
for case in summary['cases']:
    if 'suite_file' in case:
        suite_raw = (ROOT / case['suite_file']).read_bytes()
        assert hashlib.sha256(suite_raw).hexdigest() == case['suite_sha256']
        suite = parse_object(suite_raw)
        fixture = next(c for c in suite['cases'] if c['case_id'] == case['case_id'])
        assert fixture['data_class'] == 'synthetic'
        request = fixture['request']
        request_raw = json.dumps(request, ensure_ascii=False, sort_keys=True).encode()
    else:
        request_raw = (ROOT / case['request_file']).read_bytes()
        request = parse_object(request_raw)
    assert hashlib.sha256(request_raw).hexdigest() == case['request_sha256']
    response_raw = (ROOT / case['response_file']).read_bytes()
    assert hashlib.sha256(response_raw).hexdigest() == case['response_sha256']
    response = parse_object(response_raw)
    service = AgentService(lambda operation, value: response)
    try:
        result = getattr(service, case['operation'])(request)
    except AgentError as exc:
        assert case['expected'] == 'rejected', case['case_id']
        assert str(exc) == case['expected_error']
        outcome = 'rejected_as_expected'
    else:
        assert case['expected'] == 'accepted', case['case_id']
        assert result == response
        outcome = 'accepted'
    counts[outcome] += 1
    groups.setdefault(case['group'], Counter())[outcome] += 1
assert len(summary['cases']) == 46
assert dict(counts) == {'accepted': 45, 'rejected_as_expected': 1}
print(json.dumps({'saved_responses': len(summary['cases']), 'outcomes': dict(counts),
                  'groups': groups, 'new_api_calls': 0}))
