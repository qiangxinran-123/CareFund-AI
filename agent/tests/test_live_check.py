"""Offline checks of the live-check launcher, never evidence of real API success."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent import live_check
from agent.agent_service import AgentError


class LiveCheckTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.report = Path(self.temporary.name) / 'live-status.json'
        report_patch = patch.object(live_check, 'REPORT', self.report)
        report_patch.start()
        self.addCleanup(report_patch.stop)
        argv_patch = patch('sys.argv', ['live_check'])
        argv_patch.start()
        self.addCleanup(argv_patch.stop)

    def test_cancel_does_not_call_api(self):
        with patch.object(live_check, 'credentials', return_value=(None, None)), \
                patch.object(live_check, 'DifyRunner') as runner:
            self.assertEqual(live_check.main(), 1)
            runner.assert_not_called()
        self.assertEqual(json.loads(self.report.read_text(encoding='utf-8'))['status'],
                         'cancelled_before_api_call')

    def test_transport_failure_stops_without_retry_or_secret_in_report(self):
        with patch.object(live_check, 'credentials', return_value=('https://api.dify.ai/v1', 'test-secret')), \
                patch.object(live_check, 'DifyRunner') as runner:
            runner.return_value.side_effect = AgentError('Dify HTTP error: 401')
            self.assertEqual(live_check.main(), 1)
            self.assertEqual(runner.return_value.call_count, 1)
        text = self.report.read_text(encoding='utf-8')
        self.assertNotIn('test-secret', text)
        report = json.loads(text)
        self.assertEqual(report['status'], 'stopped_on_failure_no_retry')
        self.assertEqual(report['cases'][0]['error'], 'Dify HTTP error: 401')

    def test_mocked_completion_keeps_semantic_review_pending(self):
        def response(operation, request):
            return {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')} | {
                'candidate_facts': request['candidate_facts'], 'questions': [], 'warnings': []}
        with patch.object(live_check, 'credentials', return_value=('https://api.dify.ai/v1', 'test-secret')), \
                patch.object(live_check, 'DifyRunner') as runner:
            runner.return_value.side_effect = response
            self.assertEqual(live_check.main(), 0)
            self.assertEqual(runner.return_value.call_count, 4)
        report = json.loads(self.report.read_text(encoding='utf-8'))
        self.assertEqual(report['status'], 'api_checks_completed_semantic_review_pending')
        self.assertEqual(len(report['cases']), 4)
        self.assertTrue(all(case['semantic_review'] == 'pending_manual_review_against_expected.json'
                            for case in report['cases']))
