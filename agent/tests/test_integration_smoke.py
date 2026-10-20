"""Read-only workflow-key role checks; no credentials or real API calls."""
import io
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from agent.agent_service import AgentError
from agent import integration_smoke


class SmokeSetupTests(unittest.TestCase):
    def opener(self, name):
        response = io.BytesIO(json.dumps({'name': name, 'mode': 'workflow'}).encode())
        return Mock(open=Mock(return_value=response))

    def test_role_detection_accepts_reverse_key_order_without_serializing_keys(self):
        names = list(integration_smoke.APP_NAMES)
        with patch.object(integration_smoke, 'build_opener', side_effect=[self.opener(names[1]), self.opener(names[0])]):
            roles, mappings = integration_smoke.identify('https://api.dify.ai/v1', ('draft-private-value', 'extract-private-value'))
        self.assertEqual(roles, {'draft': 'draft-private-value', 'extract': 'extract-private-value'})
        self.assertNotIn('private-value', json.dumps(mappings))

    def test_same_app_twice_is_rejected_before_generation(self):
        name = next(iter(integration_smoke.APP_NAMES))
        with patch.object(integration_smoke, 'build_opener', side_effect=[self.opener(name), self.opener(name)]):
            with self.assertRaises(AgentError):
                integration_smoke.identify('https://api.dify.ai/v1', ('one', 'two'))

    def test_unexpected_app_does_not_guess_its_role(self):
        with patch.object(integration_smoke, 'build_opener', return_value=self.opener('Other app')):
            with self.assertRaises(AgentError):
                integration_smoke.identify('https://api.dify.ai/v1', ('one', 'two'))

    def test_info_http_error_is_redacted(self):
        opener = Mock()
        opener.open.side_effect = HTTPError('https://api.dify.ai/v1/info', 401, 'private-key', {}, io.BytesIO(b'private-body'))
        with patch.object(integration_smoke, 'build_opener', return_value=opener):
            with self.assertRaises(AgentError) as caught:
                integration_smoke.identify('https://api.dify.ai/v1', ('one', 'two'))
        self.assertEqual(str(caught.exception), 'Dify app metadata HTTP error: 401')
        self.assertEqual(opener.open.call_count, 1)

    def test_configured_environment_never_opens_an_interactive_prompt(self):
        with patch.dict(os.environ, {'DIFY_EXTRACT_API_KEY': 'one', 'DIFY_DRAFT_API_KEY': 'two'}), \
                patch.object(integration_smoke.getpass, 'getpass') as prompt:
            base, first, second = integration_smoke.credentials(False)
        self.assertEqual((first, second), ('one', 'two'))
        prompt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
