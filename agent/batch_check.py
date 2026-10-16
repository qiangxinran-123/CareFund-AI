"""Bounded real Dify evaluation; no raw MDCC narrative uploads or retries."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time

from .agent_service import AgentError, AgentService
from .dify_runner import DifyRunner, parse_object
from .mdcc_prepare import CLAUSE

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / '.local/mdcc/batch-live-status.json'
MEDICAL_MONEY = ('treatment.paid_cost', 'treatment.estimated_cost')
EXCERPT_PREFIX = '公开众筹叙述的匿名最小摘录，仅整理原句，不代表诊断已核验。原文：'
EXCERPT_SUFFIX = '。其余信息未提供。'


def semantic_checks(case, result):
    """Partial automatic acceptance checks; not independent clinical annotation."""
    if case['operation'] == 'draft':
        return [], []  # Exact content has already been checked by AgentService.
    expected = case['expectation']
    facts = result['candidate_facts']
    failures, flags = [], []
    def text(field):
        return ' '.join(str(f['value']['value']).lower() for f in facts if f['field'] == field)
    def money_values(field):
        return [f['value']['value'] for f in facts if f['field'] == field and f['value']['kind'] == 'money']
    if expected.get('no_medical_money') and any(money_values(f) for f in MEDICAL_MONEY):
        failures.append('invented_or_misattributed_medical_money')
    if expected.get('no_medical_money') and not expected.get('allow_ambiguous_cost_text'):
        for f in facts:
            if f['field'] in MEDICAL_MONEY and f['value']['kind'] == 'text' and re.search(r'\d|[一二三四五六七八九十百千万亿]+(?:元|美元)', f['value']['value']):
                failures.append('numeric_medical_cost_text_without_input_cost')
                break
    if expected.get('no_estimate_money') and money_values('treatment.estimated_cost'):
        failures.append('invented_estimate')
    if expected.get('no_medical_summary'):
        medical = text('patient.medical_summary')
        if medical and not re.search(r'未提供|未知|不清楚|未说明|没有提供', medical):
            failures.append('unsupported_medical_summary')
    for field, values in expected.get('money_exact', {}).items():
        actual = money_values(field)
        if sorted(actual, key=str) != sorted(values, key=str):
            failures.append('money_value_or_role_mismatch:' + field)
    if 'medical_any' in expected:
        medical = text('patient.medical_summary')
        if not any(token.lower() in medical for token in expected['medical_any']):
            failures.append('medical_key_phrase_missing')
    for group in expected.get('medical_all_groups', []):
        medical = re.sub(r'\s+', '', text('patient.medical_summary'))
        if not any(re.sub(r'\s+', '', token.lower()) in medical for token in group):
            failures.append('medical_disease_or_stage_component_missing')
            break
    if expected.get('input_source_only') and any(f['source_type'] != 'user_input' for f in facts):
        failures.append('public_narrative_misrepresented_as_other_source')
    if 'relationship_any' in expected:
        relation = text('patient.relationship_to_applicant')
        if not any(token.lower() in relation for token in expected['relationship_any']):
            failures.append('relationship_missing_or_wrong')
    if expected.get('must_question') and not result['questions']:
        failures.append('required_clarification_absent')
    if expected.get('no_date_value') and any(f['value']['kind'] == 'date' for f in facts):
        failures.append('completed_unknown_calendar_date')
    if 'currency_guard' in expected:
        currency = expected['currency_guard']
        paid = money_values('treatment.paid_cost')
        if paid:
            if any(v['currency'] != currency or v['amount_minor'] != expected['expected_foreign_amount_minor'] for v in paid):
                failures.append('foreign_amount_or_currency_changed')
        else:
            paid_text = text('treatment.paid_cost')
            amount = expected['expected_foreign_amount_minor']
            numeric = f'{amount//100}.{amount%100:02d}'
            if not (('usd' in paid_text or '美元' in paid_text) and numeric in paid_text):
                failures.append('foreign_paid_cost_not_preserved')
            if re.search(r'cny|rmb|人民币', paid_text):
                failures.append('foreign_currency_mislabeled_in_text')
    if 'conflict_amounts' in expected:
        actual = money_values('treatment.estimated_cost')
        if sorted(v['amount_minor'] for v in actual) != sorted(expected['conflict_amounts']) or any(v['currency'] != 'CNY' for v in actual):
            failures.append('conflicting_values_not_both_preserved')
        for amount, source in zip(expected['conflict_amounts'], ('document', 'user_input')):
            if not any(f['field'] == 'treatment.estimated_cost' and f['value']['kind'] == 'money'
                       and f['value']['value']['amount_minor'] == amount and f['source_type'] == source for f in facts):
                failures.append('conflicting_value_source_wrong')
        if not result['warnings']:
            failures.append('conflict_warning_absent')
    if len(result['questions']) > 3:
        failures.append('too_many_questions')
    if any(q['required'] for q in result['questions']):
        failures.append('unprovided_required_rule')
    prose = json.dumps(result, ensure_ascii=False)
    if re.search(r'平台(?:建议|要求|规定|强制)', prose):
        flags.append('platform_reference_needs_context_review')
    if re.search(r'加快.{0,6}审核|(?:提高|提升).{0,8}通过', prose):
        flags.append('approval_effect_claim_needs_context_review')
    return failures, flags


def load_cases(path, operation='all', limit=100):
    suite = parse_object(path.read_bytes())
    cases = suite.get('cases')
    if not isinstance(cases, list) or not cases or len(cases) > 100:
        raise AgentError('Expected 1 to 100 prepared evaluation cases')
    selected = [c for c in cases if operation == 'all' or c.get('operation') == operation][:limit]
    if not selected:
        raise AgentError('No selected cases')
    seen = set()
    service = AgentService(None)
    for case in selected:
        identifier = case.get('case_id', '')
        if not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', identifier) or identifier in seen:
            raise AgentError('Invalid or duplicate evaluation case ID')
        seen.add(identifier)
        if case.get('data_class') not in ('synthetic', 'minimal_anonymous_public_excerpt'):
            raise AgentError('Raw or unreviewed real narrative is not allowed in this batch runner')
        if case['data_class'] == 'minimal_anonymous_public_excerpt':
            req = case['request']
            description = req['user_input'].get('description', '')
            if (case['operation'] != 'extract' or not description.startswith(EXCERPT_PREFIX)
                    or not description.endswith(EXCERPT_SUFFIX) or req['extracted_documents'] or req['candidate_facts']
                    or set(req['user_input']) != {'description'}):
                raise AgentError('Anonymous excerpt envelope is not the reviewed format')
            clause = description[len(EXCERPT_PREFIX):-len(EXCERPT_SUFFIX)]
            if not CLAUSE.fullmatch(clause):
                raise AgentError('Anonymous excerpt contains text outside the allowed dictionary')
        if case['operation'] == 'draft':
            service.validate_draft_request(case['request'])
        elif case['operation'] == 'extract':
            service.validate(case['request'], 'AgentExtractRequest')
        else:
            raise AgentError('Unknown batch operation')
    return suite, selected


def credentials(gui, operations, counts):
    base = os.getenv('DIFY_BASE_URL', 'https://api.dify.ai/v1')
    keys = {op: os.getenv('DIFY_' + op.upper() + '_API_KEY') for op in operations}
    if all(keys.values()):
        return base, keys
    if not gui:
        import getpass
        return base, {op: keys[op] or getpass.getpass('Dify ' + op + ' key (hidden): ').strip() for op in operations}
    import tkinter as tk
    from tkinter import messagebox, ttk
    window = tk.Tk()
    window.title('CareFund - MDCC 批量测试（隐藏密钥）')
    window.resizable(False, False)
    panel = ttk.Frame(window, padding=20)
    panel.grid()
    ttk.Label(panel, text=f'本次最多抽取 {counts.get("extract", 0)} 次、草稿 {counts.get("draft", 0)} 次。\n仅发送最小匿名短句和明确标注的虚构案例，可能消耗额度。\n密钥只留在进程内存中；无自动重试。').grid(columnspan=2, pady=(0, 12))
    ttk.Label(panel, text='API 服务地址').grid(row=1, column=0, sticky='w')
    base_var = tk.StringVar(value=base)
    ttk.Entry(panel, textvariable=base_var, width=48).grid(row=1, column=1, pady=5)
    variables = {}
    for index, operation in enumerate(operations, start=2):
        label = '抽取应用密钥' if operation == 'extract' else '新草稿应用密钥'
        ttk.Label(panel, text=label).grid(row=index, column=0, sticky='w')
        variable = tk.StringVar(value=keys[operation] or '')
        variables[operation] = variable
        ttk.Entry(panel, textvariable=variable, show='*', width=48).grid(row=index, column=1, pady=5)
    values = []
    def submit():
        supplied = {op: var.get().strip() for op, var in variables.items()}
        if not all(supplied.values()):
            messagebox.showerror('缺少密钥', '请填写本次所需的每个应用密钥。', parent=window)
            return
        try:
            DifyRunner(user='carefund_mdcc_evaluation', base_url=base_var.get().strip(),
                       extract_api_key=supplied.get('extract'), draft_api_key=supplied.get('draft'))
        except AgentError as exc:
            messagebox.showerror('配置需要调整', str(exc), parent=window)
            return
        values.extend((base_var.get().strip(), supplied))
        for variable in variables.values():
            variable.set('')
        window.destroy()
    ttk.Button(panel, text='开始批量真实测试', command=submit).grid(row=len(operations)+2, columnspan=2, pady=(12, 0))
    window.mainloop()
    return values if values else (None, {})


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def run_cases(cases, runner, report, report_path):
    service = AgentService(runner)
    output = report_path.parent / datetime.now(timezone.utc).strftime('batch-live-%Y%m%dT%H%M%S%fZ')
    output.mkdir()
    boundary_streak = 0
    for case in cases:
        record = {'case_id': case['case_id'], 'group': case['group'], 'operation': case['operation'],
                  'data_class': case['data_class'], 'request_sha256': hashlib.sha256(json.dumps(case['request'], ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                  'status': 'calling_real_api'}
        report['cases'].append(record)
        report['status'] = 'running'
        save(report_path, report)
        start = time.monotonic()
        try:
            result = getattr(service, case['operation'])(case['request'])
        except AgentError as exc:
            record.update(status='boundary_or_transport_rejected', error=str(exc),
                          elapsed_seconds=round(time.monotonic()-start, 2))
            boundary_streak += 1
            if str(exc).startswith('Dify ') or boundary_streak >= 3:
                report['status'] = 'stopped_on_error_no_retry'
                break
        else:
            boundary_streak = 0
            failures, flags = semantic_checks(case, result)
            destination = output / (case['case_id'] + '.response.json')
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            record.update(status='automatic_checks_failed' if failures else 'automatic_checks_passed',
                          failures=failures, review_flags=flags, response_file=str(destination),
                          elapsed_seconds=round(time.monotonic()-start, 2))
        save(report_path, report)
    else:
        report['status'] = 'completed_with_findings' if any(c['status'] != 'automatic_checks_passed' or c.get('review_flags') for c in report['cases']) else 'completed_automatic_checks_passed'
    report['completed_at'] = datetime.now(timezone.utc).isoformat()
    report['counts'] = dict(Counter(c['status'] for c in report['cases']))
    save(report_path, report)
    return 0 if report['status'] == 'completed_automatic_checks_passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT / '.local/mdcc/evaluation/batch-cases.json')
    parser.add_argument('--operation', choices=('all', 'extract', 'draft'), default='all')
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--gui', action='store_true')
    parser.add_argument('--report', type=Path, default=REPORT)
    args = parser.parse_args()
    if not 1 <= args.limit <= 100:
        parser.error('limit must be between 1 and 100')
    if args.report.exists():
        parser.error('Report already exists; use --report with a new path to preserve previous attempts')
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'transport': 'real_dify_api',
              'status': 'preflight', 'cases': [],
              'scope_limit': 'Partial automatic checks on minimal anonymous clauses and synthetic cases; not full-MDCC accuracy, clinical truth, OCR or end-to-end acceptance.'}
    save(args.report, report)
    try:
        _, cases = load_cases(args.suite, args.operation, args.limit)
        report['suite_sha256'] = hashlib.sha256(args.suite.read_bytes()).hexdigest()
        report['planned_counts'] = dict(Counter(c['operation'] for c in cases))
        report['planned_cases'] = len(cases)
        report['status'] = 'awaiting_local_credentials'
        save(args.report, report)
        operations = [op for op in ('extract', 'draft') if op in report['planned_counts']]
        base, keys = credentials(args.gui, operations, report['planned_counts'])
        if not keys:
            report['status'] = 'cancelled_before_api_call'
            save(args.report, report)
            return 1
        runner = DifyRunner(user='carefund_mdcc_evaluation', base_url=base,
                            extract_api_key=keys.get('extract'), draft_api_key=keys.get('draft'))
        keys.clear()
        return run_cases(cases, runner, report, args.report)
    except AgentError as exc:
        report.update(status='failed', error=str(exc))
    except Exception as exc:
        report.update(status='local_error', error_type=type(exc).__name__)
    save(args.report, report)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
