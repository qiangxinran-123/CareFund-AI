"""Offline INT-02/06/08 checks against a supplied real B/D checkout.

Run with verify_peers.py --team-root. Generation transport is mocked here;
integration_smoke.py separately performs the two real synthetic calls.
"""
import asyncio
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent.agent_service import AgentError, AgentService
from agent.dify_runner import DifyRunner
from agent.draft_policy import DRAFT_WARNING, sections_for_facts
from agent.errors import AgentContractError, AgentTransportError, AgentWorkflowError
from backend.models import Application, Fact, ValidationIssue
from backend.services.agent import AgentIntegrationError, RealAgentService
from validation import (load_policy, prepare_agent_draft_request, validate_agent_draft,
                        validate_for_confirmation, validate_for_export)
from validation.tests.test_demo_v1 import scenario, formal_draft, actions


def literal(operation, request):
    return {**{k: request[k] for k in ('schema_version', 'application_id', 'application_revision')},
            'candidate_sections': sections_for_facts(request['candidate_facts']), 'warnings': [DRAFT_WARNING]}


class PeerIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy('demo_v1')

    def test_D_generation_confirmation_export_groups_with_current_A(self):
        for mode in ('clean', 'info', 'warning', 'conflict', 'stale', 'invalid_reference'):
            with self.subTest(mode=mode):
                app, snapshot = scenario(mode)
                if mode == 'stale':
                    app['revision'] += 1
                elif mode == 'invalid_reference':
                    snapshot['facts'][0]['evidence_ids'] = ['ev_missing']
                prepared, checked = prepare_agent_draft_request(snapshot, policy=self.policy,
                    application=app, generation_request={'expected_revision': app['revision']})
                # A can also receive all IDs, with the complete D result paired.
                full = copy.deepcopy(prepared)
                full['validation_issue_ids'] = [i['issue_id'] for i in checked['issues']]
                before = copy.deepcopy((full, checked, snapshot))
                runner = Mock(side_effect=literal)
                service = AgentService(runner)
                allowed = mode in ('clean', 'info', 'warning')
                if allowed:
                    candidate = service.draft(full, validation_result=checked)
                    self.assertTrue(validate_agent_draft(snapshot, candidate, policy=self.policy)['can_finalize'])
                    self.assertEqual(checked, service.last_draft_validation_result)
                else:
                    with self.assertRaises(AgentError):
                        service.draft(full, validation_result=checked)
                    runner.assert_not_called()
                draft = formal_draft(app, snapshot)
                confirmation, export = actions(app, draft)
                confirming_app = dict(app, status='draft_ready')
                self.assertEqual(allowed, validate_for_confirmation(snapshot, confirming_app, draft, confirmation, policy=self.policy)['can_finalize'])
                confirmed = dict(draft, status='confirmed', confirmed_at='2026-10-20T00:02:00Z')
                self.assertEqual(allowed, validate_for_export(snapshot, dict(app, status='confirmed'), confirmed, export, policy=self.policy)['can_finalize'])
                self.assertEqual(before, (full, checked, snapshot))

    def test_B_existing_adapter_uses_D_explicit_mapping_without_losing_info(self):
        app, snapshot = scenario('info')
        prepared, checked = prepare_agent_draft_request(snapshot, policy=self.policy,
            application=app, generation_request={'expected_revision': app['revision']})
        original = copy.deepcopy(checked)
        adapter = RealAgentService()
        runner = Mock(side_effect=literal)
        adapter._service = lambda app_id: (AgentService(runner), AgentError)
        ids = set(prepared['validation_issue_ids'])
        gate_issues = [ValidationIssue.model_validate(i) for i in checked['issues'] if i['issue_id'] in ids]
        sections = adapter.draft_sections(Application.model_validate(app),
            [Fact.model_validate(f) for f in snapshot['facts']], gate_issues)
        self.assertTrue(sections)
        self.assertTrue(any(i['severity'] == 'info' for i in checked['issues']))
        self.assertEqual(original, checked)
        self.assertEqual([], runner.call_args.args[1]['validation_issue_ids'])

    def test_B_current_all_ID_forwarding_needs_complete_result_or_D_mapping(self):
        app, snapshot = scenario('info')
        prepared, checked = prepare_agent_draft_request(snapshot, policy=self.policy)
        adapter = RealAgentService()
        runner = Mock(side_effect=literal)
        adapter._service = lambda app_id: (AgentService(runner), AgentError)
        with self.assertRaises(AgentIntegrationError):
            adapter.draft_sections(Application.model_validate(app), [Fact.model_validate(f) for f in snapshot['facts']],
                [ValidationIssue.model_validate(i) for i in checked['issues']])
        runner.assert_not_called()

    def test_B_failure_propagation_uses_real_A_and_fake_transport(self):
        app, _ = scenario()
        runner = DifyRunner(extract_api_key='synthetic-test-key', user=app['application_id'])
        adapter = RealAgentService()
        adapter._service = lambda app_id: (AgentService(runner), AgentError)
        modes = [(TimeoutError('private'), AgentTransportError),
                 (io.BytesIO(b'{"data":{"status":"failed","error":"private"}}'), AgentWorkflowError),
                 (io.BytesIO(b'{"data":{"status":"succeeded","outputs":{"result":"{}"}}}'), AgentContractError)]
        for value, expected in modes:
            with self.subTest(expected=expected.__name__):
                kwargs = {'side_effect': value} if isinstance(value, Exception) else {'return_value': value}
                with patch.object(runner._opener, 'open', **kwargs) as opened:
                    with self.assertRaises(AgentIntegrationError) as caught:
                        adapter.extract(Application.model_validate(app), [], [], [], {})
                self.assertIsInstance(caught.exception.__cause__, expected)
                self.assertNotIn('private', str(caught.exception))
                self.assertEqual(1, opened.call_count)

    def test_unconfirmed_fact_is_not_promoted_by_nonblocking_context(self):
        app, snapshot = scenario('info')
        snapshot['facts'][0]['user_confirmed'] = False
        prepared, checked = prepare_agent_draft_request(snapshot, policy=self.policy,
            application=app, generation_request={'expected_revision': app['revision']})
        runner = Mock(side_effect=literal)
        with self.assertRaises(AgentError):
            AgentService(runner).draft(prepared, validation_result=checked)
        runner.assert_not_called()

    def test_unknown_fact_reference_cannot_confirm_or_export(self):
        app, snapshot = scenario()
        draft = formal_draft(app, snapshot)
        confirmation, export = actions(app, draft)
        draft['sections'][0]['fact_ids'] = ['fact_nonexistent']
        self.assertFalse(validate_for_confirmation(snapshot, dict(app, status='draft_ready'), draft, confirmation, policy=self.policy)['can_finalize'])
        draft.update(status='confirmed', confirmed_at='2026-10-20T00:02:00Z')
        self.assertFalse(validate_for_export(snapshot, dict(app, status='confirmed'), draft, export, policy=self.policy)['can_finalize'])

    def test_separate_services_are_safe_for_B_background_threads(self):
        async def run():
            async def extract(index):
                def call():
                    request = dict(schema_version='1.0', application_id=f'app_thread_{index}', application_revision=index,
                                   user_input={}, extracted_documents=[], candidate_facts=[])
                    response = {**{k: request[k] for k in ('schema_version', 'application_id', 'application_revision')},
                                'candidate_facts': [], 'questions': [], 'warnings': []}
                    service = AgentService(lambda op, req: response)
                    return service.extract(request), service.last_extract_raw_response
                return await asyncio.to_thread(call)
            return await asyncio.gather(*(extract(i) for i in range(1, 5)))
        for index, (result, raw) in enumerate(asyncio.run(run()), 1):
            self.assertEqual(f'app_thread_{index}', result['application_id'])
            self.assertEqual(index, raw['application_revision'])

    def test_smoke_entrypoint_uses_two_backend_operations_with_fake_transport(self):
        from agent import integration_smoke

        def transport(runner, operation, request):
            if operation == 'draft':
                return literal(operation, request)
            response = {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')}
            response.update(candidate_facts=[
                dict(fact_id='fact_smoke_relation', field='patient.relationship_to_applicant',
                    value=dict(kind='text', value='母亲'), source_type='user_input', evidence_ids=[],
                    verification_status='pending', user_confirmed=False),
                dict(fact_id='fact_smoke_cost', field='treatment.estimated_cost',
                    value=dict(kind='money', value=dict(currency='CNY', amount_minor=3000000)),
                    source_type='document', evidence_ids=['ev_demo_001'], verification_status='pending', user_confirmed=False)],
                questions=[], warnings=[])
            return response

        peer_root = Path(__import__('backend').__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'synthetic-dry-run'
            args = ['integration_smoke', '--backend-root', str(peer_root), '--output', str(output)]
            with patch('sys.argv', args), patch.object(integration_smoke, 'credentials', return_value=('https://api.dify.ai/v1', 'first-private', 'second-private')), \
                    patch.object(integration_smoke, 'identify', return_value=({'extract': 'first-private', 'draft': 'second-private'}, [])), \
                    patch.object(DifyRunner, '__call__', transport):
                self.assertEqual(0, integration_smoke.main())
            report = json.loads((output / 'status.json').read_bytes())
            self.assertEqual(2, report['calls_attempted'])
            self.assertEqual('two_real_calls_passed', report['status'])
            self.assertNotIn('private', json.dumps(report))
        # The generated status is a test fixture only; this test mocks transport.

    def test_smoke_entrypoint_stops_after_first_generation_failure(self):
        from agent import integration_smoke
        peer_root = Path(__import__('backend').__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'synthetic-failure'
            args = ['integration_smoke', '--backend-root', str(peer_root), '--output', str(output)]
            with patch('sys.argv', args), patch.object(integration_smoke, 'credentials', return_value=('https://api.dify.ai/v1', 'first-private', 'second-private')), \
                    patch.object(integration_smoke, 'identify', return_value=({'extract': 'first-private', 'draft': 'second-private'}, [])), \
                    patch.object(DifyRunner, '__call__', side_effect=AgentTransportError('Safe synthetic failure')) as called:
                self.assertEqual(1, integration_smoke.main())
            report = json.loads((output / 'status.json').read_bytes())
            self.assertEqual(1, report['calls_attempted'])
            self.assertNotEqual('two_real_calls_passed', report['status'])
            self.assertEqual(1, called.call_count)


if __name__ == '__main__':
    unittest.main()
