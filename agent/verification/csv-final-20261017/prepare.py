"""Local-only profiling/adaptation of the user-supplied Chinese CSV.

No network code. Identity/financial columns never enter prepared model inputs.
Only entire disease cells matching the small explicit grammar may be projected.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService
from agent.batch_check import semantic_checks
from jsonschema import Draft202012Validator, FormatChecker

DISEASES = (
    '急性淋巴细胞白血病', '急性髓系白血病', '急性髓性白血病', '急性早幼粒细胞白血病',
    '急性白血病', '慢性粒细胞白血病', '慢性淋巴细胞白血病', '白血病',
    '非霍奇金淋巴瘤', '霍奇金淋巴瘤', '淋巴瘤', '多发性骨髓瘤',
    '再生障碍性贫血', '重型再生障碍性贫血', '骨髓增生异常综合征',
    '肺腺癌', '小细胞肺癌', '非小细胞肺癌', '肺癌', '乳腺癌', '胃癌', '肝癌',
    '结肠癌', '直肠癌', '结直肠癌', '食管癌', '食道癌', '胰腺癌', '胆管癌',
    '宫颈癌', '卵巢癌', '子宫内膜癌', '鼻咽癌', '喉癌', '甲状腺癌', '肾癌',
    '膀胱癌', '前列腺癌', '骨肉瘤', '神经母细胞瘤', '脑肿瘤', '脑瘤', '胶质瘤',
    '尿毒症', '肾衰竭', '慢性肾功能衰竭', '慢性肾衰竭', '肾病综合征',
    '先天性心脏病', '冠心病', '心肌梗死', '心力衰竭', '扩张型心肌病',
    '脑出血', '脑梗死', '脑梗塞', '颅脑损伤', '重度颅脑损伤',
    '肝硬化', '肝衰竭', '重症肺炎', '肺炎', '重症胰腺炎', '急性胰腺炎',
    '系统性红斑狼疮', '红斑狼疮', '股骨头坏死', '烧伤', '重度烧伤',
)
STAGE = r'(?:[0-4一二三四ⅠⅡⅢⅣIV]{1,3}[ABCabc]?期|早期|中期|晚期|中晚期|终末期)'
GRAMMAR = re.compile(
    r'(?P<status>疑似|考虑|确诊|确诊为|已确诊|排除|尚未确诊|未确诊)?'
    r'(?P<disease>' + '|'.join(re.escape(s) for s in sorted(DISEASES, key=len, reverse=True)) + ')'
    r'(?P<stage>' + STAGE + r')?')
PREFIX = '以下是数据表中去身份化的疾病字段原文，仅作为待确认陈述，不代表诊断已核验。原文：'
SUFFIX = '。其余信息未提供。'
MISSING = {'', 'nan', 'none', 'null', 'na', 'n/a', '-'}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def request(index, text):
    return dict(schema_version='1.0', application_id=f'app_csv_final_{index:06d}',
                application_revision=1, user_input={'description': text} if text else {},
                extracted_documents=[], candidate_facts=[])


def projection(text):
    # Only whitespace is removed; no substring mining through a larger narrative.
    value = re.sub(r'\s+', '', text)
    match = GRAMMAR.fullmatch(value)
    return (value, match.groupdict()) if match else None


def expectation_for(parts):
    expected = {'medical_all_groups': [[parts['disease']]], 'no_medical_money': True,
                'no_date_value': True, 'input_source_only': True}
    if parts['stage']:
        expected['medical_all_groups'].append([parts['stage']])
    if parts['status'] in ('疑似', '考虑', '排除', '尚未确诊', '未确诊'):
        expected['medical_all_groups'].append([parts['status']])
    return expected


def prepare(source, output, public):
    if output.exists() or (public / 'preparation.json').exists():
        raise SystemExit('Preparation already exists; evidence will not be overwritten.')
    output.mkdir(parents=True)
    public.mkdir(parents=True, exist_ok=True)
    raw = source.read_bytes()
    source_hash = digest(raw)
    with source.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        required = {'patient_disease', 'disease_label', 'target_amount', 'raised_amount',
                    'patient_name', 'publisher_name', 'patient_birth_date', 'projuuid', 'uuid'}
        if not required <= set(columns or []):
            raise SystemExit('CSV does not match this adapter; no model suite prepared.')
        service = AgentService(None)
        schema = dict(service.schema, **{'$ref': '#/$defs/AgentExtractRequest'})
        validator = Draft202012Validator(schema, registry=service.registry, format_checker=FormatChecker())
        counts = Counter()
        missing = Counter()
        row_hashes, project_ids, user_ids = set(), set(), set()
        candidates = {}
        length_buckets = Counter()
        for row_number, row in enumerate(reader, start=1):
            counts['rows'] += 1
            if None in row or any(v is None for v in row.values()):
                counts['malformed_rows'] += 1
                continue
            row_hashes.add(digest(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()))
            project_ids.add(row['projuuid'])
            user_ids.add(row['uuid'])
            for field in columns:
                if row[field].strip().lower() in MISSING:
                    missing[field] += 1
            text = row['patient_disease'].strip()
            if text.lower() in MISSING:
                text = ''
            size = len(text)
            length_buckets['empty' if not size else '1_to_32' if size <= 32 else
                           '33_to_200' if size <= 200 else 'over_200'] += 1
            req = request(row_number, text)
            if validator.is_valid(req):
                counts['local_request_schema_passed'] += 1
            else:
                counts['local_request_schema_rejected'] += 1
            selected = projection(text) if text else None
            if selected:
                counts['dictionary_full_cell_matches'] += 1
                phrase, parts = selected
                candidates.setdefault(phrase, dict(phrase=phrase, parts=parts,
                    source_row=row_number, source_cell_sha256=digest(text.encode())))
        # Deterministic variety sampling by disease, then optional distinct forms.
        ranked = sorted(candidates.values(), key=lambda item: digest(item['phrase'].encode()))
        selected, used_diseases = [], set()
        for item in ranked:
            if item['parts']['disease'] not in used_diseases and len(selected) < 20:
                selected.append(item)
                used_diseases.add(item['parts']['disease'])
        for item in ranked:
            if len(selected) >= 20:
                break
            if item not in selected:
                selected.append(item)
        cases, provenance = [], []
        for i, item in enumerate(selected, start=1):
            case = dict(case_id=f'csv_disease_{i:03d}', operation='extract',
                data_class='minimal_anonymous_chinese_disease_cell', group='csv_dictionary_cell',
                request=request(i, PREFIX + item['phrase'] + SUFFIX),
                expectation=expectation_for(item['parts']))
            service.validate(case['request'], 'AgentExtractRequest')
            cases.append(case)
            provenance.append(dict(case_id=case['case_id'], **item))
        excluded = [k for k in columns if k != 'patient_disease']
        suite = dict(suite_version=1, source_file_sha256=source_hash,
            privacy='Only dictionary-matched whole disease cells; all other columns excluded.', cases=cases)
        suite_bytes = (json.dumps(suite, ensure_ascii=False, indent=2) + '\n').encode()
        (output / 'minimal-disease-cases.json').write_bytes(suite_bytes)
        (output / 'provenance-local-only.json').write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        profile = dict(source_file_name=source.name, source_bytes=len(raw), source_sha256=source_hash,
            encoding='utf-8-sig', columns=columns, counts=dict(counts), missing_by_column=dict(missing),
            exact_duplicate_rows=counts['rows']-len(row_hashes),
            duplicate_project_id_rows=counts['rows']-len(project_ids),
            duplicate_user_id_rows=counts['rows']-len(user_ids),
            disease_length_buckets=dict(length_buckets), dictionary_unique_cells=len(candidates),
            prepared_model_cases=len(cases), selected_distinct_disease_terms=len(used_diseases),
            excluded_model_columns=excluded,
            suite_file=(output/'minimal-disease-cases.json').relative_to(ROOT).as_posix(),
            suite_sha256=digest(suite_bytes), local_only_model_calls=0,
            source_and_license='User-supplied CSV; original publication/license not established.',
            limits=['All-row checks are request format checks, not AI extraction accuracy.',
                    'Disease labels are unverified source assertions, not clinical ground truth.',
                    'Dictionary sampling excludes free text and is not representative.',
                    'Target and raised fundraising amounts are not medical costs.',
                    'No raw identities, full CSV, financial metadata or long narratives sent by preparation.'])
        (public/'preparation.json').write_text(json.dumps(profile, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
        return profile


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=Path, required=True)
    args = parser.parse_args()
    # Fail-closed examples for the external-input projection gate.
    assert projection('白血病') and projection('疑似肺癌') and projection('肺癌Ⅲ期')
    for unsafe in ('张三白血病', '白血病电话13800000000', '肺癌，可能误诊',
                   '排除肺癌但确诊胃癌', '白血病西安市', '白血病筹款目标20000元'):
        assert projection(unsafe) is None
    result = prepare(args.csv, ROOT/'agent/.local/csv-final-20261017', Path(__file__).resolve().parent)
    print(json.dumps({k: result[k] for k in ('counts','prepared_model_cases',
                     'dictionary_unique_cells','selected_distinct_disease_terms','local_only_model_calls')}, ensure_ascii=False))
