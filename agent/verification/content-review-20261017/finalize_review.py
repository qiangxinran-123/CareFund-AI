"""Publish deidentified judgments and ONLY fictional replay payloads. Offline."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from agent.agent_service import AgentService
from review_notes import (REAL_NOTES, SYNTHETIC_NOTES, WARNING_ALTERNATIVES,
    WARNING_RELATION, QUESTION_PRIORITY, QUESTION_EMPTY, SYNTHETIC_FLAGS)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def write(name, value):
    with (HERE / name).open('xb') as stream:
        stream.write((json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def main():
    selection = json.loads((HERE / 'selection.json').read_bytes())
    cards = {}
    for kind in ('real', 'synthetic'):
        raw = (ROOT / f'agent/.local/content-review-20261017/{kind}-cards.json').read_bytes()
        assert digest(raw) == selection['private_review_cards_sha256'][kind]
        cards[kind] = json.loads(raw)
    assert set(REAL_NOTES) == {r['review_id'] for r in cards['real']}
    assert set(SYNTHETIC_NOTES) == {r['review_id'] for r in cards['synthetic']}
    judgments, synthetic = [], []
    for r in cards['real']:
        rid = r['review_id']
        # Recheck original immutable saved bytes; do not publish them.
        original = (ROOT / r['record']['response_file']).read_bytes()
        assert digest(original) == r['record']['response_sha256']
        assert json.loads(original) == r['response']
        AgentService(lambda op, req: r['response']).extract(r['case']['request'])
        facts = r['response']['candidate_facts']
        assert all(f['source_type'] == 'user_input' and not f['evidence_ids']
                   and f['verification_status'] == 'pending' and f['user_confirmed'] is False
                   for f in facts)
        flags = []
        for group, flag in [(WARNING_ALTERNATIVES, 'warning_suggests_unsupplied_spelling'),
                            (WARNING_RELATION, 'warning_speculates_unsupplied_medical_relation'),
                            (QUESTION_PRIORITY, 'ambiguity_not_prioritized_in_questions'),
                            (QUESTION_EMPTY, 'missing_information_without_followup')]:
            if rid in group:
                flags.append(flag)
        if rid in QUESTION_EMPTY:
            assert not r['response']['questions']
        judgments.append(dict(review_id=rid, data_class='real_minimized_private_source',
            stratum=r['selected_stratum'], input_sha256=r['case']['sanitized_text_sha256'],
            response_sha256=digest(original), fact_comparison='no_added_or_omitted_components_observed',
            source_and_status_boundary='passed', findings=flags, note=REAL_NOTES[rid]))
    for r in cards['synthetic']:
        rid, case = r['review_id'], r['case']
        assert case['data_class'] == 'synthetic'
        raw = (ROOT / r['record']['response_file']).read_bytes()
        assert digest(raw) == r['record']['response_sha256'] and json.loads(raw) == r['response']
        getattr(AgentService(lambda op, req: r['response']), case['operation'])(case['request'])
        judgments.append(dict(review_id=rid, data_class='synthetic', operation=case['operation'],
            source_batch=r['batch'], case_id=case['case_id'],
            fact_comparison='no_added_or_omitted_components_observed',
            source_and_status_boundary='passed', findings=SYNTHETIC_FLAGS.get(rid, []),
            note=SYNTHETIC_NOTES[rid]))
        synthetic.append(dict(review_id=rid, case=case, response=r['response'],
            original_saved_response_sha256=digest(raw), source_batch=r['batch'],
            payload_sha256=digest(canonical({'case': case, 'response': r['response']}))))
    counts = Counter(f for j in judgments for f in j['findings'])
    report = dict(reviewed_at=datetime.now(timezone.utc).isoformat(),
        reviewer='Codex assistant source/output comparison; not human or clinical expert annotation',
        real_cases=60, synthetic_extract_cases=21, synthetic_draft_cases=6,
        real_cases_with_findings=sum(bool(j['findings']) for j in judgments[:60]),
        synthetic_cases_with_findings=sum(bool(j['findings']) for j in judgments[60:]),
        fact_content='No added or omitted components observed in these selected 87 saved outputs; not a medical accuracy estimate.',
        findings_by_category=dict(counts), all_findings_fixed=False,
        prompt_candidate_published=False, prompt_candidate_live_tests=0,
        model_generations_by_review=0, original_batch_results_changed=False,
        real_patient_payloads_shared=False, judgments=judgments,
        limits=['Purposive selection of available successful/reviewed responses excludes transport failures.',
                'Bulk runs span multiple prompt publications; this is not one-version validation.',
                'Original source truth, OCR, user confirmation, B/D transactions and final export not validated.',
                'S018 remains historical; S022 is its later same-request currency regression.',
                'Draft literal preservation can quote unwanted source instructions; publication requires review.'])
    write('review-results.json', report)
    write('synthetic-replay.json', dict(data_class='synthetic_only', new_model_generations=0,
        description='Historical saved Dify outputs across two batches, not fresh inference or one-version semantic acceptance.',
        cases=synthetic))
    print(json.dumps({k: report[k] for k in ('real_cases', 'synthetic_extract_cases',
        'synthetic_draft_cases', 'real_cases_with_findings', 'synthetic_cases_with_findings',
        'findings_by_category', 'model_generations_by_review')}))


if __name__ == '__main__':
    main()
