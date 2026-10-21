import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from agent.dify_runner import DifyRunner, parse_object
from agent.agent_service import AgentService, AgentError

class DifyTests(unittest.TestCase):
    def setUp(self):
        self.runner = DifyRunner(extract_api_key='test-secret', user='user_demo')
        self.req = dict(schema_version='1.0',application_id='app_test',application_revision=1,
                        user_input={},extracted_documents=[],candidate_facts=[])
        self.result = {k:self.req[k] for k in ('schema_version','application_id','application_revision')}
        self.result.update(candidate_facts=[],questions=[],warnings=[])
    def envelope(self, result=None, status='succeeded'):
        return io.BytesIO(json.dumps({'data':{'status':status,'outputs':{'result':json.dumps(result or self.result)}}}).encode())
    def test_transport_to_service(self):
        with patch.object(self.runner._opener, 'open', return_value=self.envelope()) as opened:
            self.assertEqual(AgentService(self.runner).extract(self.req),self.result)
        req=opened.call_args.args[0]
        payload=json.loads(req.data)
        self.assertEqual(req.full_url,'https://api.dify.ai/v1/workflows/run')
        self.assertEqual(req.get_header('Authorization'),'Bearer test-secret')
        self.assertEqual(payload['response_mode'],'blocking')
        self.assertEqual(payload['user'],'user_demo')
        self.assertEqual(json.loads(payload['inputs']['request_json']),self.req)
    def test_http_error_is_redacted(self):
        with patch.object(self.runner._opener,'open',side_effect=HTTPError(self.runner.url,401,'test-secret',{},io.BytesIO(b'patient secret'))):
            with self.assertRaisesRegex(AgentError,'Dify HTTP error: 401') as ctx:
                self.runner('extract',self.req)
        self.assertNotIn('secret',str(ctx.exception))
    def test_timeout_no_retry(self):
        with patch.object(self.runner._opener,'open',side_effect=TimeoutError()) as opened:
            with self.assertRaises(AgentError): self.runner('extract',self.req)
            self.assertEqual(opened.call_count,1)
    def test_known_http_code_is_retained_without_private_message_or_retry(self):
        body = json.dumps({'code': 'provider_quota_exceeded', 'message': 'test-secret patient text'}).encode()
        error = HTTPError(self.runner.url, 400, 'test-secret', {}, io.BytesIO(body))
        with patch.object(self.runner._opener, 'open', side_effect=error) as opened:
            with self.assertRaises(AgentError) as ctx:
                AgentService(self.runner).extract(self.req)
        self.assertEqual(str(ctx.exception), 'Dify HTTP error: 400 (provider_quota_exceeded)')
        self.assertEqual(opened.call_count, 1)
    def test_untrusted_or_oversize_http_code_is_not_logged(self):
        bodies = [b'private invalid json', b'{"code":"patient-secret"}',
                  b'{"code": ["provider_quota_exceeded"]}',
                  json.dumps({'code': 'provider_quota_exceeded', 'message': 'x'*65536}).encode(),
                  b'{"code":"provider_quota_exceeded","code":"patient-secret"}']
        for body in bodies:
            with self.subTest(length=len(body)):
                error = HTTPError(self.runner.url, 400, 'test-secret', {}, io.BytesIO(body))
                with patch.object(self.runner._opener, 'open', side_effect=error):
                    with self.assertRaises(AgentError) as ctx:
                        self.runner('extract', self.req)
                self.assertEqual(str(ctx.exception), 'Dify HTTP error: 400')
    def test_http_error_stays_redacted_through_service(self):
        error = HTTPError(self.runner.url, 401, 'test-secret', {}, io.BytesIO(b'patient secret'))
        with patch.object(self.runner._opener, 'open', side_effect=error) as opened:
            with self.assertRaisesRegex(AgentError, '^Dify HTTP error: 401$') as ctx:
                AgentService(self.runner).extract(self.req)
            self.assertNotIn('secret', str(ctx.exception))
            self.assertEqual(opened.call_count, 1)
    def test_failed_workflow(self):
        with patch.object(self.runner._opener,'open',return_value=self.envelope(status='failed')):
            with self.assertRaises(AgentError): self.runner('extract',self.req)
    def test_missing_output(self):
        with patch.object(self.runner._opener,'open',return_value=io.BytesIO(b'{"data":{"status":"succeeded","outputs":{}}}')):
            with self.assertRaises(AgentError): self.runner('extract',self.req)
    def test_strict_json(self):
        for raw in ['```json\n{}\n```','{"a":1,"a":2}','{"a":NaN}','[]','not JSON']:
            with self.subTest(raw=raw),self.assertRaises(AgentError): parse_object(raw)
    def test_unconfigured_draft(self):
        with patch.object(self.runner._opener,'open') as opened:
            with self.assertRaises(AgentError): self.runner('draft',self.req)
            opened.assert_not_called()
    def test_untrusted_base(self):
        for url in ['http://example.com/v1','https://user:pass@example.com/v1','https://example.com/v1?token=x']:
            with self.assertRaises(AgentError): DifyRunner(extract_api_key='x',user='u',base_url=url)
    def test_invalid_configuration_is_safe_and_rejected_before_network(self):
        from agent.errors import AgentConfigurationError
        cases = [dict(base_url='https://example.com:bad/v1'),
                 dict(base_url='https://[invalid/v1'), dict(base_url=None),
                 dict(base_url='https://example.com/ v1'),
                 dict(extract_api_key='private\nvalue'), dict(extract_api_key='   '),
                 dict(extract_api_key=123), dict(timeout='90'), dict(timeout=True)]
        for overrides in cases:
            with self.subTest(fields=list(overrides)), patch('agent.dify_runner.build_opener') as opened:
                options = dict(extract_api_key='test-secret', user='user_demo')
                options.update(overrides)
                with self.assertRaises(AgentConfigurationError) as caught:
                    DifyRunner(**options)
                self.assertNotIn('private', str(caught.exception))
                opened.assert_not_called()
    def test_revision_rejected_after_transport(self):
        self.result['application_revision']=2
        with patch.object(self.runner._opener,'open',return_value=self.envelope()):
            with self.assertRaises(AgentError): AgentService(self.runner).extract(self.req)
    def test_existing_fact_omission(self):
        self.req['candidate_facts']=[dict(fact_id='fact_keep',field='contact.city',value={'kind':'text','value':'西安市'},source_type='user_input',evidence_ids=[],verification_status='pending',user_confirmed=True)]
        with patch.object(self.runner._opener,'open',return_value=self.envelope()):
            with self.assertRaisesRegex(AgentError,'omitted'): AgentService(self.runner).extract(self.req)
