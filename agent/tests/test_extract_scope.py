"""Extraction scope regressions, including the saved DeepSeek field escape."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from agent.agent_service import AgentError, AgentService


class ExtractionScopeTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(schema_version='1.0', application_id='app_scope_test',
                            application_revision=1, user_input={},
                            extracted_documents=[], candidate_facts=[])
        self.response = {k: self.request[k] for k in
                         ('schema_version', 'application_id', 'application_revision')}
        self.response.update(candidate_facts=[], questions=[], warnings=[])

    def fact(self, field='patient.medical_summary', fact_id='fact_scope', **changes):
        return dict(fact_id=fact_id, field=field,
                    value={'kind': 'text', 'value': '测试陈述'},
                    source_type='user_input', evidence_ids=[],
                    verification_status='pending', user_confirmed=False) | changes

    def service(self):
        return AgentService(lambda operation, request: copy.deepcopy(self.response))

    def test_saved_deepseek_fundraising_fields_are_rejected(self):
        agent = Path(__file__).resolve().parents[1]
        suite = json.loads((agent / 'verification/batch/synthetic-cases.json').read_bytes())
        case = next(c for c in suite['cases'] if c['case_id'] == 'extract_0042')
        response = json.loads((agent / 'verification/deepseek-batch-20261016/'
                               'extract_0042.response.json').read_bytes())
        with self.assertRaisesRegex(AgentError, 'New candidate field is outside the extraction scope'):
            AgentService(lambda operation, request: response).extract(case['request'])

    def test_mixed_response_is_rejected_whole_without_retry_or_mutation(self):
        self.response['candidate_facts'] = [self.fact(), self.fact('fundraising.target_amount', 'fact_other')]
        before = copy.deepcopy((self.request, self.response))
        runner = Mock(return_value=self.response)
        with self.assertRaisesRegex(AgentError, 'outside the extraction scope'):
            AgentService(runner).extract(self.request)
        runner.assert_called_once()
        self.assertEqual((self.request, self.response), before)

    def test_existing_out_of_scope_fact_is_preserved_with_new_allowed_fact(self):
        existing = self.fact('legacy.family_income', 'fact_legacy', user_confirmed=True)
        self.request['candidate_facts'] = [existing]
        self.response['candidate_facts'] = [copy.deepcopy(existing), self.fact()]
        before = copy.deepcopy(self.request)
        self.assertEqual(self.service().extract(self.request)['candidate_facts'], self.response['candidate_facts'])
        self.assertEqual(self.request, before)

    def test_new_id_cannot_reuse_out_of_scope_existing_field(self):
        existing = self.fact('legacy.family_income', 'fact_legacy')
        self.request['candidate_facts'] = [existing]
        self.response['candidate_facts'] = [copy.deepcopy(existing),
                                            self.fact('legacy.family_income', 'fact_new')]
        with self.assertRaisesRegex(AgentError, 'New candidate field is outside the extraction scope'):
            self.service().extract(self.request)

    def test_existing_out_of_scope_fact_still_cannot_be_changed(self):
        self.request['candidate_facts'] = [self.fact('legacy.family_income')]
        self.response['candidate_facts'] = [self.fact('legacy.family_income', user_confirmed=True)]
        with self.assertRaisesRegex(AgentError, 'Existing fact changed'):
            self.service().extract(self.request)

    def test_out_of_scope_question_is_rejected(self):
        self.response['questions'] = [dict(question_id='question_scope', field='fundraising.target_amount',
                                          question='测试追问', reason='测试理由', required=False)]
        with self.assertRaisesRegex(AgentError, 'Question field is outside the extraction scope'):
            self.service().extract(self.request)

    def test_diagnosis_document_field_is_question_only(self):
        self.response['questions'] = [dict(question_id='question_scope', field='documents.diagnosis_proof',
                                          question='是否有检查材料？', reason='便于核对已有陈述', required=False)]
        # Raw question fields are validated before deterministic presentation.
        self.assertEqual(self.service().extract(self.request)['candidate_facts'], [])
        self.response['candidate_facts'] = [self.fact('documents.diagnosis_proof')]
        with self.assertRaisesRegex(AgentError, 'New candidate field is outside the extraction scope'):
            self.service().extract(self.request)

    def test_current_prompt_fact_and_question_fields_remain_accepted(self):
        fields = ('patient.relationship_to_applicant', 'patient.medical_summary',
                  'treatment.paid_cost', 'treatment.estimated_cost',
                  'treatment.recorded_date', 'contact.city')
        for field in fields:
            with self.subTest(field=field):
                self.response['candidate_facts'] = [self.fact(field)]
                self.response['questions'] = [dict(question_id='question_scope', field=field,
                                                  question='测试追问', reason='测试理由', required=False)]
                self.assertEqual(self.service().extract(self.request)['candidate_facts'], self.response['candidate_facts'])

    def test_scope_error_does_not_echo_model_field_or_patient_content(self):
        self.response['candidate_facts'] = [self.fact('private.patient_identifier',
                                                    value={'kind': 'text', 'value': 'private patient content'})]
        with self.assertRaises(AgentError) as caught:
            self.service().extract(self.request)
        self.assertEqual(str(caught.exception), 'New candidate field is outside the extraction scope')


if __name__ == '__main__':
    unittest.main()
