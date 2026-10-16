"""Offline launcher checks; none of these invoke the real Dify service."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent import draft_live_check, live_check, run_draft
from agent.agent_service import AgentError, AgentService
from agent.draft_policy import DRAFT_WARNING, sections_for_facts


class DraftEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.report = Path(self.temporary.name) / 'draft-live-status.json'
        report_patch = patch.object(draft_live_check, 'REPORT', self.report)
        report_patch.start()
        self.addCleanup(report_patch.stop)

    def test_live_cancel_has_no_api_call(self):
        with patch('sys.argv', ['draft_live_check', '--gui']), \
                patch.object(draft_live_check, 'credentials', return_value=(None, None)) as credentials, \
                patch.object(draft_live_check, 'DifyRunner') as runner:
            self.assertEqual(draft_live_check.main(), 1)
            credentials.assert_called_once_with(True, operation='draft', case_count=3)
            runner.assert_not_called()
        self.assertEqual(json.loads(self.report.read_text(encoding='utf-8'))['status'], 'cancelled_before_api_call')

    def test_live_error_stops_and_redacts_key(self):
        with patch('sys.argv', ['draft_live_check']), \
                patch.object(draft_live_check, 'credentials', return_value=('https://api.dify.ai/v1', 'draft-test-secret')), \
                patch.object(draft_live_check, 'DifyRunner') as runner:
            runner.return_value.side_effect = AgentError('Dify HTTP error: 401')
            self.assertEqual(draft_live_check.main(), 1)
            self.assertEqual(runner.return_value.call_count, 1)
        text = self.report.read_text(encoding='utf-8')
        self.assertNotIn('draft-test-secret', text)
        self.assertEqual(json.loads(text)['status'], 'stopped_on_failure_no_retry')

    def test_live_mocked_three_cases_reach_content_guard(self):
        def response(operation, request):
            self.assertEqual(operation, 'draft')
            return {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')} | {
                'candidate_sections': sections_for_facts(request['candidate_facts']), 'warnings': [DRAFT_WARNING]}
        with patch('sys.argv', ['draft_live_check']), \
                patch.object(draft_live_check, 'credentials', return_value=('https://api.dify.ai/v1', 'draft-test-secret')), \
                patch.object(draft_live_check, 'DifyRunner') as runner:
            runner.return_value.side_effect = response
            self.assertEqual(draft_live_check.main(), 0)
            self.assertEqual(runner.return_value.call_count, 3)
        report = json.loads(self.report.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'three_synthetic_draft_calls_passed')
        for record in report['cases']:
            self.assertEqual(record['status'], 'schema_references_and_literal_content_passed')

    def test_live_mocked_hallucination_does_not_write_response(self):
        def response(operation, request):
            sections = sections_for_facts(request['candidate_facts'])
            sections[0]['content'] += '已通过平台审核'
            return {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')} | {
                'candidate_sections': sections, 'warnings': [DRAFT_WARNING]}
        with patch('sys.argv', ['draft_live_check']), \
                patch.object(draft_live_check, 'credentials', return_value=('https://api.dify.ai/v1', 'draft-test-secret')), \
                patch.object(draft_live_check, 'DifyRunner') as runner:
            runner.return_value.side_effect = response
            self.assertEqual(draft_live_check.main(), 1)
            self.assertEqual(runner.return_value.call_count, 1)
        self.assertFalse(list(Path(self.temporary.name).rglob('*.response.json')))

    def test_cli_invalid_input_never_prompts_or_calls_api(self):
        request = json.loads((draft_live_check.ROOT / 'examples' / 'draft-request.json').read_text(encoding='utf-8'))
        request['candidate_facts'][0]['user_confirmed'] = False
        path = Path(self.temporary.name) / 'unconfirmed.json'
        path.write_text(json.dumps(request), encoding='utf-8')
        with patch('sys.argv', ['run_draft', str(path), '--user', 'opaque_test']), \
                patch.object(run_draft.getpass, 'getpass') as prompt, \
                patch.object(run_draft, 'DifyRunner') as runner, patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as exc:
                run_draft.main()
            self.assertEqual(exc.exception.code, 1)
            prompt.assert_not_called()
            runner.assert_not_called()

    def test_env_draft_credentials_do_not_reuse_extract_key(self):
        with patch.dict(os.environ, {'DIFY_DRAFT_API_KEY': 'same-key', 'DIFY_EXTRACT_API_KEY': 'same-key'}):
            with self.assertRaisesRegex(AgentError, 'separate'):
                live_check.credentials(False, operation='draft')

    def test_warning_cannot_claim_platform_approval(self):
        request = json.loads((draft_live_check.ROOT / 'examples' / 'draft-request.json').read_text(encoding='utf-8'))
        result = {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')} | {
            'candidate_sections': sections_for_facts(request['candidate_facts']), 'warnings': ['平台已审核通过']}
        with self.assertRaisesRegex(AgentError, 'policy notice'):
            AgentService(lambda operation, request: copy.deepcopy(result)).draft(request)
