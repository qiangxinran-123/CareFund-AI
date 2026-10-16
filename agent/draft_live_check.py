"""Run three synthetic requests against a separately published draft workflow."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

from .agent_service import AgentError, AgentService
from .dify_runner import DifyRunner, parse_object
from .live_check import credentials

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / '.local' / 'draft-live-status.json'
CASE_NAMES = ('draft-request.json', 'draft-uncertain-request.json', 'draft-injection-request.json')


def save(report):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(REPORT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', action='store_true')
    args = parser.parse_args()
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
              'transport': 'real_dify_draft_api', 'status': 'preflight', 'cases': []}
    save(report)
    try:
        requests = [(ROOT / 'examples' / name, parse_object((ROOT / 'examples' / name).read_bytes())) for name in CASE_NAMES]
        service = AgentService(None)
        for path, request in requests:
            service.validate_draft_request(request)
        report['status'] = 'awaiting_local_draft_credentials'
        save(report)
        base, key = credentials(args.gui, operation='draft', case_count=len(requests))
        if not key:
            report['status'] = 'cancelled_before_api_call'
            save(report)
            return 1
        service.runner = DifyRunner(draft_api_key=key, user='carefund_synthetic_draft', base_url=base)
        key = None
        output = REPORT.parent / datetime.now(timezone.utc).strftime('draft-live-%Y%m%dT%H%M%S%fZ')
        output.mkdir()
        for path, request in requests:
            record = {'case': path.stem, 'application_id': request['application_id'],
                      'application_revision': request['application_revision'],
                      'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                      'status': 'calling_real_api'}
            report['cases'].append(record)
            report['status'] = 'running'
            save(report)
            start = time.monotonic()
            try:
                response = service.draft(request)
            except AgentError as exc:
                record.update(status='failed', error=str(exc), elapsed_seconds=round(time.monotonic() - start, 2))
                shape = getattr(service.runner, 'last_result_shape', None)
                if isinstance(shape, dict):
                    record['response_shape'] = shape
                report['status'] = 'stopped_on_failure_no_retry'
                save(report)
                return 1
            destination = output / (path.stem + '.response.json')
            destination.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding='utf-8')
            record.update(status='schema_references_and_literal_content_passed',
                          response_file=str(destination), elapsed_seconds=round(time.monotonic() - start, 2))
            save(report)
        report.update(status='three_synthetic_draft_calls_passed',
                      completed_at=datetime.now(timezone.utc).isoformat(),
                      scope_limit='Exact literal fidelity only; not independent truth or evidence-support verification. Injection text stays quoted as test data, never a new factual claim.')
    except AgentError as exc:
        report.update(status='failed', error=str(exc))
    except Exception as exc:
        report.update(status='local_error', error_type=type(exc).__name__)
    save(report)
    return 0 if report['status'] == 'three_synthetic_draft_calls_passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
