"""Revalidate saved outputs and exported DSL hashes offline; never calls an API."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService
from agent.dify_runner import parse_object

summary = parse_object((HERE / 'summary.json').read_bytes())
for case in summary['cases']:
    request_raw = (ROOT / case['request_file']).read_bytes()
    response_raw = (ROOT / case['response_file']).read_bytes()
    assert hashlib.sha256(request_raw).hexdigest() == case['request_sha256']
    assert hashlib.sha256(response_raw).hexdigest() == case['response_sha256']
    response = parse_object(response_raw)
    service = AgentService(lambda operation, request: response)
    assert getattr(service, case['operation'])(parse_object(request_raw)) == response
for export in summary['workflow_exports']:
    workflow_raw = (ROOT / export['workflow_file']).read_bytes()
    assert hashlib.sha256(workflow_raw).hexdigest() == export['sha256']
print(f"{len(summary['cases'])} saved outputs passed strict parser, contract and AgentService policy checks offline; no API calls.")
print(f"{len(summary['workflow_exports'])} exported workflow SHA-256 hashes matched.")
