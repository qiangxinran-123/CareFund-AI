"""Run only the four synthetic handoff cases; credentials remain in process memory."""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import platform
import time

from .agent_service import AgentError, AgentService
from .dify_runner import DifyRunner, parse_object


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / 'agent' / 'examples' / 'extract_cases'
REPORT = ROOT / 'agent' / '.local' / 'live-status.json'


def save(report):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    temporary = REPORT.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(REPORT)


def credentials(gui, *, operation='extract', case_count=4):
    if operation not in ('extract', 'draft'):
        raise AgentError('Unsupported credential operation')
    base = os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1')
    key = os.getenv('DIFY_' + operation.upper() + '_API_KEY')
    if key:
        if operation == 'draft' and key == os.getenv('DIFY_EXTRACT_API_KEY'):
            raise AgentError('Use a separate draft workflow API key')
        return base, key
    if not gui:
        return base, getpass.getpass('Dify ' + operation + ' app API key (hidden): ').strip()
    import tkinter as tk
    from tkinter import ttk, messagebox
    window = tk.Tk()
    label = '抽取' if operation == 'extract' else '草稿'
    window.title('CareFund - 本地 Dify ' + label + '联调')
    window.resizable(False, False)
    panel = ttk.Frame(window, padding=20)
    panel.grid()
    ttk.Label(panel, text=f'仅运行 {case_count} 个虚构{label}案例，可能消耗 Dify/模型额度。\n密钥仅保存在此进程内存中，不写入文件或聊天。').grid(columnspan=2, pady=(0, 16))
    ttk.Label(panel, text='API 服务地址').grid(row=1, column=0, sticky='w')
    base_var = tk.StringVar(value=base)
    ttk.Entry(panel, textvariable=base_var, width=48).grid(row=1, column=1, pady=5)
    ttk.Label(panel, text=label + '应用 API 密钥').grid(row=2, column=0, sticky='w')
    key_var = tk.StringVar()
    entry = ttk.Entry(panel, textvariable=key_var, show='*', width=48)
    entry.grid(row=2, column=1, pady=5)
    values = []

    def submit():
        address, secret = base_var.get().strip(), key_var.get().strip()
        try:
            if operation == 'draft' and secret == os.getenv('DIFY_EXTRACT_API_KEY'):
                raise AgentError('Use a separate draft workflow API key')
            DifyRunner(**{operation + '_api_key': secret}, user='carefund_local_synthetic', base_url=address)
        except AgentError as exc:
            messagebox.showerror('配置需要调整', str(exc), parent=window)
            return
        values.extend((address, secret))
        key_var.set('')
        window.destroy()

    ttk.Button(panel, text='开始真实联调', command=submit).grid(row=3, columnspan=2, pady=(16, 0))
    window.bind('<Return>', lambda event: submit())
    window.after(100, entry.focus_force)
    window.mainloop()
    return tuple(values) if values else (None, None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gui', action='store_true', help='Use a local masked credential window')
    args = parser.parse_args()
    report = {'started_at': datetime.now(timezone.utc).isoformat(),
              'python': platform.python_version(), 'transport': 'real_dify_api',
              'status': 'preflight', 'cases': []}
    save(report)
    try:
        files = sorted(CASES.glob('[0-9][0-9]_*.json'))
        if len(files) != 4:
            raise AgentError('Expected the four original synthetic handoff cases')
        requests = [(path, parse_object(path.read_bytes())) for path in files]
        service = AgentService(None)
        for path, request in requests:
            service.validate(request, 'AgentExtractRequest')
        report['status'] = 'awaiting_local_credentials'
        save(report)
        base, key = credentials(args.gui)
        if not key:
            report['status'] = 'cancelled_before_api_call'
            save(report)
            return 1
        service.runner = DifyRunner(extract_api_key=key, user='carefund_local_synthetic', base_url=base)
        key = None
        output = REPORT.parent / datetime.now(timezone.utc).strftime('live-%Y%m%dT%H%M%S%fZ')
        output.mkdir()
        report['output_directory'] = str(output)
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
                result = service.extract(request)
            except AgentError as exc:
                record.update(status='failed', error=str(exc), elapsed_seconds=round(time.monotonic() - start, 2))
                report['status'] = 'stopped_on_failure_no_retry'
                save(report)
                return 1
            destination = output / (path.stem + '.response.json')
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            record.update(status='schema_and_references_passed', response_file=str(destination),
                          elapsed_seconds=round(time.monotonic() - start, 2),
                          semantic_review='pending_manual_review_against_expected.json')
            save(report)
        report['status'] = 'api_checks_completed_semantic_review_pending'
        save(report)
        return 0
    except AgentError as exc:
        report.update(status='failed', error=str(exc))
    except Exception as exc:
        # Do not serialize unexpected exception text, local variables or tracebacks.
        report.update(status='local_error', error_type=type(exc).__name__)
    save(report)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
