"""Supplemental prose review after the frozen automatic run; no API calls."""
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

if __name__=='__main__':
    summary=json.loads((HERE/'summary.json').read_bytes())
    pattern=re.compile(r'平台(?:常用|通常|默认|支持|仅支持|只接受|限制|币种)')
    hits=[]
    for row in summary['cases']:
        if row['operation']!='extract' or 'response_file' not in row:continue
        result=json.loads((ROOT/row['response_file']).read_bytes())
        prose=list(result['warnings'])
        prose.extend(q[k] for q in result['questions'] for k in ('question','reason'))
        if any(pattern.search(t) for t in prose):hits.append(row)
    assert [r['case_id'] for r in hits]==['expand_synthetic_extract_007']
    row=hits[0]
    assert row['response_sha256']=='2d1307f752f61f2f8819e330a52937305cd45225b9269410b0f709304453c2e6'
    report=dict(date='2026-10-17',new_model_calls=0,
        automatic_results_preserved=True,
        cases_scanned_for_additional_platform_currency_claim=sum(r['operation']=='extract' and 'response_file' in r for r in summary['cases']),
        contextual_review_by='Codex; not independent business or clinical acceptance',
        findings=[dict(case_id=row['case_id'],response_sha256=row['response_sha256'],
            original_automatic_status=row['status'],classification='unsupported_platform_currency_comparison_in_warning',
            severity='wording_issue_requires_correction',
            synthetic_excerpt='币种与平台常用的人民币不同',
            issue='Input did not provide platform currency usage; this comparison has no supplied basis.',
            facts_preserved='Original USD amount and currency retained as text, with no conversion or fabricated CNY fact.',
            not_observed='No mandatory platform rule or approval-effect promise in this response.',
            automatic_check_gap='Original known-phrase scan did not cover platform currency-default comparisons.',
            disposition='open; correction candidate prepared, not published or re-generated',
            proposed_warning='已支付医疗费按用户自述保留为 USD 389.17，未换算，尚无材料核对。')],
        limits='Additional phrase scan is partial. Non-flagged outputs are not proven free of other semantic issues.')
    conclusion=dict(status='completed_with_content_finding',generation_calls=summary['calls_attempted'],
        automatic_checks_passed=summary['counts'].get('automatic_checks_passed',0),
        supplemental_content_findings=len(hits),cases_with_open_findings=[r['case_id'] for r in hits],
        new_model_calls_by_review=0,automatic_results_preserved=True,
        production_fix_published=False,correction_candidate='wording-correction-candidate.md',
        limits='Automatic checks passing is not complete semantic acceptance; the wording finding remains open.')
    for name,value in [('post-run-review.json',report),('evaluation-conclusion.json',conclusion)]:
        path=HERE/name
        if path.exists():assert json.loads(path.read_bytes())==value
        else:path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'additional_scanned_extracts':report['cases_scanned_for_additional_platform_currency_claim'],
        'open_wording_findings':len(hits),'new_model_calls':0,'automatic_history_preserved':True}))
