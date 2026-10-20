"""Supplemental lexical review of saved outputs; zero model calls, no accuracy claim."""
import argparse
from collections import Counter
import importlib.util
import json
import re
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha

spec = importlib.util.spec_from_file_location('csv_review_vocabulary', HERE.parent / 'csv-final-20261017/prepare.py')
VOCAB = importlib.util.module_from_spec(spec)
spec.loader.exec_module(VOCAB)

ALIASES = {
    '食道癌': ('食道癌', '食管癌'), '食管癌': ('食道癌', '食管癌'),
    '脑梗塞': ('脑梗塞', '脑梗死'), '脑梗死': ('脑梗塞', '脑梗死'),
    '急性髓性白血病': ('急性髓性白血病', '急性髓系白血病'),
    '急性髓系白血病': ('急性髓性白血病', '急性髓系白血病'),
}
STAGE_NUMBER = {'一': '1', '二': '2', '三': '3', '四': '4', 'Ⅰ': '1', 'Ⅱ': '2', 'Ⅲ': '3', 'Ⅳ': '4',
                'I': '1', 'II': '2', 'III': '3', 'IV': '4'}


def normalize(text):
    value = re.sub(r'\s+', '', text).lower()
    for token, number in sorted(STAGE_NUMBER.items(), key=lambda item: len(item[0]), reverse=True):
        value = value.replace(token.lower() + '期', number + '期')
    return value


def review(source, result):
    medical = ' '.join(str(f['value']['value']) for f in result.get('candidate_facts', [])
                       if f.get('field') == 'patient.medical_summary')
    normalized = normalize(medical)
    flags = []
    for disease in VOCAB.DISEASES:
        if disease in source and not any(normalize(alias) in normalized for alias in ALIASES.get(disease, (disease,))):
            flags.append('source_disease_keyword_needs_context_review')
    for marker in ('疑似', '未确诊', '尚未确诊', '排除'):
        if marker in source and marker not in medical:
            flags.append('uncertainty_or_negation_wording_needs_context_review')
    for stage in re.finditer(VOCAB.STAGE, source):
        if normalize(stage[0]) not in normalized:
            flags.append('source_stage_keyword_needs_context_review')
    return sorted(set(flags))


def main(stop_on_finding=False):
    inputs = json.loads((HERE / 'input-preparation.json').read_bytes())
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    rows = {row: json.loads(record) for row, record in db.execute(
        "SELECT source_row,record FROM attempts WHERE status NOT IN ('calling_or_unknown')")}
    db.close()
    findings, counts = [], Counter()
    with (ROOT / inputs['private_input_file']).open(encoding='utf-8') as stream:
        for line in stream:
            case = json.loads(line)
            attempt = rows.get(case['source_row'])
            if not attempt or not attempt.get('response_file'):
                continue
            raw = (ROOT / attempt['response_file']).read_bytes()
            if sha(raw) != attempt['response_sha256']:
                raise SystemExit('Response changed.')
            result = json.loads(raw)
            text = case['request']['user_input'].get('description', '')
            source = text.split('字段原文：', 1)[1].removesuffix('。其他信息未提供。') if text else ''
            flags = review(source, result)
            counts['saved_responses_checked'] += 1
            if flags:
                counts['responses_flagged_for_context_review'] += 1
                findings.append({'case_id': case['case_id'], 'source_row': case['source_row'],
                                 'response_sha256': attempt['response_sha256'], 'review_flags': flags})
    report = {'kind': 'supplemental_lexical_review', 'counts': dict(counts), 'findings': findings,
              'external_calls': 0, 'limits': 'Keyword matches can flag aliases or different phrasing; inspect context before deciding correctness.'}
    (HERE / 'lexical-review.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    if findings and stop_on_finding:
        (PRIVATE / 'STOP').touch(exist_ok=True)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--stop-on-finding', action='store_true')
    args = parser.parse_args()
    main(args.stop_on_finding)
