"""A correction creates a new candidate; it cannot silently replace confirmed history."""
import copy
import unittest
from unittest.mock import Mock
from agent.agent_service import AgentError, AgentService


class CorrectionLifecycleTests(unittest.TestCase):
    def test_new_correction_keeps_history_and_conflict_blocks_draft(self):
        old = dict(fact_id='fact_correction_old', field='patient.medical_summary',
                   value={'kind': 'text', 'value': '虚构测试：已确诊测试病甲'},
                   source_type='user_input', evidence_ids=[], verification_status='pending', user_confirmed=True)
        new = dict(fact_id='fact_correction_new', field='patient.medical_summary',
                   value={'kind': 'text', 'value': '虚构更正：可能为测试病乙，尚未确诊'},
                   source_type='user_correction', evidence_ids=[], verification_status='pending', user_confirmed=False)
        request = dict(schema_version='1.0', application_id='app_correction_lifecycle', application_revision=2,
                       user_input={'description': '完全虚构：更正为可能为测试病乙，尚未确诊。'},
                       extracted_documents=[], candidate_facts=[old])
        response = {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')}
        response.update(candidate_facts=[copy.deepcopy(old), new], questions=[], warnings=['两个版本待核对。'])
        service = AgentService(lambda op, req: copy.deepcopy(response))
        extracted = service.extract(request)
        self.assertEqual(extracted['candidate_facts'][0], old)
        self.assertFalse(extracted['candidate_facts'][1]['user_confirmed'])
        self.assertEqual(extracted['candidate_facts'][1]['source_type'], 'user_correction')
        # Even confirming both versions must not authorize a contradictory draft.
        extracted['candidate_facts'][1]['user_confirmed'] = True
        draft = {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')}
        draft.update(candidate_facts=extracted['candidate_facts'], validation_issue_ids=[])
        never_call = Mock(side_effect=AssertionError('Contradictory facts must stop before inference'))
        with self.assertRaisesRegex(AgentError, 'multiple values'):
            AgentService(never_call).draft(draft)
        never_call.assert_not_called()
