"""Offline replay of 27 fictional saved outputs. Never imports a live runner."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import socket
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService
from agent.batch_check import semantic_checks


def main():
    suite = json.loads((HERE / 'synthetic-replay.json').read_bytes())
    decisions = json.loads((HERE / 'review-results.json').read_bytes())
    counts, contextual_flags = Counter(), []
    with patch.object(socket, 'socket', side_effect=AssertionError('Network forbidden in offline replay')):
        for entry in suite['cases']:
            case, response = entry['case'], entry['response']
            if case['data_class'] != 'synthetic':
                raise ValueError('Replay allows fictional data only')
            raw = json.dumps({'case': case, 'response': response}, ensure_ascii=False,
                             sort_keys=True, separators=(',', ':')).encode()
            if hashlib.sha256(raw).hexdigest() != entry['payload_sha256']:
                raise ValueError('Saved fictional payload fingerprint mismatch')
            result = getattr(AgentService(lambda op, req: response), case['operation'])(case['request'])
            failures, flags = semantic_checks(case, result)
            if failures:
                raise ValueError('Limited historical checks failed: ' + entry['review_id'])
            if flags:
                contextual_flags.append(entry['review_id'])
            counts[case['operation']] += 1
    assert counts == {'extract': 21, 'draft': 6}
    print(json.dumps(dict(mode='offline_saved_fictional_responses', model_generations=0,
        boundary_and_limited_checks=dict(counts), contextual_scan_flags=contextual_flags,
        findings_preserved={j['review_id']: j['findings'] for j in decisions['judgments']
                            if j['data_class'] == 'synthetic' and j['findings']},
        semantic_acceptance_claimed=False), ensure_ascii=True))


if __name__ == '__main__':
    # The original immutable report and ZIP keep the old 27-pass result.
    # Current A deliberately rejects S014; use the current-policy regression.
    import runpy
    runpy.run_path(str(HERE.parent / 'content-fix-20261017' / 'verify_saved.py'), run_name='__main__')
