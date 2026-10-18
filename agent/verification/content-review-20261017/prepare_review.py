"""Freeze an offline review sample. No network, keys, or new model generations."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
import sqlite3
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIVATE = ROOT / 'agent/.local/content-review-20261017'
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write(path, value):
    with path.open('xb') as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def main():
    PRIVATE.mkdir(parents=True, exist_ok=True)
    assert not (HERE / 'selection.json').exists()
    source = ROOT / 'agent/.local/full-csv-20261017'
    db = sqlite3.connect((source / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    db.execute('BEGIN')
    records = {n: json.loads(raw) | {'ledger_status': state} for n, state, raw in
               db.execute('SELECT source_row,status,record FROM attempts')}
    progress = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    assert progress['status'] != 'running'
    snapshot = dict(progress)
    db.close()
    eligible, seen = [], set()
    for line in (source / 'prepared-inputs.jsonl').open(encoding='utf-8'):
        case = json.loads(line)
        record = records.get(case['source_row'])
        if (not record or record['ledger_status'] not in ('partial_checks_passed', 'needs_context_review')
                or case['sanitized_text_sha256'] in seen):
            continue
        seen.add(case['sanitized_text_sha256'])
        raw = (ROOT / record['response_file']).read_bytes()
        assert sha(raw) == record['response_sha256']
        assert sha(json.dumps(case['request'], ensure_ascii=False, sort_keys=True).encode()) == record['request_sha256']
        response = json.loads(raw)
        AgentService(lambda op, req: response).extract(case['request'])
        description = case['request']['user_input'].get('description', '')
        text = description.split('字段原文：', 1)[-1].removesuffix('。其他信息未提供。')
        eligible.append(dict(case=case, record=record, response=response, text=text))
    patterns = dict(uncertainty=r'疑似|考虑|可能|待查|待排|疑[似为]?',
        negation_or_nonprefix=r'排除|未见|未确诊|不是|非|否认|未诊断',
        stage=r'[ⅠⅡⅢⅣIViv一二三四1234][ABCabc]?期|晚期|早期|中期|转移|分期',
        multiple=r'[，,、/；;\n]|伴|合并|并发|及|和', colloquial=r'不知道|不清楚|好像|检查|[?？]|没钱|肿块|占位')
    selected, selected_ids = [], set()
    def take(pool, maximum, stratum):
        added = 0
        for item in pool:
            number = item['case']['source_row']
            if number in selected_ids:
                continue
            selected_ids.add(number)
            selected.append(dict(item, selected_stratum=stratum))
            added += 1
            if added >= maximum:
                break
    for label, maximum in [('uncertainty', 4), ('negation_or_nonprefix', 13), ('stage', 8), ('multiple', 10)]:
        pool = [r for r in eligible if re.search(patterns[label], r['text'])]
        pool.sort(key=lambda r: (-len(r['text']), r['case']['source_row']))
        take(pool, maximum, label)
    take(sorted([r for r in eligible if len(r['text']) > 30], key=lambda r: -len(r['text'])), 8, 'long_field')
    take([r for r in eligible if re.search(patterns['colloquial'], r['text'])], 6, 'colloquial')
    remaining = [r for r in eligible if r['case']['source_row'] not in selected_ids]
    random.Random(20261017).shuffle(remaining)
    take(remaining, 60 - len(selected), 'seeded_breadth')
    assert len(selected) == 60
    for index, item in enumerate(selected, 1):
        item['review_id'] = f'R{index:03d}'
    write(PRIVATE / 'real-cards.json', selected)
    synthetic = []
    for batch in ('expanded-20261017', 'currency-wording-20261017'):
        profile = json.loads((ROOT / f'agent/verification/{batch}/preparation.json').read_bytes())
        raw = (ROOT / profile['suite_file']).read_bytes()
        assert sha(raw) == profile['suite_sha256']
        suite = json.loads(raw)
        cases = suite['cases']
        summary = json.loads((ROOT / f'agent/verification/{batch}/summary.json').read_bytes())
        saved = {c['case_id']: c for c in summary['cases']}
        for case in cases:
            if case.get('data_class') != 'synthetic':
                continue
            record = saved[case['case_id']]
            response_raw = (ROOT / record['response_file']).read_bytes()
            assert sha(response_raw) == record['response_sha256']
            response = json.loads(response_raw)
            getattr(AgentService(lambda op, req: response), case['operation'])(case['request'])
            synthetic.append(dict(review_id=f'S{len(synthetic)+1:03d}', batch=batch,
                case=case, record=record, response=response))
    assert len(synthetic) == 27
    write(PRIVATE / 'synthetic-cards.json', synthetic)
    write(HERE / 'selection.json', dict(recorded_at=snapshot['updated_at'], model_generations=0,
        bulk_snapshot=snapshot, real_review_cases=60, synthetic_review_cases=len(synthetic),
        eligible_distinct_saved_fields=len(eligible), sample_method='Purposive risk strata plus seeded breadth; not a random population accuracy sample.',
        strata=dict(Counter(r['selected_stratum'] for r in selected)),
        real_input_categories=dict(Counter(r['case']['category'] for r in selected)),
        private_review_cards_sha256=dict(real=sha((PRIVATE / 'real-cards.json').read_bytes()),
            synthetic=sha((PRIVATE / 'synthetic-cards.json').read_bytes())),
        review_type='Assistant source/output comparison, not independent clinical expert annotation.',
        raw_patient_text_in_public_report=False))
    print(json.dumps(dict(real=60, synthetic=len(synthetic), strata=dict(Counter(r['selected_stratum'] for r in selected))), ensure_ascii=True))


if __name__ == '__main__':
    main()
