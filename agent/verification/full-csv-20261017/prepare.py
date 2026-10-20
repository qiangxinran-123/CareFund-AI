"""Offline whole-file inventory. Never sends data or treats a projection as a model run."""
from collections import Counter
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import statistics

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIVATE = ROOT / 'agent/.local/full-csv-20261017'
SOURCE = Path('C:/Users/zxw01/Downloads/data_final(1).csv')
EXPECTED_SHA = 'fbcd57439ad7c1b02ae34078990c4042a7e3193977e49bb0a9b5e93bac5b2cc2'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    if (HERE / 'preparation.json').exists() or PRIVATE.exists():
        raise SystemExit('Existing inventory will not be overwritten.')
    raw = SOURCE.read_bytes()
    if sha(raw) != EXPECTED_SHA:
        raise SystemExit('Source fingerprint changed; review the new source first.')
    spec = importlib.util.spec_from_file_location('prior_csv_prepare', HERE.parent / 'csv-final-20261017/prepare.py')
    prior = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(prior)
    counts, values, safe_values, markers = Counter(), Counter(), Counter(), Counter()
    PRIVATE.mkdir(parents=True)
    mapping = PRIVATE / 'row-index.jsonl'
    with SOURCE.open(encoding='utf-8-sig', newline='') as stream, mapping.open('x', encoding='utf-8', newline='\n') as out:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        for number, row in enumerate(reader, 1):
            counts['rows'] += 1
            if None in row or any(v is None for v in row.values()):
                raise SystemExit('Malformed CSV row; no external suite approved.')
            text = row['patient_disease'].strip()
            if text.lower() in prior.MISSING:
                text = ''
            values[text] += 1
            projected = prior.projection(text) if text else None
            category = 'empty' if not text else 'strict_minimal_disease' if projected else 'unreviewed_free_text'
            counts[category] += 1
            if projected:
                safe_values[projected[0]] += 1
            if re.search(r'https?://|www\.|[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', text):
                markers['url_or_email_rows'] += 1
            if re.search(r'(?<!\d)(?:1[3-9]\d{9}|\d{17}[\dXx])(?!\d)', text):
                markers['phone_or_identity_number_pattern_rows'] += 1
            if any(row[name].strip() and row[name].strip().lower() not in prior.MISSING
                   and len(row[name].strip()) >= 2 and row[name].strip() in text
                   for name in ('patient_name', 'publisher_name')):
                markers['source_name_exact_overlap_rows'] += 1
            record = {'source_row': number, 'disease_cell_sha256': sha(text.encode()), 'category': category}
            if projected:
                record['minimal_phrase_sha256'] = sha(projected[0].encode())
            out.write(json.dumps(record, ensure_ascii=False) + '\n')
    old = json.loads((HERE.parent / 'expanded-20261017/summary.json').read_text(encoding='utf-8'))
    sample = [r for r in old['cases'] if r['data_class'] == 'minimal_anonymous_chinese_disease_cell']
    durations = [r['elapsed_seconds'] for r in sample]
    tokens = [r['dify_usage_metadata']['total_tokens'] for r in sample]
    nonempty_unique = len(values) - int('' in values)
    profile = {
        'source_file': SOURCE.name, 'source_sha256': EXPECTED_SHA, 'source_bytes': len(raw),
        'counts': dict(counts), 'distinct_nonempty_disease_cells': nonempty_unique,
        'distinct_strict_minimal_phrases': len(safe_values),
        'strict_minimal_row_coverage': sum(safe_values.values()),
        'unreviewed_distinct_disease_cells': sum(1 for v in values if v and not prior.projection(v)),
        'local_privacy_pattern_flags': dict(markers),
        'row_index_sha256': sha(mapping.read_bytes()),
        'historical_chinese_sample_size': len(sample),
        'historical_chinese_mean_seconds': statistics.mean(durations),
        'historical_chinese_mean_total_tokens': statistics.mean(tokens),
        'independent_nonempty_row_calls': counts['rows'] - counts['empty'],
        'independent_including_empty_calls': counts['rows'],
        'independent_row_serial_days_estimate': statistics.mean(durations) * counts['rows'] / 86400,
        'independent_row_total_tokens_estimate': round(statistics.mean(tokens) * counts['rows']),
        'nonempty_deduplicated_calls': nonempty_unique,
        'deduplicated_nonempty_serial_hours_estimate': statistics.mean(durations) * nonempty_unique / 3600,
        'columns_excluded_from_model_inputs': [c for c in columns if c != 'patient_disease'],
        'privacy_gate': 'Only the prior strict whole-cell grammar is currently reviewed for external sending; other text remains local.',
        'planned_model_calls_approved_by_this_script': 0, 'actual_model_calls': 0,
        'provider_rates_checked_2026_10_17': {
            'source': 'https://api-docs.deepseek.com/zh-cn/quick_start/pricing/',
            'unit': 'CNY per million tokens', 'model': 'deepseek-flash',
            'off_peak': {'input_cache_hit': 0.02, 'input_cache_miss': 1, 'output': 4},
            'peak': {'input_cache_hit': 0.04, 'input_cache_miss': 2, 'output': 8}},
        'limits': [
            'Timing and token extrapolations are planning estimates, not actual usage or a quote.',
            'Stored total-token metadata does not identify input/output/cache mix; exact cost cannot be derived.',
            'Identity columns are excluded, but disease free text can itself contain identity details.',
            'Local privacy patterns are incomplete; a lack of flags is not proof of deidentification.',
            'Deduplicated reuse is not an independent model execution on every source row.',
            'No dataset-wide semantic labels or ground truth have been established.']}
    (HERE / 'preparation.json').write_bytes((json.dumps(profile, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(profile, ensure_ascii=False))


if __name__ == '__main__':
    main()
