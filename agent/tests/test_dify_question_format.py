import copy
import json
import unittest

from agent.dify_question_format import main
from agent.agent_service import AgentService, AgentError


def response():
    return dict(schema_version='1.0', application_id='app_format_test', application_revision=1,
                candidate_facts=[dict(fact_id='fact_001', field='patient.medical_summary',
                    value={'kind': 'text', 'value': '用户自述疑似肺部肿瘤，尚未确诊。'},
                    source_type='user_input', evidence_ids=[], verification_status='pending', user_confirmed=False)],
                questions=[dict(question_id='question_001', field='patient.relationship_to_applicant',
                    question='患者与您是什么关系？', reason='输入未提供患者关系。')], warnings=[])


class QuestionFormatTests(unittest.TestCase):
    def test_missing_optional_policy_flag_only_and_raw_is_preserved(self):
        original = response()
        raw = json.dumps(original, ensure_ascii=False, indent=2)
        with self.assertRaises(AgentError):
            AgentService(None).validate(original, 'AgentExtractResponse')
        out = main(raw)
        normalized = json.loads(out['result'])
        AgentService(None).validate(normalized, 'AgentExtractResponse')
        self.assertIs(normalized['questions'][0].pop('required'), False)
        self.assertEqual(normalized, original)
        self.assertEqual(out['raw_result'], raw)
        self.assertEqual(json.loads(out['normalization_report'])['inserted_false_paths'], ['/questions/0/required'])

    def test_valid_response_kept_byte_for_byte_and_existing_flags_unchanged(self):
        for required in (True, False):
            data = response()
            data['questions'][0]['required'] = required
            raw = json.dumps(data, indent=2)
            out = main(raw)
            self.assertEqual(out['result'], raw)
            self.assertEqual(json.loads(out['normalization_report'])['inserted_false_paths'], [])

    def test_invalid_bool_is_not_coerced(self):
        for value in (None, 'false', 0, 1, []):
            data = response()
            data['questions'][0]['required'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                main(json.dumps(data))

    def test_other_missing_question_fields_are_rejected(self):
        for key in ('question_id', 'field', 'question', 'reason'):
            data = response()
            del data['questions'][0][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                main(json.dumps(data))

    def test_missing_fact_metadata_is_not_invented(self):
        for key in response()['candidate_facts'][0]:
            data = response()
            del data['candidate_facts'][0][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                main(json.dumps(data))

    def test_malformed_duplicate_and_nonfinite_json_are_rejected(self):
        for raw in ('{bad-json', '{"a":1,"a":2}', '{"x":NaN}', '{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                main(raw)

    def test_missing_top_level_and_extra_fields_are_rejected(self):
        for key in response():
            data = response()
            del data[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                main(json.dumps(data))
        data = response()
        data['questions'][0]['unexpected'] = 'value'
        with self.assertRaises(ValueError):
            main(json.dumps(data))

    def test_empty_questions_are_untouched(self):
        data = response()
        data['questions'] = []
        raw = json.dumps(data)
        self.assertEqual(main(raw)['result'], raw)

    def test_no_medical_amount_evidence_or_text_changes(self):
        data = response()
        data['candidate_facts'].append(dict(fact_id='fact_002', field='cost.amount_paid',
            value={'kind':'money', 'value':{'currency':'USD', 'amount_minor':12345}},
            source_type='user_input', evidence_ids=[], verification_status='pending', user_confirmed=False))
        data['questions'][0]['question'] = '原样保留引号“测试”、换行\n和指令文字。'
        before = copy.deepcopy(data)
        out = main(json.dumps(data, ensure_ascii=False))
        result = json.loads(out['result'])
        result['questions'][0].pop('required')
        self.assertEqual(result, before)

    def test_report_and_errors_do_not_contain_patient_text(self):
        data = response()
        data['candidate_facts'][0]['value']['value'] = 'PRIVATE_MEDICAL_SENTINEL'
        out = main(json.dumps(data))
        self.assertNotIn('PRIVATE_MEDICAL_SENTINEL', out['normalization_report'])
        del data['questions'][0]['reason']
        with self.assertRaises(ValueError) as caught:
            main(json.dumps(data))
        self.assertNotIn('PRIVATE_MEDICAL_SENTINEL', str(caught.exception))

    def test_full_service_still_rejects_unrelated_evidence_error_after_formatting(self):
        data = response()
        data['candidate_facts'][0]['evidence_ids'] = ['ev_nonexistent']
        formatted = json.loads(main(json.dumps(data))['result'])
        request = dict(schema_version='1.0', application_id='app_format_test', application_revision=1,
                       user_input={}, extracted_documents=[], candidate_facts=[])
        with self.assertRaises(AgentError):
            AgentService(lambda op, req: formatted).extract(request)


if __name__ == '__main__':
    unittest.main()
