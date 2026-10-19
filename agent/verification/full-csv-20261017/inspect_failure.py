"""Recover this run's failed result via read-only Dify logs; never regenerate."""
from datetime import datetime
import argparse
import json
import re
import sqlite3
import sys
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import identify
from agent.agent_service import AgentError
from agent.dify_runner import parse_object, _NoRedirect


def main(source_row=44):
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    original = json.loads(db.execute('SELECT record FROM attempts WHERE source_row=?', (source_row,)).fetchone()[0])
    db.close()
    credentials = parse_object(sys.stdin.readline())
    key = identify(credentials)
    credentials.clear()
    getter = build_opener(_NoRedirect())
    reads = []

    def get(path):
        reads.append(path.split('?', 1)[0])
        request = Request('https://api.dify.ai/v1' + path, headers={'Authorization': 'Bearer ' + key})
        try:
            with getter.open(request, timeout=30) as response:
                raw = response.read(4 * 1024 * 1024 + 1)
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise AgentError('Read-only inspection HTTP error: ' + str(status)) from None
        except (URLError, OSError):
            raise AgentError('Read-only inspection network error') from None
        if len(raw) > 4 * 1024 * 1024:
            raise AgentError('Read-only inspection response too large')
        return parse_object(raw)

    report = {'generation_calls': 0, 'status': 'not_recovered', 'read_only_endpoints': reads}
    try:
        progress = parse_object((HERE / 'live-progress.json').read_bytes())
        params = urlencode({'page': 1, 'limit': 100,
                            'created_by_end_user_session_id': 'carefund_fullcsv_20261017',
                            'created_at__after': progress['started_at']})
        logs = get('/workflows/logs?' + params)
        relevant = [r for r in logs.get('data', []) if
                    (r.get('created_by_end_user') or {}).get('session_id') == 'carefund_fullcsv_20261017']
        report['matched_current_run_logs'] = len(relevant)
        for row in relevant[:6]:
            run = row.get('workflow_run', {})
            if original.get('total_tokens') and run.get('total_tokens') != original['total_tokens']:
                continue
            run_id = run.get('id', '')
            if not re.fullmatch(r'[0-9a-f-]{36}', run_id):
                continue
            detail = get('/workflows/run/' + run_id)
            inputs = detail.get('inputs', {})
            if isinstance(inputs, str):
                inputs = parse_object(inputs)
            request = parse_object(inputs['request_json']) if isinstance(inputs.get('request_json'), str) else None
            if not request or request.get('application_id') != f'app_fullcsv_{source_row:06d}':
                continue
            if sha(json.dumps(request, ensure_ascii=False, sort_keys=True).encode()) != original['request_sha256']:
                raise AgentError('Recovered request differs from local attempted request')
            target = PRIVATE / f'failure-{source_row:06d}.dify-detail.json'
            raw = (json.dumps(detail, ensure_ascii=False, indent=2) + '\n').encode()
            with target.open('xb') as stream:
                stream.write(raw)
            outputs = detail.get('outputs', {})
            if isinstance(outputs, str):
                outputs = parse_object(outputs)
            value = outputs.get('result')
            report.update(status='recovered_exact_failed_request', source_row=source_row,
                          detail_file=target.relative_to(ROOT).as_posix(), detail_sha256=sha(raw),
                          workflow_status=detail.get('status'), total_tokens=detail.get('total_tokens'),
                          result_type=type(value).__name__)
            if isinstance(value, str):
                report['result_bytes'] = len(value.encode())
                try:
                    parse_object(value)
                    report['strict_result_json'] = 'valid_on_recovered_detail'
                except AgentError:
                    report['strict_result_json'] = 'invalid'
                    try:
                        json.loads(value)
                    except json.JSONDecodeError as exc:
                        report.update(json_error=exc.msg, json_error_line=exc.lineno, json_error_column=exc.colno)
                    else:
                        report['json_error'] = 'Strict parser rejects duplicate keys, non-finite values, or non-object root'
            break
    except AgentError as exc:
        report.update(status='read_only_inspection_failed', error=str(exc))
    except Exception as exc:
        report.update(status='local_inspection_error', error_type=type(exc).__name__)
    finally:
        key = None
        credentials.clear()
        destination = HERE / 'failure-inspection.json'
        if source_row != 44:
            destination = HERE / f'failure-inspection-row{source_row:06d}.json'
        if destination.exists():
            index = 2
            while (HERE / f'failure-inspection-{index:03d}.json').exists():
                index += 1
            destination = HERE / f'failure-inspection-{index:03d}.json'
        with destination.open('xb') as stream:
            stream.write((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
        print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--row', type=int, default=44)
    args = parser.parse_args()
    main(args.row)
