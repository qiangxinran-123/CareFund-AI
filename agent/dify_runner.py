"""Dify Workflow Service API adapter. No retries or mock fallback."""
import json
import os
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from .errors import (AgentError, AgentConfigurationError, AgentContractError,
                     AgentHTTPError, AgentTransportError, AgentWorkflowError)


_SAFE_ERROR_CODES = frozenset({
    'invalid_param', 'not_workflow_app', 'provider_not_initialize',
    'provider_quota_exceeded', 'model_currently_not_support',
    'completion_request_error', 'too_many_requests', 'rate_limit_error',
})


def _http_error_code(error):
    """Read a bounded error body; return only a known constant, never its message."""
    try:
        raw = error.read(65537)
        if len(raw) > 65536:
            return None
        code = parse_object(raw).get('code')
        return code if isinstance(code, str) and code in _SAFE_ERROR_CODES else None
    except (AgentError, OSError, ValueError):
        return None


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('Non-finite JSON value')


def parse_object(text):
    try:
        value = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, TypeError, UnicodeError):
        raise AgentContractError('Dify returned invalid JSON') from None
    if not isinstance(value, dict):
        raise AgentContractError('Dify returned a non-object JSON value')
    return value


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class DifyRunner:
    def __init__(self, *, extract_api_key=None, user, base_url='https://api.dify.ai/v1',
                 timeout=90, draft_api_key=None):
        parsed = urlsplit(base_url)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise AgentConfigurationError('Dify base URL must be an HTTPS API base URL')
        if not (extract_api_key or draft_api_key) or not isinstance(user, str) or not user.strip():
            raise AgentConfigurationError('At least one Dify workflow API key and opaque user ID are required')
        if extract_api_key and extract_api_key == draft_api_key:
            raise AgentConfigurationError('Use separate extraction and draft workflow API keys')
        if not 0 < timeout <= 300:
            raise AgentConfigurationError('Invalid Dify timeout')
        self._keys = {'extract': extract_api_key, 'draft': draft_api_key}
        self.user = user
        self.url = base_url.rstrip('/') + '/workflows/run'
        self.timeout = timeout
        self._opener = build_opener(_NoRedirect())
        self.last_result_shape = None

    @classmethod
    def from_env(cls, *, user):
        return cls(extract_api_key=os.getenv('DIFY_EXTRACT_API_KEY'),
                   draft_api_key=os.getenv('DIFY_DRAFT_API_KEY'), user=user,
                   base_url=os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1'))

    def __call__(self, operation, request):
        self.last_result_shape = None
        key = self._keys.get(operation)
        if not key:
            raise AgentConfigurationError('Dify workflow is not configured for this operation')
        payload = {'inputs': {'request_json': json.dumps(request, ensure_ascii=False, allow_nan=False)},
                   'response_mode': 'blocking', 'user': self.user}
        req = Request(self.url, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                      headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'},
                      method='POST')
        # Never log the request, credentials, server error body, or patient content.
        try:
            with self._opener.open(req, timeout=self.timeout) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as exc:
            code = exc.code
            try:
                reason = _http_error_code(exc)
            finally:
                exc.close()
            raise AgentHTTPError(code, reason) from None
        except (URLError, TimeoutError, OSError):
            raise AgentTransportError('Dify network request failed or timed out; execution may still be running') from None
        if len(raw) > 4 * 1024 * 1024:
            raise AgentContractError('Dify response exceeds size limit')
        body = parse_object(raw)
        data = body.get('data')
        if not isinstance(data, dict) or data.get('status') != 'succeeded':
            raise AgentWorkflowError('Dify workflow did not succeed')
        outputs = data.get('outputs')
        if not isinstance(outputs, dict) or not isinstance(outputs.get('result'), str):
            raise AgentContractError('Dify workflow must return a result string')
        result = parse_object(outputs['result'])
        self.last_result_shape = {
            'has_candidate_sections': 'candidate_sections' in result,
            'has_candidate_facts': 'candidate_facts' in result,
            'has_questions': 'questions' in result,
            'candidate_sections_type': type(result.get('candidate_sections')).__name__,
            'warnings_type': type(result.get('warnings')).__name__,
        }
        return result
