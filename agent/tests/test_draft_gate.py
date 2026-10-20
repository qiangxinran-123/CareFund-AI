"""INT-08: paired D results, unchanged contracts, no model calls on rejection."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from agent.agent_service import AgentError, AgentService
from agent.draft_policy import DRAFT_WARNING, sections_for_facts


class DraftGateTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads((Path(__file__).resolve().parents[1] / 'examples/draft-request.json').read_bytes())
        self.validation = {k: self.request[k] for k in ('schema_version', 'application_id', 'application_revision')}
        self.validation.update(validation_id='validation_int08', issues=[], can_finalize=True,
                               evaluated_at='2026-10-20T12:00:00Z')
        self.runner = Mock(side_effect=lambda operation, request: {
            **{k: request[k] for k in ('schema_version', 'application_id', 'application_revision')},
            'candidate_sections': sections_for_facts(request['candidate_facts']), 'warnings': [DRAFT_WARNING]})
        self.service = AgentService(self.runner)

    def issue(self, severity, suffix='one'):
        item = dict(issue_id='issue_' + suffix, type='unsupported', severity=severity,
            field=self.request['candidate_facts'][0]['field'], message='合成来源提示，仍需核对。',
            related_fact_ids=[self.request['candidate_facts'][0]['fact_id']])
        self.validation['issues'].append(item)
        self.request['validation_issue_ids'].append(item['issue_id'])
        return item

    def reject(self):
        with self.assertRaises(AgentError):
            self.service.draft(self.request, validation_result=self.validation)
        self.runner.assert_not_called()

    def test_no_issues_with_checked_context(self):
        self.assertTrue(self.service.draft(self.request, validation_result=self.validation)['candidate_sections'])

    def test_info_and_nonblocking_warning_preserve_full_context(self):
        self.issue('info')
        self.issue('warning', 'two')
        before = copy.deepcopy((self.request, self.validation))
        self.service.draft(self.request, validation_result=self.validation)
        sent = self.runner.call_args.args[1]
        self.assertEqual(sent['validation_issue_ids'], [])
        self.assertEqual(sent['candidate_facts'], self.request['candidate_facts'])
        self.assertNotIn('validation_result', sent)
        self.assertEqual((self.request, self.validation), before)
        self.assertEqual(self.service.last_draft_validation_result, self.validation)
        self.assertEqual(self.service.last_draft_gate_report['complete_issues_count'], 2)
        self.assertNotIn('message', json.dumps(self.service.last_draft_gate_report))

    def test_d_blocking_only_projection_is_accepted_with_full_result(self):
        self.issue('info')
        self.request['validation_issue_ids'] = []
        self.service.draft(self.request, validation_result=self.validation)
        self.assertEqual(self.service.last_draft_gate_report['input_issue_scope'], 'blocking')
        self.assertEqual(len(self.service.last_draft_validation_result['issues']), 1)

    def test_legacy_nonempty_ids_do_not_infer_severity(self):
        self.issue('info')
        with self.assertRaisesRegex(AgentError, 'complete current ValidationResult'):
            self.service.draft(self.request)
        self.runner.assert_not_called()

    def test_blocking_rejected_even_if_can_finalize_is_forged_true(self):
        self.issue('blocking')
        self.reject()

    def test_removing_blocking_id_cannot_bypass_complete_result(self):
        self.issue('blocking')
        self.request['validation_issue_ids'] = []
        self.reject()

    def test_can_finalize_false_is_not_overridden_for_info(self):
        self.issue('info')
        self.validation['can_finalize'] = False
        self.reject()

    def test_unknown_or_partial_issue_ids_are_rejected(self):
        self.issue('info')
        self.issue('warning', 'two')
        for supplied in [['issue_unknown'], ['issue_one']]:
            with self.subTest(supplied=supplied):
                self.request['validation_issue_ids'] = supplied
                self.reject()

    def test_different_application_revision_or_schema_rejected(self):
        for field, value in [('application_id', 'app_other'), ('application_revision', 99), ('schema_version', '2.0')]:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.validation)
                changed[field] = value
                with self.assertRaises(AgentError):
                    self.service.draft(self.request, validation_result=changed)
        self.runner.assert_not_called()

    def test_duplicate_or_unknown_fact_issue_reference_rejected(self):
        item = self.issue('info')
        original = copy.deepcopy(self.validation)
        self.validation['issues'].append(copy.deepcopy(item))
        self.reject()
        self.validation = original
        self.validation['issues'][0]['related_fact_ids'] = ['fact_unknown']
        self.reject()

    def test_unknown_severity_and_extra_json_fields_rejected(self):
        self.issue('info')['severity'] = 'safe'
        self.reject()
        self.validation['issues'][0]['severity'] = 'info'
        self.request['validation_result'] = copy.deepcopy(self.validation)
        self.reject()

    def test_context_does_not_override_fact_confirmation_or_conflict(self):
        self.issue('info')
        for change in [dict(user_confirmed=False), dict(verification_status='conflicting'), dict(verification_status='unsupported')]:
            with self.subTest(change=change):
                request = copy.deepcopy(self.request)
                request['candidate_facts'][0].update(change)
                with self.assertRaises(AgentError):
                    self.service.draft(request, validation_result=self.validation)
        self.runner.assert_not_called()

    def test_raw_model_output_still_requires_literal_content(self):
        self.issue('info')
        self.runner.side_effect = None
        self.runner.return_value = {**{k: self.request[k] for k in ('schema_version', 'application_id', 'application_revision')},
            'candidate_sections': [{'title': '合成', 'content': '凭空追加的病情。',
                                    'fact_ids': [self.request['candidate_facts'][0]['fact_id']]}], 'warnings': [DRAFT_WARNING]}
        with self.assertRaisesRegex(AgentError, 'literal draft format'):
            self.service.draft(self.request, validation_result=self.validation)

    def test_gate_audit_is_cleared_after_failure_and_legacy_call(self):
        self.issue('info')
        self.service.draft(self.request, validation_result=self.validation)
        self.validation['application_revision'] += 1
        with self.assertRaises(AgentError):
            self.service.draft(self.request, validation_result=self.validation)
        self.assertIsNone(self.service.last_draft_validation_result)
        self.assertIsNone(self.service.last_draft_gate_report)
        self.request['validation_issue_ids'] = []
        self.service.draft(self.request)
        self.assertIsNone(self.service.last_draft_validation_result)


if __name__ == '__main__':
    unittest.main()
