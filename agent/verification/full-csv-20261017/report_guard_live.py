"""Sanitized segment evidence; never changes attempts or calls a provider."""
from collections import Counter
from datetime import datetime, timezone
import json
import sqlite3

from prepare import HERE, ROOT, PRIVATE, sha
import billing_checkpoint


def main():
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri()+'?mode=ro', uri=True)
    db.execute('BEGIN')
    records = []
    for state, raw in db.execute('SELECT status,record FROM attempts ORDER BY source_row'):
        record = json.loads(raw)
        record.setdefault('status', state)
        records.append(record)
    progress = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    total_charge = db.execute('SELECT COALESCE(SUM(charge),0) FROM attempts').fetchone()[0]
    budget_control = billing_checkpoint.report(db, total_charge)
    db.close()
    current = [r for r in records if r.get('publication_basis',{}).get('epoch')=='question-format-guard-v1-user-reported']
    verified = [r for r in current if r.get('question_format_version')]
    for record in current:
        for file_key,hash_key in (('response_file','response_sha256'),('wire_response_file','wire_response_sha256')):
            if record.get(file_key):
                assert sha((ROOT/record[file_key]).read_bytes()) == record[hash_key]
    failures = [{k:r.get(k) for k in ('source_row','status','error','error_type','failures','review_flags','total_tokens')}
                for r in current if r['status'] not in ('partial_checks_passed','calling_or_unknown')]
    export = HERE / 'verified-question-guard-export.json'
    export_verified = export.exists()
    report = dict(updated_at=datetime.now(timezone.utc).isoformat(), runner_status=progress['status'],
        publication_basis=('user_reported_publication_saved_export_verified_later' if export_verified
                           else 'user_reported_fresh_editor_export_not_yet_available'),
        saved_configuration_export_verified=export_verified,
        export_verification_file=export.relative_to(ROOT).as_posix() if export_verified else None,
        claims_recorded_after_export_verification=sum(
            r.get('publication_basis',{}).get('saved_configuration_verified_by_export') is True for r in current),
        new_calls_attempted=len(current), source_rows=[r['source_row'] for r in current],
        counts=dict(Counter(r['status'] for r in current)),
        response_provenance_verified=len(verified),
        raw_model_contract_valid=sum(r.get('raw_model_contract_valid') is True for r in verified),
        raw_model_contract_invalid=sum(r.get('raw_model_contract_valid') is False for r in verified),
        policy_applied_calls=sum(bool(r.get('question_policy_inserted_false_paths')) for r in verified),
        inserted_optional_false_flags=sum(len(r.get('question_policy_inserted_false_paths',[])) for r in verified),
        failures=failures, cumulative_calls=len(records),
        cumulative_counts=dict(Counter(r['status'] for r in records)), cumulative_cost_upper_bound_cny=total_charge/1e6,
        historical_failed_rows_retained=[r['source_row'] for r in records if r['source_row']<=85 and r['status']!='partial_checks_passed'],
        failed_rows_retried=False, actual_bill_read=False, external_calls_by_report=0,
        limits='Response provenance verifies returned raw text/result/policy report, not every editor setting. Full medical semantics not independently annotated. Policy-processed responses do not prove raw model output correct.')
    if budget_control is not None:
        report['budget_control'] = budget_control
    (HERE/'question-guard-live.json').write_bytes((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report,ensure_ascii=True))


if __name__=='__main__':
    main()
