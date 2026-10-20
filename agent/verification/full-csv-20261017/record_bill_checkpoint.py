"""Record the user's CNY1.92 bill observation without resetting any history."""
from datetime import datetime, timezone
import json
import sqlite3

import billing_checkpoint as billing
from prepare import HERE, ROOT, PRIVATE, sha
from run_live import resume_review, CURRENT_EXPORT, CURRENT_EXPORT_SHA


def main():
    assert sha(CURRENT_EXPORT.read_bytes()) == CURRENT_EXPORT_SHA
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    db.execute('BEGIN IMMEDIATE')
    assert not db.execute("SELECT value FROM meta WHERE key='billing_checkpoint'").fetchone()
    authorization = db.execute("SELECT value FROM meta WHERE key='authorization'").fetchone()[0]
    original = json.loads(authorization)
    assert original['budget_micro_cny'] == 20_000_000 and original['max_calls'] == 84712
    progress = json.loads(db.execute("SELECT value FROM meta WHERE key='last_progress'").fetchone()[0])
    assert progress['status'] == 'paused_before_budget_or_call_limit'
    rows = billing.baseline_rows(db, 1011)
    assert len(rows) == 1009 and rows[-1][0] == 1011
    assert db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0] == len(rows)
    assert not any(r[1] == 'calling_or_unknown' for r in rows)
    before = billing.fingerprint(rows)
    evidence = dict(version=billing.VERSION, recorded_at=datetime.now(timezone.utc).isoformat(),
        source='explicit_user_report', user_statement='才花费1.92人民币，继续',
        platform_bill_machine_verified=False, reported_spent_micro_cny=1_920_000,
        actual_spend_limit_micro_cny=20_000_000, authorization_sha256=sha(authorization.encode()),
        baseline_calls=len(rows), baseline_last_source_row=1011,
        baseline_ledger_charge_micro_cny=sum(r[3] for r in rows), baseline_records_sha256=before,
        prior_unknown_usage_reserve_micro_cny=sum(r[3] for r in rows if json.loads(r[4]).get('total_tokens') is None),
        original_authorization_unchanged=True, aggregate_call_cap_unchanged=True,
        historical_attempts_and_costs_unchanged=True, failed_rows_retried=False,
        scope='Only continue unattempted approved rows. Future calls retain highest-rate reservations. '
              'Prior unknown attempts retain extra full allowances; no scaling by an empirical price ratio.',
        pricing_source='https://api-docs.deepseek.com/zh-cn/quick_start/pricing/', pricing_checked='2026-10-17')
    path = HERE / 'billing-checkpoint-001.json'
    encoded = (json.dumps(evidence, ensure_ascii=False, indent=2) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(encoded)
    db.execute("INSERT INTO meta VALUES ('billing_checkpoint',?)", (json.dumps(dict(
        file=path.relative_to(ROOT).as_posix(), sha256=sha(encoded))),))
    ceiling, _ = billing.load(db)
    assert ceiling > sum(r[3] for r in rows)
    resume_review(db)
    assert billing.fingerprint(billing.baseline_rows(db, 1011)) == before
    assert db.execute("SELECT value FROM meta WHERE key='authorization'").fetchone()[0] == authorization
    report = billing.report(db)
    db.commit()
    db.close()
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
