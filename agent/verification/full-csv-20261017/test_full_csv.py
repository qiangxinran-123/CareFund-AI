"""Offline checks for privacy holds, durable claims, and budget accounting."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
import io
from unittest.mock import patch

import prepare_inputs as prep
import run_live as live
import report_guard_live as guard_report
import billing_checkpoint as billing


def row(text, **extra):
    return dict(patient_disease=text, **{k: extra.get(k, '') for k in prep.DIRECT_FIELDS})


def case(number=1):
    return {'case_id': f'fullcsv_{number:06d}', 'source_row': number,
            'category': 'strict_minimal', 'request': prep.request(number, '疑似肺癌')}


def bill_fixture(db, root, spent=1_920_000):
    rows = db.execute('SELECT source_row,status,reservation,charge,record FROM attempts ORDER BY source_row').fetchall()
    authorization = db.execute("SELECT value FROM meta WHERE key='authorization'").fetchone()[0]
    evidence = dict(version=billing.VERSION, actual_spend_limit_micro_cny=20_000_000,
        source='explicit_user_report', platform_bill_machine_verified=False, reported_spent_micro_cny=spent,
        baseline_calls=len(rows), baseline_last_source_row=rows[-1][0], recorded_at='test-checkpoint',
        baseline_ledger_charge_micro_cny=sum(r[3] for r in rows), baseline_records_sha256=billing.fingerprint(rows),
        authorization_sha256=live.sha(authorization.encode()),
        prior_unknown_usage_reserve_micro_cny=sum(r[3] for r in rows if json.loads(r[4]).get('total_tokens') is None))
    path = root / 'checkpoint.json'
    path.write_text(json.dumps(evidence), encoding='utf-8')
    with db:
        db.execute("INSERT INTO meta VALUES ('billing_checkpoint',?)", (json.dumps(dict(
            file='checkpoint.json', sha256=live.sha(path.read_bytes()))),))
    return evidence, path


class FullCSVTests(unittest.TestCase):
    def test_bill_checkpoint_keeps_historical_ledger_and_reserves_unknown_usage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db = live.connect(root / 'attempts.db')
            with db:
                db.execute("INSERT INTO meta VALUES ('authorization',?)", (json.dumps(dict(
                    budget_micro_cny=20_000_000, max_calls=84712)),))
            live.claim(db, case(), 20_000_000)
            live.settle(db, dict(source_row=1, status='boundary_or_transport_rejected', total_tokens=None))
            live.claim(db, case(2), 20_000_000)
            live.settle(db, dict(source_row=2, status='partial_checks_passed', total_tokens=2000))
            before = db.execute('SELECT * FROM attempts ORDER BY source_row').fetchall()
            checkpoint, path = bill_fixture(db, root)
            with patch.object(billing, 'ROOT', root), patch.object(billing, 'HERE', root):
                ceiling, _ = billing.load(db)
                self.assertEqual(ceiling, checkpoint['baseline_ledger_charge_micro_cny'] + 20_000_000
                    - 1_920_000 - live.reservation(case()['request']))
                report = billing.report(db)
                self.assertEqual(report['actual_spend_limit_cny'], 20)
                self.assertFalse(report['actual_platform_bill_read'])
                self.assertAlmostEqual(report['controlled_spend_upper_bound_cny'],
                    1.92 + live.reservation(case()['request']) / 1e6)
                # A new in-flight claim immediately consumes its full reservation.
                live.claim(db, case(3), ceiling)
                new_report = billing.report(db)
                self.assertAlmostEqual(new_report['new_calls_cost_upper_bound_cny'],
                    live.reservation(case(3)['request']) / 1e6)
                self.assertEqual(db.execute('SELECT * FROM attempts WHERE source_row<=2 ORDER BY source_row').fetchall(), before)
                with db:
                    db.execute('UPDATE attempts SET charge=0 WHERE source_row=1')
                with self.assertRaises(ValueError):
                    billing.load(db)
                path.write_text('{}', encoding='utf-8')
                with self.assertRaises(ValueError):
                    billing.load(db)
            db.close()

    def test_budget_resume_requires_checkpoint_and_still_refuses_unaffordable_next_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            db = live.connect(root / 'attempts.db')
            with db:
                db.execute("INSERT INTO meta VALUES ('authorization',?)", (json.dumps(dict(
                    budget_micro_cny=20_000_000, max_calls=84712)),))
                db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps(dict(
                    status='paused_before_budget_or_call_limit', started_at='original-start')),))
            (root / 'review-decisions.json').write_text('{}', encoding='utf-8')
            live.claim(db, case(), 20_000_000)
            live.settle(db, dict(source_row=1, status='partial_checks_passed', total_tokens=2000))
            with patch.object(live, 'PRIVATE', root), patch.object(billing, 'ROOT', root), patch.object(billing, 'HERE', root):
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
                bill_fixture(db, root, spent=19_990_000)
                self.assertEqual(live.resume_review(db), 'original-start')
                ceiling, _ = billing.load(db)
                self.assertFalse(live.claim(db, case(2), ceiling))
                self.assertEqual(db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone(), (1,16000))
            db.close()

    def test_read_only_timeout_recovery_requires_exact_request_and_keeps_ledger_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'private'
            private.mkdir()
            prepared = dict(case(), expectation={})
            (private / 'prepared-inputs.jsonl').write_text(json.dumps(prepared) + '\n', encoding='utf-8')
            db = live.connect(private / 'attempts.db')
            db.execute("INSERT INTO meta VALUES ('active_publication',?)", (json.dumps(dict(
                question_format_version=live.QUESTION_FORMAT_VERSION)),))
            db.commit()
            live.claim(db, prepared, 20_000_000)
            live.settle(db, dict(source_row=1, case_id=prepared['case_id'],
                status='boundary_or_transport_rejected', total_tokens=None,
                error='Dify network request failed or timed out; execution may still be running'))
            original = json.loads(db.execute('SELECT record FROM attempts').fetchone()[0])
            before = db.execute('SELECT status,charge,reservation,record FROM attempts').fetchone()
            response = {k: prepared['request'][k] for k in ('schema_version', 'application_id', 'application_revision')}
            response.update(candidate_facts=[], questions=[], warnings=[])
            detail = dict(status='succeeded', total_tokens=2000,
                inputs=json.dumps(dict(request_json=json.dumps(prepared['request']))),
                outputs=live.question_format(json.dumps(response)))
            path = private / 'detail.json'
            evidence = dict(original_attempt=original,
                classification='exact_timeout_result_recovered_and_checked', detail_file='private/detail.json')
            decisions = {'1': dict(request_sha256=original['request_sha256'], retry_failed_row=False,
                disposition='recovered_exact_timeout_result_reviewed_no_retry_continue_new_rows',
                evidence_file='private/evidence.json')}
            evidence_path = private / 'evidence.json'
            def save_review():
                path.write_text(json.dumps(detail), encoding='utf-8')
                evidence['detail_sha256'] = live.sha(path.read_bytes())
                evidence_path.write_text(json.dumps(evidence), encoding='utf-8')
                decisions['1']['evidence_sha256'] = live.sha(evidence_path.read_bytes())
                (private / 'review-decisions.json').write_text(json.dumps(decisions), encoding='utf-8')
            save_review()
            db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps(dict(
                status='paused_on_finding_no_retry', started_at='original-start')),))
            db.commit()
            with patch.object(live, 'ROOT', root), patch.object(live, 'PRIVATE', private):
                self.assertEqual(live.resume_review(db), 'original-start')
                self.assertEqual(db.execute('SELECT status,charge,reservation,record FROM attempts').fetchone(), before)
                altered_request = dict(prepared['request'], application_id='app_fullcsv_000002')
                original_inputs = detail['inputs']
                detail['inputs'] = json.dumps(dict(request_json=json.dumps(altered_request)))
                save_review()
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
                detail['inputs'] = original_inputs
                detail['total_tokens'] = 100000
                save_review()
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
                detail['total_tokens'] = 2000
                detail['outputs'].pop('raw_result')
                save_review()
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
            db.close()

    def test_reviewed_negative_disclaimer_preserves_status_cost_and_rejects_other_claims(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'private'
            private.mkdir()
            db = live.connect(private / 'attempts.db')
            live.claim(db, case(), 20_000_000)
            warning = '相关追问仅为便于核对已有陈述，不代表平台要求或审核结论。'
            response = dict(schema_version='1.0', application_id='app_test', application_revision=1,
                            candidate_facts=[], questions=[], warnings=[warning])
            saved_response = private / 'response.json'
            saved_response.write_text(json.dumps(response), encoding='utf-8')
            live.settle(db, dict(source_row=1, case_id=case()['case_id'], status='needs_context_review',
                total_tokens=2475, failures=[], review_flags=['platform_reference_needs_context_review'],
                response_file='private/response.json', response_sha256=live.sha(saved_response.read_bytes())))
            original = json.loads(db.execute('SELECT record FROM attempts').fetchone()[0])
            before = db.execute('SELECT status,charge,record FROM attempts').fetchone()
            evidence = dict(original_attempt=original, classification='negated_platform_warning_false_positive',
                            warning_index=0, reviewed_warning=warning)
            evidence_path = private / 'review.json'
            decisions = {'1': dict(request_sha256=original['request_sha256'], retry_failed_row=False,
                disposition='reviewed_negated_platform_warning_keep_original_continue_new_rows',
                evidence_file='private/review.json')}
            def save_review():
                evidence_path.write_text(json.dumps(evidence), encoding='utf-8')
                decisions['1']['evidence_sha256'] = live.sha(evidence_path.read_bytes())
                (private / 'review-decisions.json').write_text(json.dumps(decisions), encoding='utf-8')
            save_review()
            db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps(dict(
                status='paused_on_finding_no_retry', started_at='original-start')),))
            db.commit()
            with patch.object(live, 'ROOT', root), patch.object(live, 'PRIVATE', private):
                self.assertEqual(live.resume_review(db), 'original-start')
                self.assertEqual(db.execute('SELECT status,charge,record FROM attempts').fetchone(), before)
                evidence['original_attempt'] = dict(original, request_sha256='tampered')
                save_review()
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
                evidence['original_attempt'] = original
                # Even a rehashed review cannot suppress a separate positive platform claim.
                response['warnings'].append('平台要求必须提交材料。')
                saved_response.write_text(json.dumps(response), encoding='utf-8')
                changed_record = dict(original, response_sha256=live.sha(saved_response.read_bytes()))
                evidence['original_attempt'] = changed_record
                with self.assertRaises(live.AgentError):
                    live.validate_negated_warning_review(changed_record, evidence)
                saved_response.write_text('changed', encoding='utf-8')
                save_review()
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
            db.close()

    def test_guard_report_handles_inflight_claim_and_uses_same_ledger_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'private'
            private.mkdir()
            db = live.connect(private / 'attempts.sqlite3')
            with db:
                db.execute("INSERT INTO meta VALUES ('active_publication',?)", (json.dumps(
                    {'epoch': 'question-format-guard-v1-user-reported'}),))
            live.claim(db, case(), 20_000_000)
            live.settle(db, dict(source_row=1, case_id=case()['case_id'],
                                 status='partial_checks_passed', total_tokens=2000))
            # The progress metadata can precede the next durable claim.
            with db:
                db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps(
                    {'updated_at': 'test', 'status': 'running', 'calls_attempted': 1,
                     'counts': {'partial_checks_passed': 1}, 'cost_upper_bound_cny': 0.016}),))
            live.claim(db, case(2), 20_000_000)
            expected_charge = db.execute('SELECT SUM(charge) FROM attempts').fetchone()[0]
            db.close()
            with patch.object(guard_report, 'ROOT', root), patch.object(guard_report, 'PRIVATE', private), \
                    patch.object(guard_report, 'HERE', root), patch('sys.stdout', new=io.StringIO()):
                guard_report.main()
            result = json.loads((root / 'question-guard-live.json').read_bytes())
            self.assertEqual(result['cumulative_calls'], 2)
            self.assertEqual(result['cumulative_counts'], {'partial_checks_passed': 1, 'calling_or_unknown': 1})
            self.assertEqual(result['cumulative_cost_upper_bound_cny'], expected_charge / 1e6)
            self.assertEqual(result['new_calls_attempted'], 2)

    def test_identity_redaction_requires_hold_not_silent_upload(self):
        text, removed, flags = prep.clean(row('张小甲确诊肺癌，住在测试市', patient_name='张小甲', patient_city='测试市'))
        self.assertNotIn('张小甲', text)
        self.assertNotIn('测试市', text)
        self.assertIn('肺癌', text)
        self.assertTrue(removed)
        self.assertIn('redacted_cell_requires_local_review', flags)

    def test_novel_address_is_held_even_without_source_name(self):
        _, _, flags = prep.clean(row('某医院检查疑似肺癌'))
        self.assertIn('possible_residual_identifier_requires_local_review', flags)

    def test_uncertainty_and_stage_not_rewritten(self):
        text = '尚未确诊肺癌Ⅲ期'
        cleaned, removed, flags = prep.clean(row(text))
        self.assertEqual(cleaned, text)
        self.assertEqual((removed, flags), ([], []))

    def test_request_contains_disease_only(self):
        req = prep.request(2, '疑似肺癌')
        self.assertEqual(set(req['user_input']), {'description'})
        self.assertEqual(req['candidate_facts'], [])
        self.assertEqual(req['extracted_documents'], [])
        self.assertEqual(req['application_id'], 'app_fullcsv_000002')
        self.assertEqual(prep.clean(row('NaN')), ('', [], []))

    def test_budget_reserves_before_dispatch_and_stops_before_exceeding(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = live.connect(Path(temporary) / 'attempts.db')
            reserve = live.reservation(case()['request'])
            self.assertFalse(live.claim(db, case(), reserve - 1))
            self.assertEqual(db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0], 0)
            self.assertTrue(live.claim(db, case(), reserve))
            self.assertFalse(live.claim(db, case(2), reserve))
            live.settle(db, {'source_row': 1, 'case_id': case()['case_id'],
                             'status': 'partial_checks_passed', 'total_tokens': 2000})
            self.assertEqual(db.execute('SELECT charge FROM attempts').fetchone()[0], 16000)
            self.assertTrue(live.claim(db, case(2), reserve + 16000))
            db.close()

    def test_missing_usage_keeps_full_reservation_and_no_repeat(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'attempts.db'
            db = live.connect(path)
            live.claim(db, case(), 20_000_000)
            live.settle(db, {'source_row': 1, 'case_id': case()['case_id'],
                             'status': 'boundary_or_transport_rejected', 'total_tokens': None})
            self.assertEqual(db.execute('SELECT charge,reservation FROM attempts').fetchone(),
                             (live.reservation(case()['request']),) * 2)
            db.close()
            reopened = live.connect(path)
            with self.assertRaises(sqlite3.IntegrityError):
                live.claim(reopened, case(), 20_000_000)
            reopened.close()

    def test_crash_claim_survives_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'attempts.db'
            db = live.connect(path)
            live.claim(db, case(), 20_000_000)
            db.close()
            reopened = live.connect(path)
            self.assertEqual(reopened.execute('SELECT status FROM attempts').fetchone()[0], 'calling_or_unknown')
            reopened.close()

    def test_new_claim_records_publication_without_relabelling_old_attempts(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = live.connect(Path(temporary) / 'attempts.db')
            live.claim(db, case(), 20_000_000)
            publication = {'epoch': 'user-reported', 'publication_verified_by_export': False}
            db.execute("INSERT INTO meta VALUES ('active_publication',?)", (json.dumps(publication),))
            db.commit()
            live.claim(db, case(2), 20_000_000)
            records = [json.loads(r[0]) for r in db.execute('SELECT record FROM attempts ORDER BY source_row')]
            self.assertNotIn('publication_basis', records[0])
            self.assertEqual(records[1]['publication_basis'], publication)
            db.close()

    def test_reviewed_unknown_timeout_preserves_full_charge_and_refuses_mismatched_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'private'
            private.mkdir()
            db = live.connect(private / 'attempts.db')
            live.claim(db, case(), 20_000_000)
            live.settle(db, {'source_row': 1, 'case_id': case()['case_id'],
                             'status': 'boundary_or_transport_rejected', 'total_tokens': None,
                             'error': 'Dify network request failed or timed out; execution may still be running'})
            original = json.loads(db.execute('SELECT record FROM attempts').fetchone()[0])
            db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps({
                'status': 'paused_on_finding_no_retry', 'started_at': 'original-start'}),))
            db.commit()
            evidence = private / 'evidence.json'
            evidence.write_text(json.dumps({'original_attempt': original, 'lookup_status': 'not_recovered'}), encoding='utf-8')
            decisions = {'1': {'request_sha256': original['request_sha256'],
                               'disposition': 'network_unknown_no_retry_full_reservation_continue_new_rows',
                               'remote_execution_status': 'unknown', 'retry_failed_row': False,
                               'evidence_file': 'private/evidence.json', 'evidence_sha256': live.sha(evidence.read_bytes())}}
            (private / 'review-decisions.json').write_text(json.dumps(decisions), encoding='utf-8')
            with patch.object(live, 'PRIVATE', private), patch.object(live, 'ROOT', root):
                self.assertEqual(live.resume_review(db), 'original-start')
                self.assertEqual(db.execute('SELECT charge,reservation FROM attempts').fetchone(),
                                 (live.reservation(case()['request']),) * 2)
                original['request_sha256'] = 'wrong'
                evidence.write_text(json.dumps({'original_attempt': original, 'lookup_status': 'not_recovered'}), encoding='utf-8')
                decisions['1']['evidence_sha256'] = live.sha(evidence.read_bytes())
                (private / 'review-decisions.json').write_text(json.dumps(decisions), encoding='utf-8')
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
            db.close()

    def test_observed_usage_over_reservation_is_flagged(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = live.connect(Path(temporary) / 'attempts.db')
            live.claim(db, case(), 20_000_000)
            self.assertFalse(live.settle(db, {'source_row': 1, 'case_id': case()['case_id'],
                                            'status': 'partial_checks_passed', 'total_tokens': 100000}))
            db.close()

    def test_invalid_inner_json_is_saved_before_it_can_be_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw = json.dumps({'data': {'total_tokens': 2216, 'outputs': {'result': '{bad-json'}}}).encode()
            metadata = {}
            path = Path(temporary) / 'wire.json'
            captured = live.UsageResponse(io.BytesIO(raw), metadata, path).read(65536)
            self.assertEqual(captured, raw)
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(metadata['total_tokens'], 2216)

    def test_policy_filled_raw_result_is_reported_invalid_and_provenance_is_verified(self):
        raw = json.dumps({'schema_version':'1.0','application_id':'app_test','application_revision':1,
                          'candidate_facts':[], 'warnings':[], 'questions':[{
                              'question_id':'question_001','field':'patient.relationship_to_applicant',
                              'question':'患者与您什么关系？','reason':'输入未提供。'}]})
        outputs = live.question_format(raw)
        wire = json.dumps({'data':{'outputs':outputs}}).encode()
        result = live.inspect_question_format(wire, live.QUESTION_FORMAT_VERSION)
        self.assertIs(result['raw_model_contract_valid'], False)
        self.assertEqual(result['question_policy_inserted_false_paths'], ['/questions/0/required'])
        outputs['result'] = '{}'
        with self.assertRaises(live.AgentError):
            live.inspect_question_format(json.dumps({'data':{'outputs':outputs}}).encode())

    def test_missing_provenance_cannot_masquerade_as_new_guard_workflow(self):
        wire = json.dumps({'data':{'outputs':{'result':'{}'}}}).encode()
        self.assertEqual(live.inspect_question_format(wire), {})
        with self.assertRaises(live.AgentError):
            live.inspect_question_format(wire, live.QUESTION_FORMAT_VERSION)

    def test_missing_question_flag_review_requires_reported_guard_and_preserves_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'private'
            private.mkdir()
            db = live.connect(private / 'attempts.db')
            live.claim(db, case(), 20_000_000)
            live.settle(db, {'source_row':1, 'case_id':case()['case_id'],
                'status':'boundary_or_transport_rejected', 'total_tokens':2444,
                'error':'Schema validation failed: AgentExtractResponse (required at schema properties/questions/items/required; missing required)'})
            saved = json.loads(db.execute('SELECT record FROM attempts').fetchone()[0])
            original = dict(schema_version='1.0',application_id='app_test',application_revision=1,
                candidate_facts=[],warnings=[],questions=[dict(question_id='question_001',
                    field='patient.relationship_to_applicant',question='患者与您什么关系？',reason='输入未提供。')])
            evidence = private / 'original.json'
            evidence.write_text(json.dumps(original),encoding='utf-8')
            decisions = {'1':dict(request_sha256=saved['request_sha256'],
                disposition='confirmed_missing_question_required_kept_failed_continue_new_rows',
                retry_failed_row=False,evidence_file='private/original.json',evidence_sha256=live.sha(evidence.read_bytes()))}
            (private/'review-decisions.json').write_text(json.dumps(decisions),encoding='utf-8')
            db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps({
                'status':'paused_on_finding_no_retry','started_at':'original-start'}),))
            db.commit()
            with patch.object(live,'PRIVATE',private),patch.object(live,'ROOT',root):
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
                db.execute("INSERT INTO meta VALUES ('active_publication',?)", (json.dumps({
                    'question_format_version':live.QUESTION_FORMAT_VERSION}),))
                db.commit()
                self.assertEqual(live.resume_review(db),'original-start')
            self.assertEqual(db.execute('SELECT status,charge FROM attempts').fetchone(),
                             ('boundary_or_transport_rejected',2444*8))
            db.close()

    def test_reviewed_resume_does_not_clear_failed_row_or_previous_charges(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / 'private'
            private.mkdir()
            db = live.connect(private / 'attempts.db')
            live.claim(db, case(), 20_000_000)
            live.settle(db, {'source_row': 1, 'case_id': case()['case_id'],
                             'status': 'boundary_or_transport_rejected', 'total_tokens': 2216,
                             'error': 'Dify returned invalid JSON'})
            saved = json.loads(db.execute('SELECT record FROM attempts').fetchone()[0])
            db.execute("INSERT INTO meta VALUES ('last_progress',?)", (json.dumps({
                'status': 'paused_on_finding_no_retry', 'started_at': 'original-start'}),))
            db.commit()
            evidence = private / 'evidence.json'
            evidence.write_text('{}', encoding='utf-8')
            decisions = {'1': {'request_sha256': saved['request_sha256'],
                        'disposition': 'confirmed_invalid_model_json_kept_failed_continue_new_rows',
                        'evidence_file': 'private/evidence.json', 'evidence_sha256': live.sha(evidence.read_bytes())}}
            (private / 'review-decisions.json').write_text(json.dumps(decisions), encoding='utf-8')
            with patch.object(live, 'PRIVATE', private), patch.object(live, 'ROOT', root):
                self.assertEqual(live.resume_review(db), 'original-start')
            self.assertEqual(db.execute('SELECT status,charge FROM attempts').fetchone(),
                             ('boundary_or_transport_rejected', 2216 * 8))
            evidence.write_text('changed', encoding='utf-8')
            with patch.object(live, 'PRIVATE', private), patch.object(live, 'ROOT', root):
                with self.assertRaises(live.AgentError):
                    live.resume_review(db)
            db.close()


if __name__ == '__main__':
    unittest.main()
