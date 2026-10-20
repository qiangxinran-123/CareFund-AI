"""Stable, redacted failure categories for B background jobs."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from agent.agent_service import AgentError, AgentService
from agent.dify_runner import DifyRunner
from agent.errors import (AgentConfigurationError, AgentContractError,
    AgentHTTPError, AgentTransportError, AgentWorkflowError)


class IntegrationErrorTests(unittest.TestCase):
    def setUp(self):
        self.runner = DifyRunner(extract_api_key='synthetic-test-key', user='synthetic_user')
        self.service = AgentService(self.runner)
        self.request = dict(schema_version='1.0', application_id='app_errors', application_revision=1,
                            user_input={}, extracted_documents=[], candidate_facts=[])

    def test_configuration_failure_is_distinct_and_backwards_compatible(self):
        with self.assertRaises(AgentConfigurationError) as caught:
            DifyRunner(user='synthetic_user')
        self.assertIsInstance(caught.exception, AgentError)
        self.assertEqual(caught.exception.code, 'agent_configuration_error')

    def test_timeout_keeps_uncertain_execution_and_never_retries(self):
        with patch.object(self.runner._opener, 'open', side_effect=TimeoutError('private text')) as opened:
            with self.assertRaises(AgentTransportError) as caught:
                self.service.extract(self.request)
        self.assertTrue(caught.exception.execution_may_be_running)
        self.assertEqual(opened.call_count, 1)
        self.assertNotIn('private text', str(caught.exception))

    def test_failed_workflow_does_not_expose_provider_message(self):
        body = {'data': {'status': 'failed', 'error': 'private text'}}
        with patch.object(self.runner._opener, 'open', return_value=io.BytesIO(json.dumps(body).encode())):
            with self.assertRaises(AgentWorkflowError) as caught:
                self.service.extract(self.request)
        self.assertNotIn('private text', str(caught.exception))

    def test_http_failure_has_only_allowlisted_provider_code(self):
        body = b'{"code":"provider_quota_exceeded","message":"private text"}'
        error = HTTPError(self.runner.url, 400, 'private text', {}, io.BytesIO(body))
        with patch.object(self.runner._opener, 'open', side_effect=error):
            with self.assertRaises(AgentHTTPError) as caught:
                self.service.extract(self.request)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.provider_code, 'provider_quota_exceeded')
        self.assertNotIn('private text', str(caught.exception))

    def test_bad_json_and_contract_are_distinct_from_transport(self):
        for body in [b'private malformed response', b'{"data":{"status":"succeeded","outputs":{"result":"{}"}}}']:
            with self.subTest(body_length=len(body)):
                with patch.object(self.runner._opener, 'open', return_value=io.BytesIO(body)):
                    with self.assertRaises(AgentContractError) as caught:
                        self.service.extract(self.request)
                self.assertNotIn('private', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
