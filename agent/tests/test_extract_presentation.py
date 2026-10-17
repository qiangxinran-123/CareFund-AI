import copy
import json
import unittest
from unittest.mock import Mock
from agent.agent_service import AgentService, AgentError
from agent.extract_presentation import VERSION


class PresentationTests(unittest.TestCase):
    def setUp(self):
        self.req = dict(schema_version='1.0', application_id='app_presentation_test', application_revision=1,
                        user_input={'description': '完全虚构：测试病甲'}, extracted_documents=[], candidate_facts=[])
        self.out = {k: self.req[k] for k in ('schema_version', 'application_id', 'application_revision')}
        self.out.update(candidate_facts=[self.fact()], questions=[], warnings=[])

    def fact(self, field='patient.medical_summary', value='虚构：测试病甲', identifier='fact_presentation'):
        return dict(fact_id=identifier, field=field, value={'kind': 'text', 'value': value},
                    source_type='user_input', evidence_ids=[], verification_status='pending', user_confirmed=False)

    def extract(self):
        self.runner = Mock(return_value=self.out)
        self.service = AgentService(self.runner)
        return self.service.extract(self.req)

    def test_model_typo_alternative_never_enters_public_prose(self):
        self.out['warnings'] = ['虚构错别字可能为另一种模型猜测名称的笔误。']
        result = self.extract()
        self.assertNotIn('另一种模型猜测名称', json.dumps(result, ensure_ascii=False))
        self.assertEqual(result['candidate_facts'], self.out['candidate_facts'])
        self.assertEqual(result['questions'][0]['field'], 'patient.medical_summary')
        self.assertEqual(self.service.last_extract_raw_response, self.out)
        self.assertIsNot(self.service.last_extract_raw_response, self.out)
        self.runner.assert_called_once()

    def test_unprovided_relation_and_platform_claim_replaced_by_neutral_notice(self):
        self.out['warnings'] = ['测试病甲与测试情况乙可能相关；平台常用人民币；补材料加快审核。']
        result = self.extract()
        prose = json.dumps([result['warnings'], result['questions']], ensure_ascii=False)
        for text in ('测试病甲与测试情况乙', '平台常用人民币', '加快审核'):
            self.assertNotIn(text, prose)

    def test_original_explicit_relation_is_not_rewritten_in_fact(self):
        self.out['candidate_facts'][0]['value']['value'] = '虚构：原文说测试情况甲引起测试情况乙'
        self.assertEqual(self.extract()['candidate_facts'], self.out['candidate_facts'])

    def test_missing_information_gets_optional_questions(self):
        result = self.extract()
        self.assertGreaterEqual(len(result['questions']), 1)
        self.assertLessEqual(len(result['questions']), 3)
        self.assertTrue(all(q['required'] is False for q in result['questions']))

    def test_uncertainty_precedes_generic_questions(self):
        self.req['user_input']['description'] = '完全虚构：测试病甲待排，测试情况乙？'
        result = self.extract()
        self.assertEqual(result['questions'][0]['field'], 'patient.medical_summary')
        self.assertIn('不需要猜测诊断', result['questions'][0]['question'])

    def test_conflict_is_neutral_and_keeps_both_values(self):
        self.out['candidate_facts'] = [self.fact('treatment.estimated_cost', '虚构原文一', 'fact_one'),
                                       self.fact('treatment.estimated_cost', '虚构原文二', 'fact_two')]
        self.out['questions'] = [dict(question_id='question_old', field='treatment.estimated_cost',
                                      question='是你记错还是材料更新？', reason='旧措辞', required=False)]
        result = self.extract()
        self.assertEqual(result['candidate_facts'], self.out['candidate_facts'])
        question = result['questions'][0]
        self.assertEqual(question['field'], 'treatment.estimated_cost')
        self.assertIn('范围、时间和来源', question['question'])
        self.assertNotIn('记错', question['question'])

    def test_clear_usd_not_questioned_again(self):
        self.out['candidate_facts'] = [self.fact('treatment.paid_cost', 'USD 389.17（美元）')]
        self.req['user_input']['description'] = '完全虚构：已支付医疗费USD 389.17，明确为美元。'
        self.assertNotIn('treatment.paid_cost', [q['field'] for q in self.extract()['questions']])

    def test_ambiguous_currency_is_prioritized(self):
        self.out['candidate_facts'] = [self.fact('treatment.paid_cost', '$7200（币种未说明）')]
        self.assertEqual(self.extract()['questions'][0]['field'], 'treatment.paid_cost')

    def test_explicit_unknown_estimate_and_missing_document_not_reasked(self):
        self.req['user_input']['description'] = '完全虚构：后续费用不知道，暂时没有医院费用预估单。'
        self.assertNotIn('treatment.estimated_cost', [q['field'] for q in self.extract()['questions']])

    def test_explicit_null_is_not_missing(self):
        self.req['user_input']['treatment.paid_cost'] = None
        self.assertNotIn('treatment.paid_cost', [q['field'] for q in self.extract()['questions']])

    def test_user_can_decline_further_questions(self):
        self.req['user_input']['description'] += '。我不愿补充，不要追问。'
        self.assertEqual(self.extract()['questions'], [])

    def test_empty_no_context_stays_empty(self):
        self.req['user_input'] = {}
        self.out['candidate_facts'] = []
        self.assertEqual(self.extract(), self.out)

    def test_raw_invalid_response_is_not_repaired_by_presentation(self):
        self.out['questions'] = [dict(question_id='question_bad', field='patient.medical_summary', question='虚构', reason='虚构')]
        with self.assertRaisesRegex(AgentError, 'missing required'):
            self.extract()
        self.assertIsNone(self.service.last_extract_presentation_report)
        self.assertIsNone(self.service.last_extract_raw_response)

    def test_audit_state_cleared_after_later_failure(self):
        self.extract()
        self.service.runner = Mock(side_effect=TimeoutError())
        with self.assertRaises(AgentError):
            self.service.extract(self.req)
        self.assertIsNone(self.service.last_extract_raw_response)
        self.assertIsNone(self.service.last_extract_presentation_report)

    def test_ids_are_stable_and_provenance_has_no_body(self):
        first = self.extract()
        second = self.service.extract(self.req)
        self.assertEqual(first, second)
        report = self.service.last_extract_presentation_report
        self.assertEqual(report['version'], VERSION)
        self.assertTrue(report['candidate_facts_unchanged'])
        self.assertNotIn('测试病甲', json.dumps(report, ensure_ascii=False))

    def test_input_and_runner_output_are_unchanged(self):
        before = copy.deepcopy((self.req, self.out))
        self.extract()
        self.assertEqual((self.req, self.out), before)
