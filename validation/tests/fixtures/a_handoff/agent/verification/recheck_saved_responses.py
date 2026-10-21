"""Offline validation of seven saved real responses. No network calls."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService
count = 0
for operation in ('extract', 'draft'):
    summary = json.loads((Path(__file__).resolve().parent / (operation + '-live-summary.json')).read_bytes())
    for case in summary['cases']:
        request = json.loads((ROOT / case['request_file']).read_bytes())
        response = json.loads((ROOT / case['response_file']).read_bytes())
        service = AgentService(lambda op, req: response)
        assert getattr(service, operation)(request) == response
        count += 1
assert count == 7
print('Seven saved real responses revalidated offline; no API calls.')
