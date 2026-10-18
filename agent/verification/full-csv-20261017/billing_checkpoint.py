"""User-reported bill baseline plus conservative reservations for future calls.

Never replaces historical charges or represents a user report as a platform read.
"""
import hashlib
import json

from prepare import ROOT, HERE

LIMIT = 20_000_000
VERSION = 'user-reported-bill-plus-new-reservations-v1'


def fingerprint(rows):
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def baseline_rows(db, last_row):
    return db.execute('SELECT source_row,status,reservation,charge,record FROM attempts '
                      'WHERE source_row<=? ORDER BY source_row', (last_row,)).fetchall()


def load(db):
    pointer = db.execute("SELECT value FROM meta WHERE key='billing_checkpoint'").fetchone()
    if not pointer:
        return LIMIT, None
    pointer = json.loads(pointer[0])
    path = (ROOT / pointer['file']).resolve()
    if path.parent != HERE.resolve():
        raise ValueError('Billing checkpoint is outside the report directory.')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pointer['sha256']:
        raise ValueError('Billing checkpoint evidence changed.')
    checkpoint = json.loads(raw)
    if (checkpoint.get('version') != VERSION or checkpoint.get('actual_spend_limit_micro_cny') != LIMIT
            or checkpoint.get('source') != 'explicit_user_report'
            or checkpoint.get('platform_bill_machine_verified') is not False):
        raise ValueError('Billing checkpoint policy does not match authorization.')
    for key in ('reported_spent_micro_cny', 'baseline_calls', 'baseline_last_source_row',
                'baseline_ledger_charge_micro_cny', 'prior_unknown_usage_reserve_micro_cny'):
        if type(checkpoint.get(key)) is not int or checkpoint[key] < 0:
            raise ValueError('Invalid billing checkpoint amount or count.')
    if checkpoint['reported_spent_micro_cny'] >= LIMIT or checkpoint['baseline_calls'] < 1:
        raise ValueError('No authorized bill headroom remains.')
    authorization = db.execute("SELECT value FROM meta WHERE key='authorization'").fetchone()
    if (not authorization or hashlib.sha256(authorization[0].encode()).hexdigest()
            != checkpoint['authorization_sha256']):
        raise ValueError('Original authorization changed after the bill checkpoint.')
    original = json.loads(authorization[0])
    if original['budget_micro_cny'] != LIMIT or original['max_calls'] != 84712:
        raise ValueError('Original budget or call cap changed.')
    rows = baseline_rows(db, checkpoint['baseline_last_source_row'])
    unknown_reserve = sum(r[3] for r in rows if json.loads(r[4]).get('total_tokens') is None)
    if (len(rows) != checkpoint['baseline_calls'] or fingerprint(rows) != checkpoint['baseline_records_sha256']
            or sum(r[3] for r in rows) != checkpoint['baseline_ledger_charge_micro_cny']
            or unknown_reserve != checkpoint['prior_unknown_usage_reserve_micro_cny']
            or any(r[1] == 'calling_or_unknown' for r in rows)):
        raise ValueError('Historical attempts changed after the bill checkpoint.')
    additional_allowance = LIMIT - checkpoint['reported_spent_micro_cny'] - unknown_reserve
    if additional_allowance <= 0:
        raise ValueError('No headroom after preserving unknown prior usage.')
    # This is a ledger-index threshold, not a higher authorized actual spending cap.
    ledger_ceiling = checkpoint['baseline_ledger_charge_micro_cny'] + additional_allowance
    return ledger_ceiling, checkpoint


def report(db, charge=None):
    _, checkpoint = load(db)
    if checkpoint is None:
        return None
    if charge is None:
        charge = db.execute('SELECT COALESCE(SUM(charge),0) FROM attempts').fetchone()[0]
    additional = charge - checkpoint['baseline_ledger_charge_micro_cny']
    if additional < 0:
        raise ValueError('Historical cost ledger was reduced.')
    controlled = (checkpoint['reported_spent_micro_cny']
                  + checkpoint['prior_unknown_usage_reserve_micro_cny'] + additional)
    return dict(mode=VERSION, actual_spend_limit_cny=LIMIT / 1e6,
        user_reported_spend_at_checkpoint_cny=checkpoint['reported_spent_micro_cny'] / 1e6,
        checkpoint_calls=checkpoint['baseline_calls'], checkpoint_time=checkpoint['recorded_at'],
        prior_unknown_usage_allowance_cny=checkpoint['prior_unknown_usage_reserve_micro_cny'] / 1e6,
        new_calls_cost_upper_bound_cny=additional / 1e6,
        controlled_spend_upper_bound_cny=controlled / 1e6,
        remaining_headroom_cny=(LIMIT - controlled) / 1e6,
        historical_cost_estimates_preserved=True, actual_platform_bill_read=False,
        caveat='Depends on the user-reported bill baseline and pinned rates; not a provider spending limit.')
