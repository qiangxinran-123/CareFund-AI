"""Current A policy regression on immutable saved responses; no inference.

Default: the 27 shareable fictional cases. --private-real additionally checks the
60 private real-source cards on the original workstation, emitting hashes only.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService, AgentError
from agent.batch_check import semantic_checks
from agent.extract_presentation import (VERSION, WARNING_USER, WARNING_DOCUMENT,
    WARNING_NO_EVIDENCE, WARNING_CONFLICT, WARNING_AMBIGUITY)


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(include_private=False):
    previous = ROOT / 'agent/verification/content-review-20261017'
    suite = json.loads((previous / 'synthetic-replay.json').read_bytes())
    decisions = json.loads((previous / 'review-results.json').read_bytes())
    judgments = {x['review_id']: x for x in decisions['judgments']}
    inputs = []
    for entry in suite['cases']:
        assert entry['case']['data_class'] == 'synthetic'
        assert sha(canonical({'case': entry['case'], 'response': entry['response']})) == entry['payload_sha256']
        inputs.append((entry['review_id'], entry['case'], entry['response']))
    if include_private:
        selection = json.loads((previous / 'selection.json').read_bytes())
        raw = (ROOT / 'agent/.local/content-review-20261017/real-cards.json').read_bytes()
        assert sha(raw) == selection['private_review_cards_sha256']['real']
        for item in json.loads(raw):
            assert sha((ROOT / item['record']['response_file']).read_bytes()) == item['record']['response_sha256']
            inputs.append((item['review_id'], dict(item['case'], operation='extract'), item['response']))
    counts, checks = Counter(), []
    constant_warnings = {WARNING_USER, WARNING_DOCUMENT, WARNING_NO_EVIDENCE, WARNING_CONFLICT, WARNING_AMBIGUITY}
    with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden in saved replay')):
        for rid, case, response in inputs:
            before = canonical({'request': case['request'], 'response': response})
            runner = Mock(return_value=response)
            service = AgentService(runner)
            if rid == 'S014':
                try:
                    service.draft(case['request'])
                except AgentError as exc:
                    assert str(exc) == 'Draft fact contains generation instructions; review the source fact before drafting'
                else:
                    raise AssertionError('Instruction-bearing draft was not blocked')
                runner.assert_not_called()
                disposition = 'unsafe_draft_blocked_before_model'
            else:
                result = getattr(service, case['operation'])(case['request'])
                runner.assert_called_once()
                if case['operation'] == 'extract':
                    assert result['candidate_facts'] == response['candidate_facts']
                    assert service.last_extract_raw_response == response
                    assert set(result['warnings']) <= constant_warnings
                    assert all(q['required'] is False for q in result['questions'])
                    assert len(result['questions']) <= 3
                    labels = judgments[rid]['findings']
                    if 'ambiguity_not_prioritized_in_questions' in labels:
                        assert result['questions'][0]['field'] == 'patient.medical_summary'
                    if 'missing_information_without_followup' in labels:
                        assert result['questions']
                    if rid == 'S015':
                        question = result['questions'][0]
                        assert question['field'] == 'treatment.estimated_cost'
                        assert '范围、时间和来源' in question['question'] and '记错' not in question['question']
                    if rid == 'S026':
                        assert not any(q['field'] == 'treatment.paid_cost' for q in result['questions'])
                    if rid.startswith('S'):
                        failures, flags = semantic_checks(case, result)
                        assert not failures and not flags, (rid, failures, flags)
                    disposition = 'facts_unchanged_neutral_presentation_verified'
                else:
                    disposition = 'eligible_literal_draft_unchanged'
            assert canonical({'request': case['request'], 'response': response}) == before
            counts[disposition] += 1
            checks.append(dict(review_id=rid, result=disposition,
                original_response_canonical_sha256=sha(canonical(response)),
                historical_findings=judgments[rid]['findings'],
                finding_disposition='addressed_by_current_A_policy' if judgments[rid]['findings'] else 'regression_retained'))
    expected_extracts = 81 if include_private else 21
    assert counts['facts_unchanged_neutral_presentation_verified'] == expected_extracts
    assert counts['eligible_literal_draft_unchanged'] == 5
    assert counts['unsafe_draft_blocked_before_model'] == 1
    runtime = ['agent_service.py', 'extract_presentation.py', 'draft_input_policy.py', 'draft_policy.py', 'dify_runner.py']
    return dict(checked_at=datetime.now(timezone.utc).isoformat(), mode='offline_saved_response_regression',
        policy=VERSION, new_model_calls=0, real_cases=60 if include_private else 0, fictional_cases=27,
        counts=dict(counts), historical_finding_cases_checked=sum(bool(c['historical_findings']) for c in checks),
        historical_outputs_modified=False, raw_model_defects_claimed_fixed=False,
        live_workflow_or_prompt_changed=False, code_policy_regression_passed=True,
        runtime_sha256={f'agent/{p}': sha((ROOT / 'agent' / p).read_bytes()) for p in runtime},
        limits=['Deterministic presentation coverage and bounded input-instruction guard, not medical accuracy.',
                'Draft lexical guard cannot detect every paraphrase, encoding or instruction.',
                'B/D confirmation, revision transactions, evidence truth and final export remain separate integration responsibilities.'],
        cases=checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-real', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = run(args.private_real)
    if args.report:
        with args.report.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k not in ('cases', 'runtime_sha256')}, ensure_ascii=True))
