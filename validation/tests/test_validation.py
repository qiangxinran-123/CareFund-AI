from contextlib import redirect_stdout
import copy
import io
import json
from pathlib import Path
import unittest

from validation import (
    ContractValidationError, ValidationPolicy, validate,
    validate_for_confirmation, validate_for_export,
)
from validation.__main__ import main
from validation.evidence_tracker import EvidenceTracker
from validation.rules.values import money_mentions, supported_by
from validation.schema import check_model


ROOT = Path(__file__).resolve().parents[2]


def load_example(name):
    return json.loads((ROOT / "contracts" / "examples" / name).read_text(encoding="utf-8"))


def make_request():
    application = load_example("application.example.json")
    facts = load_example("agent-response.example.json")["candidate_facts"]
    for fact in facts:
        fact["user_confirmed"] = True
        if fact["source_type"] == "document":
            fact["verification_status"] = "supported"
    return {
        "schema_version": "1.0",
        "application_id": application["application"]["application_id"],
        "application_revision": application["application"]["revision"],
        "documents": application["documents"],
        "evidence": application["evidence"],
        "facts": facts,
    }


def make_policy():
    return ValidationPolicy.from_dict(json.loads(
        (ROOT / "validation" / "examples" / "policy.demo.json").read_text(encoding="utf-8"),
    ))


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.request = make_request()
        self.policy = make_policy()

    def run_check(self):
        response = validate(self.request, policy=self.policy)
        check_model(response, "validation.schema.json", "ValidationResult")
        known = {fact["fact_id"] for fact in self.request["facts"]}
        self.assertTrue(all(set(item["related_fact_ids"]) <= known for item in response["issues"]))
        return response

    def assert_blocked(self, kind=None):
        response = self.run_check()
        self.assertFalse(response["can_finalize"])
        if kind:
            self.assertTrue(any(item["type"] == kind and item["severity"] == "blocking" for item in response["issues"]))
        return response

    def test_valid_input_and_output_follow_shared_contract(self):
        response = self.run_check()
        self.assertTrue(response["can_finalize"])
        self.assertEqual(self.request["application_revision"], response["application_revision"])
        self.assertTrue(any(item["severity"] == "info" for item in response["issues"]))

    def test_input_is_not_modified(self):
        before = copy.deepcopy(self.request)
        self.run_check()
        self.assertEqual(before, self.request)

    def test_no_policy_never_finalizes(self):
        response = validate(self.request)
        self.assertFalse(response["can_finalize"])
        self.assertTrue(any(item["field"] == "validation.policy" for item in response["issues"]))

    def test_empty_collections_require_facts_and_material(self):
        self.request.update(documents=[], evidence=[], facts=[])
        self.assert_blocked("missing")

    def test_unconfirmed_required_fact_blocks(self):
        self.request["facts"][0]["user_confirmed"] = False
        self.assert_blocked("missing")

    def test_user_statement_cannot_replace_required_document_fact(self):
        self.request["facts"][1].update(source_type="user_input", evidence_ids=[], verification_status="pending")
        self.assert_blocked("unsupported")

    def test_user_confirmation_alone_cannot_claim_document_support(self):
        self.request["facts"][0]["verification_status"] = "supported"
        self.assert_blocked("unsupported")

    def test_pending_document_fact_is_independently_checked_without_promotion(self):
        self.request["facts"][1]["verification_status"] = "pending"
        self.assertTrue(self.run_check()["can_finalize"])
        self.assertEqual("pending", self.request["facts"][1]["verification_status"])
        self.request["evidence"][0]["text_excerpt"] = "费用未提供。"
        self.assert_blocked("unsupported")

    def test_unsupported_or_conflicting_status_blocks(self):
        for status in ("unsupported", "conflicting"):
            with self.subTest(status=status):
                self.request["facts"][1]["verification_status"] = status
                self.assert_blocked()

    def test_foreign_application_document_blocks(self):
        self.request["documents"][0]["application_id"] = "app_someone_else"
        self.assert_blocked("unsupported")

    def test_unfinished_or_failed_document_blocks(self):
        for status in ("uploaded", "processing", "failed"):
            with self.subTest(status=status):
                self.request["documents"][0]["processing_status"] = status
                self.assert_blocked("missing")

    def test_duplicate_ids_never_silently_overwrite(self):
        for collection in ("documents", "evidence", "facts"):
            with self.subTest(collection=collection):
                self.request = make_request()
                self.request[collection].append(copy.deepcopy(self.request[collection][0]))
                self.assert_blocked("invalid_format")

    def test_missing_document_reference_blocks(self):
        self.request["evidence"][0]["document_id"] = "doc_missing"
        self.assert_blocked("unsupported")

    def test_fabricated_evidence_reference_blocks(self):
        self.request["facts"][1]["evidence_ids"] = ["ev_invented"]
        self.assert_blocked("unsupported")

    def test_unknown_page_remains_null(self):
        self.request["evidence"][0]["page"] = None
        self.assertTrue(self.run_check()["can_finalize"])
        trace = EvidenceTracker(self.request).trace("fact_demo_002")
        self.assertIsNone(trace[0]["evidence"]["page"])

    def test_fabricated_supported_amount_is_rejected(self):
        self.request["facts"][1]["value"]["value"]["amount_minor"] *= 10
        self.assert_blocked("unsupported")

    def test_currency_is_not_inferred_or_converted(self):
        self.request["facts"][1]["value"]["value"]["currency"] = "USD"
        self.assert_blocked("unsupported")

    def test_money_conflict_between_user_and_document(self):
        other = copy.deepcopy(self.request["facts"][1])
        other.update(fact_id="fact_user_cost", source_type="user_input", evidence_ids=[], verification_status="pending")
        other["value"]["value"]["amount_minor"] = 9999900
        self.request["facts"].append(other)
        self.assert_blocked("inconsistent_amount")

    def test_cross_currency_values_conflict(self):
        other = copy.deepcopy(self.request["facts"][1])
        other.update(fact_id="fact_user_cost", source_type="user_input", evidence_ids=[], verification_status="pending")
        other["value"]["value"]["currency"] = "USD"
        self.request["facts"].append(other)
        self.assert_blocked("inconsistent_amount")

    def test_date_conflict_between_sources(self):
        other = copy.deepcopy(self.request["facts"][2])
        other.update(fact_id="fact_user_date", source_type="user_input", evidence_ids=[], verification_status="pending")
        other["value"]["value"] = "2026-10-19"
        self.request["facts"].append(other)
        self.assert_blocked("inconsistent_date")

    def test_correction_does_not_automatically_win_over_other_sources(self):
        other = copy.deepcopy(self.request["facts"][0])
        other.update(fact_id="fact_correction", source_type="user_correction")
        other["value"]["value"] = "另一个相矛盾的陈述"
        self.request["facts"].append(other)
        self.assert_blocked("conflict")

    def test_identical_values_from_two_sources_are_not_a_conflict(self):
        other = copy.deepcopy(self.request["facts"][1])
        other.update(fact_id="fact_user_cost", source_type="user_input", evidence_ids=[], verification_status="pending")
        self.request["facts"].append(other)
        self.assertTrue(self.run_check()["can_finalize"])

    def test_field_kind_is_checked_by_explicit_policy(self):
        self.request["facts"][1]["value"] = {"kind": "text", "value": "示例费用预估合计"}
        self.assert_blocked("invalid_format")

    def test_whitespace_only_user_fact_blocks(self):
        self.request["facts"][0]["value"]["value"] = "  \n "
        self.assert_blocked("invalid_format")

    def test_schema_rejects_bad_enum_missing_field_and_extra_field(self):
        for mutation in (
            lambda r: r.update(schema_version="2.0"),
            lambda r: r.pop("application_revision"),
            lambda r: r.update(can_finalize=True),
            lambda r: r.update(evidence=None),
            lambda r: r["facts"][0].update(source_type="llm"),
        ):
            with self.subTest(mutation=mutation):
                request = make_request()
                mutation(request)
                with self.assertRaises(ContractValidationError):
                    validate(request, policy=self.policy)

    def test_money_must_be_a_nonnegative_integer_not_float_or_bool(self):
        for value in (-1, 1.2, 1250000.0, True):
            with self.subTest(value=value):
                self.request["facts"][1]["value"]["value"]["amount_minor"] = value
                with self.assertRaises(ContractValidationError):
                    self.run_check()

    def test_invalid_calendar_date_rejected(self):
        self.request["facts"][2]["value"]["value"] = "2026-02-30"
        with self.assertRaises(ContractValidationError):
            self.run_check()

    def test_contract_error_does_not_echo_sensitive_rejected_value(self):
        self.request["facts"][0]["source_type"] = "PRIVATE_PATIENT_CONTENT"
        with self.assertRaises(ContractValidationError) as raised:
            self.run_check()
        self.assertNotIn("PRIVATE_PATIENT_CONTENT", str(raised.exception))

    def test_policy_rejects_invalid_and_empty_rules(self):
        for data in (
            {}, {"required_fields": []}, {"required_fields": "medical"},
            {"required_fields": ["ok"], "unknown": True},
            {"required_fields": ["ok", "ok"]},
            {"required_fields": ["ok"], "document_required_fields": ["other"]},
            {"required_fields": ["ok"], "require_user_confirmation": "false"},
            {"required_fields": ["ok"], "field_kinds": {"ok": "float"}},
        ):
            with self.subTest(data=data), self.assertRaises(ValueError):
                ValidationPolicy.from_dict(data)

    def test_supported_value_checks_do_not_match_numeric_substrings(self):
        self.assertFalse(supported_by({"kind": "money", "value": {"currency": "CNY", "amount_minor": 125000}}, "12500元"))
        self.assertFalse(supported_by({"kind": "integer", "value": 12}, "112"))
        self.assertFalse(supported_by({"kind": "date", "value": "2026-10-18"}, "2026-10-19"))

    def test_money_normalization_uses_decimal_and_explicit_currency(self):
        for text in ("人民币 12,500.00 元", "12500元", "人民币1.25万元", "￥１２，５００．００"):
            with self.subTest(text=text):
                self.assertIn(("CNY", 1250000), money_mentions(text))
        self.assertNotIn(("CNY", 1250000), money_mentions("12500"))
        self.assertIn(("USD", 1250000), money_mentions("USD 12500"))

    def test_negation_and_uncertainty_are_not_dropped(self):
        for text in ("无肺癌", "未见肺癌", "疑似肺癌", "肺癌待排", "考虑肺癌"):
            with self.subTest(text=text):
                self.assertFalse(supported_by({"kind": "text", "value": "肺癌"}, text))
        self.assertTrue(supported_by({"kind": "text", "value": "疑似肺癌"}, "检查结论：疑似肺癌。"))


class CostMeaningTests(unittest.TestCase):
    """A numeric match must retain the financial meaning supplied by evidence."""

    def check_cost(self, field, excerpt, *, source_type="document", status="pending"):
        request = make_request()
        fact = request["facts"][1]
        fact.update(field=field, source_type=source_type, verification_status=status)
        request["facts"] = [fact]
        request["evidence"] = [request["evidence"][0]]
        request["evidence"][0]["text_excerpt"] = excerpt
        policy = ValidationPolicy(required_fields=(field,), field_kinds={field: "money"})
        original = copy.deepcopy(request)
        report = validate(request, policy=policy)
        check_model(report, "validation.schema.json", "ValidationResult")
        self.assertEqual(original, request)
        return report

    def test_estimate_cannot_prove_already_paid_cost(self):
        report = self.check_cost("treatment.paid_cost", "后续治疗预估人民币12500元。")
        self.assertFalse(report["can_finalize"])
        self.assertTrue(any(issue["type"] == "unsupported" for issue in report["issues"]))

    def test_paid_cost_cannot_prove_future_estimate(self):
        self.assertFalse(self.check_cost("treatment.estimated_cost", "已支付医疗费人民币12500元。")["can_finalize"])

    def test_explicit_paid_cost_is_accepted_without_promoting_pending(self):
        for text in ("累计已支付人民币12,500.00元。", "医疗费实缴12500元。", "已结算人民币12500元。"):
            with self.subTest(text=text):
                self.assertTrue(self.check_cost("treatment.paid_cost", text)["can_finalize"])

    def test_explicit_estimate_is_accepted(self):
        for text in ("后续费用预计人民币12500元。", "治疗费用预算1.25万元。", "人民币12500元为预估费用。"):
            with self.subTest(text=text):
                self.assertTrue(self.check_cost("treatment.estimated_cost", text)["can_finalize"])

    def test_amount_without_cost_meaning_needs_clarification(self):
        for field in ("treatment.paid_cost", "treatment.estimated_cost"):
            with self.subTest(field=field):
                self.assertFalse(self.check_cost(field, "金额人民币12500元。")["can_finalize"])

    def test_negation_and_mixed_ambiguous_meanings_block(self):
        for text in ("尚未支付人民币12500元。", "并非已支付人民币12500元。", "已支付金额不含人民币12500元。", "已支付与预估费用共人民币12500元。"):
            with self.subTest(text=text):
                self.assertFalse(self.check_cost("treatment.paid_cost", text)["can_finalize"])

    def test_cost_meaning_cannot_be_borrowed_from_another_clause(self):
        self.assertFalse(self.check_cost("treatment.paid_cost", "已支付100元，后续预估12500元。")["can_finalize"])
        self.assertFalse(self.check_cost("treatment.estimated_cost", "已支付12500元；后续预估100元。")["can_finalize"])

    def test_separate_correctly_labelled_amount_can_be_used(self):
        text = "已支付12,500.00元，后续预估100元。"
        self.assertTrue(self.check_cost("treatment.paid_cost", text)["can_finalize"])

    def test_claimed_supported_status_does_not_bypass_cost_meaning(self):
        for source in ("document", "user_input", "user_correction"):
            with self.subTest(source=source):
                self.assertFalse(self.check_cost("treatment.paid_cost", "预估费用12500元。", source_type=source, status="supported")["can_finalize"])

    def test_paid_and_estimated_are_distinct_fields_even_when_values_differ(self):
        request = make_request()
        estimated = request["facts"][1]
        estimated["verification_status"] = "pending"
        paid = copy.deepcopy(estimated)
        paid.update(fact_id="fact_paid_demo", field="treatment.paid_cost", evidence_ids=["ev_paid_demo"])
        paid["value"]["value"]["amount_minor"] = 10000
        request["facts"] = [estimated, paid]
        request["evidence"].append(dict(copy.deepcopy(request["evidence"][0]), evidence_id="ev_paid_demo", text_excerpt="已支付人民币100元。"))
        policy = ValidationPolicy(required_fields=("treatment.paid_cost", "treatment.estimated_cost"))
        report = validate(request, policy=policy)
        self.assertTrue(report["can_finalize"])
        self.assertFalse(any(issue["type"] == "inconsistent_amount" for issue in report["issues"]))


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.request = make_request()
        self.policy = make_policy()
        self.application = load_example("application.example.json")["application"]
        self.application["status"] = "confirmed"
        self.draft = load_example("draft.example.json")
        self.draft.update(status="confirmed", confirmed_at="2026-10-20T09:45:00Z")
        self.action = {
            "draft_id": self.draft["draft_id"], "draft_revision": self.draft["draft_revision"],
            "expected_application_revision": self.application["revision"], "format": "json",
        }

    def check(self):
        response = validate_for_export(self.request, self.application, self.draft, self.action, policy=self.policy)
        check_model(response, "validation.schema.json", "ValidationResult")
        return response

    def test_current_confirmed_draft_can_export(self):
        self.assertTrue(self.check()["can_finalize"])

    def test_confirmation_uses_current_generated_draft(self):
        self.application["status"] = "draft_ready"
        self.draft.update(status="generated", confirmed_at=None)
        self.action.pop("format")
        response = validate_for_confirmation(self.request, self.application, self.draft, self.action, policy=self.policy)
        self.assertTrue(response["can_finalize"])

    def test_changed_application_invalidates_old_draft(self):
        self.application["revision"] += 1
        self.assertFalse(self.check()["can_finalize"])

    def test_outdated_or_foreign_snapshot_is_rejected(self):
        for field, value in (("application_revision", 1), ("application_id", "app_foreign")):
            with self.subTest(field=field):
                original = self.request[field]
                self.request[field] = value
                self.assertFalse(self.check()["can_finalize"])
                self.request[field] = original

    def test_request_must_match_both_draft_and_application_revision(self):
        for key, value in (("draft_id", "draft_other"), ("draft_revision", 9), ("expected_application_revision", 1)):
            with self.subTest(key=key):
                original = self.action[key]
                self.action[key] = value
                self.assertFalse(self.check()["can_finalize"])
                self.action[key] = original

    def test_stale_or_unconfirmed_draft_never_exports(self):
        for status in ("stale", "generated"):
            with self.subTest(status=status):
                self.draft["status"] = status
                self.assertFalse(self.check()["can_finalize"])

    def test_application_state_must_allow_export(self):
        self.application["status"] = "reviewing"
        self.assertFalse(self.check()["can_finalize"])

    def test_missing_or_invalid_confirmation_timestamp_blocks(self):
        for confirmed_at in (None, "2026-10-20T09:00:00Z"):
            with self.subTest(confirmed_at=confirmed_at):
                self.draft["confirmed_at"] = confirmed_at
                self.assertFalse(self.check()["can_finalize"])

    def test_fabricated_fact_reference_blocks(self):
        self.draft["sections"][0]["fact_ids"] = ["fact_invented"]
        self.assertFalse(self.check()["can_finalize"])

    def test_draft_cannot_use_unconfirmed_optional_fact(self):
        self.request["facts"][2]["user_confirmed"] = False
        self.draft["sections"][0]["fact_ids"].append("fact_demo_003")
        self.assertFalse(self.check()["can_finalize"])

    def test_duplicate_section_ids_block(self):
        self.draft["sections"][1]["section_id"] = self.draft["sections"][0]["section_id"]
        self.assertFalse(self.check()["can_finalize"])

    def test_draft_cannot_exaggerate_cost_even_with_valid_reference(self):
        self.draft["sections"][1]["content"] = "预计花费125000元。"
        self.assertFalse(self.check()["can_finalize"])

    def test_draft_cannot_hide_new_amount_by_omitting_currency_unit(self):
        for prose in ("预计花费125000。", "需要12.5万。", "费用$12500。", "还需要300次治疗。"):
            with self.subTest(prose=prose):
                self.draft["sections"][1]["content"] = prose
                self.assertFalse(self.check()["can_finalize"])

    def test_draft_common_exaggeration_is_blocked(self):
        self.draft["sections"][0]["content"] += "患者生命垂危，急需抢救。"
        self.assertFalse(self.check()["can_finalize"])

    def test_draft_cannot_invent_date_in_title(self):
        self.draft["sections"][0]["title"] = "2026年10月19日的治疗"
        self.assertFalse(self.check()["can_finalize"])

    def test_invalid_date_in_draft_is_not_silently_ignored(self):
        self.draft["sections"][0]["content"] = "治疗日期为2026-02-30。"
        self.assertFalse(self.check()["can_finalize"])

    def test_draft_can_use_date_supported_by_its_own_references(self):
        self.draft["sections"][0].update(content="材料记载日期为2026年10月18日。", fact_ids=["fact_demo_003"])
        self.assertTrue(self.check()["can_finalize"])

    def test_export_rechecks_current_evidence_instead_of_trusting_old_result(self):
        self.assertTrue(self.check()["can_finalize"])
        self.request["evidence"][0]["text_excerpt"] = "金额尚未提供。"
        self.assertFalse(self.check()["can_finalize"])

    def test_export_does_not_mutate_any_input_or_state(self):
        before = copy.deepcopy((self.request, self.application, self.draft, self.action))
        self.check()
        self.assertEqual(before, (self.request, self.application, self.draft, self.action))


class CliTests(unittest.TestCase):
    def test_cli_uses_real_request_and_produces_contract_json(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([str(ROOT / "validation" / "examples" / "request.demo.json"),
                         "--policy", str(ROOT / "validation" / "examples" / "policy.demo.json")])
        response = json.loads(output.getvalue())
        self.assertEqual(0, code)
        check_model(response, "validation.schema.json", "ValidationResult")
        self.assertTrue(response["can_finalize"])

    def test_cli_missing_policy_blocks(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([str(ROOT / "validation" / "examples" / "request.demo.json")])
        self.assertEqual(1, code)
        self.assertFalse(json.loads(output.getvalue())["can_finalize"])

    def test_cli_missing_file_returns_safe_error_response(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([str(ROOT / "validation" / "examples" / "absent.json")])
        response = json.loads(output.getvalue())
        self.assertEqual(2, code)
        check_model(response, "common.schema.json", "ErrorResponse")
        self.assertNotIn(str(ROOT), output.getvalue())


if __name__ == "__main__":
    unittest.main()
