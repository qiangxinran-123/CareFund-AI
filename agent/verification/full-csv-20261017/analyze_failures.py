"""Offline analysis of actual failed responses; preserves original statuses."""
from collections import Counter
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha


if __name__ == '__main__':
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    records = [json.loads(r[0]) for r in db.execute('SELECT record FROM attempts ORDER BY source_row')]
    db.close()
    findings = []
    for record in records:
        if record['status'] == 'partial_checks_passed':
            continue
        item = {k: record.get(k) for k in ('case_id', 'source_row', 'status', 'error', 'total_tokens')}
        if record['source_row'] == 44:
            evidence = json.loads((PRIVATE / 'failure-000044.dify-detail.json').read_bytes())
            outputs = evidence['outputs']
            outputs = json.loads(outputs) if isinstance(outputs, str) else outputs
            value = outputs['result']
            item['evidence_kind'] = 'read_only_recovered_exact_request'
            item['evidence_sha256'] = sha((PRIVATE / 'failure-000044.dify-detail.json').read_bytes())
        elif record.get('wire_response_file'):
            raw = (ROOT / record['wire_response_file']).read_bytes()
            assert sha(raw) == record['wire_response_sha256']
            value = json.loads(raw)['data']['outputs']['result']
            item['evidence_kind'] = 'original_http_success_bytes_before_inner_json_parse'
            item['evidence_sha256'] = sha(raw)
        else:
            item.update(evidence_kind='no_response_bytes_received',
                        remote_execution_status='unknown_no_matching_run_recovered_by_bounded_read_only_lookup',
                        usage_basis='full_reservation_retained', automatic_retry=False)
            findings.append(item)
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            item.update(json_syntax='invalid', json_error=exc.msg,
                        json_error_line=exc.lineno, json_error_column=exc.colno,
                        disposition='failed_response_correctly_rejected_no_automatic_repair',
                        model_issue_fixed=False, automatic_retry=False)
        else:
            item['json_syntax'] = 'valid'
            if 'schema properties/questions/items/required' in record.get('error', ''):
                required = {'question_id', 'field', 'question', 'reason', 'required'}
                item['missing_question_fields'] = [dict(question_index=index,
                    missing=sorted(required - question.keys()))
                    for index, question in enumerate(parsed.get('questions', []))
                    if isinstance(question, dict) and required - question.keys()]
                item['disposition'] = 'schema_invalid_response_correctly_rejected_no_field_invention'
                item['model_issue_fixed'] = False
                item['automatic_retry'] = False
        findings.append(item)
    progress = json.loads((HERE / 'live-progress.json').read_bytes())
    result = dict(calls_attempted=len(records), counts=dict(Counter(r['status'] for r in records)),
                  findings=findings, cost_upper_bound_cny=progress['cost_upper_bound_cny'],
                  actual_provider_bill_read=False, full_file_model_test_complete=False,
                  next_step='User reports format-v4 publication; 4 new calls produced 2 schema rejections. Obtain fresh DSL to verify actual configuration before further changes or calls.',
                  external_calls_by_analysis=0)
    (HERE / 'failure-analysis.json').write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(result, ensure_ascii=False))
