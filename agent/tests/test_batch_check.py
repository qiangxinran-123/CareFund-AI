"""Checks of batch evaluation itself; never counted as real Dify calls."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.agent_service import AgentError, AgentService
from agent import batch_check
from agent.mdcc_prepare import CLAUSE, CONTEXT_RISK, synthetic_cases, request


class BatchChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.cases = synthetic_cases(1)

    def response(self, case, facts=None, questions=None):
        result = {k: case['request'][k] for k in ('schema_version', 'application_id', 'application_revision')}
        result.update(candidate_facts=facts or [], questions=questions or [], warnings=[])
        return result

    def write_suite(self, cases):
        path = self.folder / 'suite.json'
        path.write_text(json.dumps({'cases': cases}, ensure_ascii=False), encoding='utf-8')
        return path

    def test_generated_cases_preflight_without_parent_handoff_directory(self):
        _, cases = batch_check.load_cases(self.write_suite(self.cases))
        self.assertEqual(len(cases), 30)
        self.assertEqual(sum(c['operation']=='draft' for c in cases), 10)

    def test_raw_narrative_class_cannot_be_sent(self):
        case = copy.deepcopy(self.cases[0])
        case['data_class'] = 'real_public_sensitive_local_only'
        with self.assertRaisesRegex(AgentError, 'Raw or unreviewed'):
            batch_check.load_cases(self.write_suite([case]))

    def test_anonymous_clause_cannot_smuggle_name_into_model_request(self):
        case = copy.deepcopy(self.cases[0])
        case['data_class'] = 'minimal_anonymous_public_excerpt'
        case['request']['user_input']['description'] = batch_check.EXCERPT_PREFIX + 'Alice was diagnosed with cancer' + batch_check.EXCERPT_SUFFIX
        with self.assertRaisesRegex(AgentError, 'outside the allowed dictionary'):
            batch_check.load_cases(self.write_suite([case]))

    def test_anonymous_clause_cannot_smuggle_metadata(self):
        case = copy.deepcopy(self.cases[0])
        case['data_class'] = 'minimal_anonymous_public_excerpt'
        case['request']['user_input'] = {'description': batch_check.EXCERPT_PREFIX + 'My mother was diagnosed with breast cancer' + batch_check.EXCERPT_SUFFIX,
                                        'name': 'private-name'}
        with self.assertRaisesRegex(AgentError, 'envelope'):
            batch_check.load_cases(self.write_suite([case]))

    def test_context_negation_is_not_cut_away(self):
        self.assertTrue(CLAUSE.search('My mother was diagnosed with breast cancer'))
        self.assertTrue(CONTEXT_RISK.search('My mother was diagnosed with breast cancer but this was later ruled out'))
        self.assertTrue(CONTEXT_RISK.search('If I was diagnosed with cancer'))
        self.assertFalse(CLAUSE.fullmatch('My mother Alice was diagnosed with breast cancer'))

    def test_money_oracle_catches_role_swap(self):
        case = self.cases[0]
        expected = case['expectation']['money_exact']
        def fact(field, value, index):
            return {'fact_id': 'fact_' + str(index), 'field': field, 'value': {'kind': 'money', 'value': value},
                    'source_type': 'user_input', 'evidence_ids': [], 'verification_status': 'pending', 'user_confirmed': False}
        fields = list(expected)
        facts = [fact(fields[0], expected[fields[1]][0], 1), fact(fields[1], expected[fields[0]][0], 2)]
        failures, _ = batch_check.semantic_checks(case, self.response(case, facts))
        self.assertEqual(len(failures), 2)

    def test_goal_must_not_be_accepted_as_paid_cost(self):
        case = self.cases[1]
        result = self.response(case, [{'field': 'treatment.paid_cost', 'value': {'kind': 'money', 'value': {'currency': 'CNY', 'amount_minor': 2000000}}}])
        failures, _ = batch_check.semantic_checks(case, result)
        self.assertIn('invented_or_misattributed_medical_money', failures)
        ambiguous = self.cases[3]
        text_result = self.response(ambiguous, [{'field': 'treatment.paid_cost', 'value': {'kind': 'text', 'value': '$5000，币种未知'}}])
        failures, _ = batch_check.semantic_checks(ambiguous, text_result)
        self.assertNotIn('numeric_medical_cost_text_without_input_cost', failures)

    def test_transport_error_stops_after_one_attempt(self):
        calls = []
        def runner(operation, req):
            calls.append(req)
            raise AgentError('Dify HTTP error: 429')
        report = {'status': 'preflight', 'cases': []}
        destination = self.folder / 'status.json'
        self.assertEqual(batch_check.run_cases(self.cases[:2], runner, report, destination), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(report['status'], 'stopped_on_error_no_retry')

    def test_unsupported_approval_effect_is_flagged_for_review(self):
        case = self.cases[1]
        result = self.response(case)
        result['warnings'] = ['补充材料有助于加快审核进度。']
        failures, flags = batch_check.semantic_checks(case, result)
        self.assertEqual(failures, [])
        self.assertIn('approval_effect_claim_needs_context_review', flags)

    def test_existing_report_is_preserved_without_prompt_or_api_call(self):
        destination = self.folder / 'status.json'
        original = b'{"status":"stopped_on_error_no_retry","cases":[{"case_id":"extract_0023"}]}'
        destination.write_bytes(original)
        with patch('sys.argv', ['batch_check', '--report', str(destination)]), \
                patch.object(batch_check, 'credentials') as prompt, \
                patch.object(batch_check, 'DifyRunner') as runner:
            with self.assertRaises(SystemExit) as ctx:
                batch_check.main()
            self.assertEqual(ctx.exception.code, 2)
            prompt.assert_not_called()
            runner.assert_not_called()
        self.assertEqual(destination.read_bytes(), original)

    def test_semantic_failure_is_saved_and_does_not_become_success(self):
        case = self.cases[0]
        response = self.response(case)
        report = {'status': 'preflight', 'cases': []}
        self.assertEqual(batch_check.run_cases([case], lambda op, req: response, report, self.folder/'status.json'), 1)
        self.assertEqual(report['status'], 'completed_with_findings')
        self.assertEqual(report['cases'][0]['status'], 'automatic_checks_failed')

    def test_cancel_does_not_create_runner_or_call_api(self):
        suite = self.write_suite([self.cases[0]])
        with patch.object(batch_check, 'REPORT', self.folder/'status.json'), \
                patch('sys.argv', ['batch_check', '--suite', str(suite)]), \
                patch.object(batch_check, 'credentials', return_value=(None, {})), \
                patch.object(batch_check, 'DifyRunner') as runner:
            self.assertEqual(batch_check.main(), 1)
            runner.assert_not_called()
        report = json.loads((self.folder/'status.json').read_bytes())
        self.assertEqual(report['status'], 'cancelled_before_api_call')


if __name__ == '__main__':
    unittest.main()
