"""Prepare all CSV disease cells locally; retain a private redaction/review ledger.

This is preparation only. No credentials, network calls, or upload authorization.
"""
from collections import Counter
import csv
import importlib.util
import json
from pathlib import Path
import re

from prepare import HERE, ROOT, PRIVATE, SOURCE, EXPECTED_SHA, sha

DIRECT_FIELDS = ('patient_name', 'publisher_name', 'patient_city', 'patient_province',
                 'projuuid', 'uuid', 'patient_birth_date', 'created_time')
PATTERNS = (
    ('url', re.compile(r'https?://[^\s，。；、]+|www\.[^\s，。；、]+', re.I)),
    ('email', re.compile(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}')),
    ('phone_or_id', re.compile(r'(?<!\d)(?:1[3-9]\d{9}|\d{17}[\dXx])(?!\d)')),
    ('calendar_date', re.compile(r'(?:19|20)\d{2}(?:年\d{1,2}月(?:\d{1,2}日)?|[-/]\d{1,2}[-/]\d{1,2})')),
)
# Conservative local hold only; false positives must be reviewed, never silently dropped.
REVIEW = re.compile(r'医院|卫生院|学校|大学|住址|地址|姓名|联系人|电话|手机|微信|身份证|住在|家住|[省市县区][^，。；]{0,6}[路街村镇]|\d{7,}|https?://|@')
MISSING = {'', 'nan', 'none', 'null', 'na', 'n/a', '-'}


def clean(row):
    original = row['patient_disease'].strip()
    if original.lower() in MISSING:
        return '', [], []
    text, redactions = original, []
    # Exact source-linked removal only; no inference of medical facts or labels.
    identifiers = sorted({row[f].strip() for f in DIRECT_FIELDS
                          if row.get(f, '').strip().lower() not in MISSING
                          and len(row[f].strip()) >= 2}, key=len, reverse=True)
    for identifier in identifiers:
        if identifier in text:
            text = text.replace(identifier, '[身份信息已移除]')
            redactions.append('source_linked_identifier')
    for label, pattern in PATTERNS:
        text, count = pattern.subn('[身份信息已移除]', text)
        redactions.extend([label] * count)
    flags = []
    if redactions:
        flags.append('redacted_cell_requires_local_review')
    if REVIEW.search(text):
        flags.append('possible_residual_identifier_requires_local_review')
    return text, sorted(set(redactions)), flags


def request(row_number, text):
    description = ('以下是数据表中的疾病字段，仅作为未核验、待确认的用户陈述。'
                   '方括号中的身份信息移除标记不包含医疗事实。字段原文：' + text + '。其他信息未提供。')
    return {'schema_version': '1.0', 'application_id': f'app_fullcsv_{row_number:06d}',
            'application_revision': 1, 'user_input': {'description': description} if text else {},
            'extracted_documents': [], 'candidate_facts': []}


def main():
    target = PRIVATE / 'prepared-inputs.jsonl'
    if target.exists() or (HERE / 'input-preparation.json').exists():
        raise SystemExit('Prepared inputs already exist; do not overwrite evidence.')
    if sha(SOURCE.read_bytes()) != EXPECTED_SHA:
        raise SystemExit('Source changed.')
    spec = importlib.util.spec_from_file_location('strict_csv_projection', HERE.parent / 'csv-final-20261017/prepare.py')
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    import sys
    sys.path.insert(0, str(ROOT))
    from agent.agent_service import AgentService
    from jsonschema import Draft202012Validator, FormatChecker
    service = AgentService(None)
    validator = Draft202012Validator(dict(service.schema, **{'$ref': '#/$defs/AgentExtractRequest'}),
                                   registry=service.registry, format_checker=FormatChecker())
    counts, review_flags, hashes = Counter(), Counter(), set()
    with SOURCE.open(encoding='utf-8-sig', newline='') as stream, target.open('x', encoding='utf-8', newline='\n') as out:
        for number, row in enumerate(csv.DictReader(stream), 1):
            text, redactions, flags = clean(row)
            req = request(number, text)
            if not validator.is_valid(req):
                flags.append('request_schema_rejected')
            projection = prior.projection(text) if text else None
            category = 'held_for_local_review' if flags else 'empty' if not text else 'strict_minimal' if projection else 'sanitized_free_text'
            counts[category] += 1
            review_flags.update(flags)
            digest = sha(text.encode())
            hashes.add(digest)
            record = {'source_row': number, 'case_id': f'fullcsv_{number:06d}',
                      'category': category, 'redactions': redactions, 'review_flags': flags,
                      'sanitized_text_sha256': digest, 'request': req,
                      'expectation': prior.expectation_for(projection[1]) if projection else {}}
            out.write(json.dumps(record, ensure_ascii=False) + '\n')
    report = {'source_sha256': EXPECTED_SHA, 'rows': sum(counts.values()),
              'categories': dict(counts), 'review_flags': dict(review_flags),
              'distinct_sanitized_texts_including_empty': len(hashes),
              'private_input_file': target.relative_to(ROOT).as_posix(),
              'private_input_file_sha256': sha(target.read_bytes()),
              'external_model_calls': 0,
              'external_send_status': 'Not started. Awaiting mode/budget decision; held cases require local review.',
              'limits': ['Deterministic cleanup is not proof that every identifier has been removed.',
                         'Free text has no complete semantic ground truth; partial checks cannot establish accuracy.',
                         'Held rows remain in the complete index and are not counted as model-tested.']}
    (HERE / 'input-preparation.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
