"""Recheck saved synthetic batch evidence offline, preserving any recorded findings."""
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
from review_checks import prompt_scope_findings

summary = parse_object((HERE / 'summary.json').read_bytes())
suite_path = ROOT / summary['suite_file']
assert hashlib.sha256(suite_path.read_bytes()).hexdigest() == summary['suite_sha256']
_, suite_cases = load_cases(suite_path)
cases = {c['case_id']: c for c in suite_cases}
assert summary['calls_attempted'] == len(summary['cases'])
assert summary['calls_attempted'] <= summary['planned_cases'] == 30
assert summary['automatic_retries'] == 0
assert summary['real_medical_records_sent'] == 0
assert len({c['case_id'] for c in summary['cases']}) == len(summary['cases'])
rechecked = Counter()
runtime_checks = Counter()
content_findings = {}
for record in summary['cases']:
    case = cases[record['case_id']]
    assert case['data_class'] == record['data_class'] == 'synthetic'
    request_raw = json.dumps(case['request'], ensure_ascii=False, sort_keys=True).encode()
    assert hashlib.sha256(request_raw).hexdigest() == record['request_sha256']
    if 'response_file' not in record:
        rechecked['without_saved_response'] += 1
        continue
    response_raw = (HERE / record['response_file']).read_bytes()
    assert hashlib.sha256(response_raw).hexdigest() == record['response_sha256']
    response = parse_object(response_raw)
    findings = prompt_scope_findings(case, response)
    if findings:
        content_findings[case['case_id']] = findings
    service = AgentService(lambda operation, request: response)
    try:
        assert getattr(service, case['operation'])(case['request']) == response
    except AgentError as exc:
        if record['status'] == 'boundary_or_transport_rejected':
            rechecked['recorded_boundary_rejection_reproduced'] += 1
            continue
        # The immutable original report predates the 2026-10-17 runtime guard.
        # Only the independently recorded field-scope finding may now reject.
        assert findings
        expected_error = ('New candidate field is outside the extraction scope'
                          if any(f['type'] == 'new_fact_field_outside_tested_prompt_scope'
                                 for f in findings) else
                          'Question field is outside the extraction scope')
        assert str(exc) == expected_error
        runtime_checks['recorded_scope_finding_rejected'] += 1
    else:
        assert not findings, 'Current runtime failed to enforce the recorded prompt scope'
        runtime_checks['accepted'] += 1
    failures, flags = semantic_checks(case, response)
    assert failures == record['failures']
    assert flags == record['review_flags']
    expected_status = ('automatic_checks_failed' if failures else
                       'needs_content_review' if flags else 'automatic_checks_passed')
    assert record['status'] == expected_status
    rechecked[expected_status] += 1
assert set(summary['unattempted_case_ids']) == set(cases) - {c['case_id'] for c in summary['cases']}
assert content_findings == summary['post_run_prompt_scope_findings']
print(json.dumps({'offline_evidence_recheck': dict(rechecked),
                  'current_runtime_checks': dict(runtime_checks),
                  'cases_with_prompt_scope_findings': len(content_findings),
                  'new_api_calls': 0}))
