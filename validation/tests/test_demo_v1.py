"""INT-07 / INT-08 acceptance with real A boundary and synthetic current state."""

from copy import deepcopy
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import Mock, patch

from agent.agent_service import AgentService, AgentError
from agent.draft_policy import DRAFT_WARNING, sections_for_facts
from validation import (
    AgentAdaptationError, ContractValidationError, DEMO_V1_POLICY_PATH,
    ValidationPolicy, load_policy, prepare_agent_draft_request, validate,
    validate_agent_draft, validate_for_generation, validate_for_confirmation, validate_for_export,
)
from validation.schema import check_model


ROOT = Path(__file__).resolve().parents[2]


def scenario(mode="clean"):
    """All confirmations here are explicit synthetic fixtures, not user actions."""
    app = {
        "application_id": "app_int07_demo", "schema_version": "1.0", "revision": 2,
        "status": "ready_for_draft",
        "patient_info": {"display_name": "合成演示患者", "medical_summary": "仍在检查，尚未确诊。"},
        "created_at": "2026-10-20T00:00:00Z", "updated_at": "2026-10-20T00:00:00Z",
    }
    document = {
        "document_id": "doc_int07_demo", "application_id": app["application_id"],
        "filename": "synthetic-only.pdf", "media_type": "application/pdf", "size_bytes": 128,
        "uploaded_at": "2026-10-20T00:00:00Z", "processing_status": "processed",
    }
    specs = [
        ("patient.medical_summary", "text", "仍在检查，尚未确诊。", "仍在检查，尚未确诊。"),
        ("treatment.estimated_cost", "money", {"currency": "CNY", "amount_minor": 1250000}, "后续预估治疗费用人民币12500元。"),
        ("patient.relationship_to_applicant", "text", "母亲", "患者与申请人关系：母亲"),
        ("contact.city", "text", "示例城市", "当前所在：示例城市"),
        ("treatment.recorded_date", "date", "2026-10-20", "记录日期2026年10月20日"),
    ]
    facts, evidence = [], []
    for i, (field, kind, value, text) in enumerate(specs):
        ref = f"ev_int07_{i}"
        evidence.append({"evidence_id": ref, "document_id": document["document_id"],
                         "source_type": "document", "page": i + 1, "text_excerpt": text,
                         "extraction_method": "manual"})
        facts.append({"fact_id": f"fact_int07_{i}", "field": field,
                      "value": {"kind": kind, "value": value}, "source_type": "document",
                      "evidence_ids": [ref], "verification_status": "pending", "user_confirmed": True})
    if mode == "info":
        # A user-origin city is informational; it is not a document requirement.
        facts[3].update(source_type="user_input", evidence_ids=[])
    elif mode == "warning":
        facts = facts[:2]
    elif mode == "conflict":
        other = deepcopy(facts[1])
        other.update(fact_id="fact_cost_other", source_type="user_input", evidence_ids=[])
        other["value"]["value"]["amount_minor"] = 2000000
        facts.append(other)
    request = {"schema_version": "1.0", "application_id": app["application_id"],
               "application_revision": app["revision"], "documents": [document],
               "evidence": evidence, "facts": facts}
    return app, request


def formal_draft(app, request):
    return {
        "schema_version": "1.0", "draft_id": "draft_int07_demo",
        "application_id": app["application_id"], "application_revision": app["revision"],
        "draft_revision": 1, "status": "generated", "created_at": "2026-10-20T00:01:00Z",
        "confirmed_at": None,
        "sections": [dict(section_id=f"section_int07_{i}", **section)
                     for i, section in enumerate(sections_for_facts(request["facts"]))],
    }


def actions(app, draft):
    confirmation = {"draft_id": draft["draft_id"], "draft_revision": draft["draft_revision"],
                    "expected_application_revision": app["revision"]}
    return confirmation, dict(confirmation, format="json")


class DemoV1Tests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy("demo_v1")

    def test_named_policy_extends_backend_integration_requirements(self):
        baseline = json.loads((ROOT / "backend/config/validation-policy.integration.json").read_text(encoding="utf-8"))
        self.assertEqual(tuple(baseline["required_fields"]), self.policy.required_fields)
        self.assertEqual(tuple(baseline["document_required_fields"]), self.policy.document_required_fields)
        self.assertTrue(self.policy.require_processed_document)
        self.assertTrue(self.policy.require_user_confirmation)
        self.assertEqual("blocking", self.policy.draft_issue_scope)
        self.assertIn("不代表", self.policy.notice)

    def test_explicit_file_loading_matches_named_policy(self):
        self.assertEqual(self.policy, load_policy(DEMO_V1_POLICY_PATH))

    def test_missing_or_invalid_policy_never_falls_back(self):
        with self.assertRaises(OSError):
            load_policy(ROOT / "validation/policies/absent.json")
        _, request = scenario()
        self.assertFalse(validate(request)["can_finalize"])
        for data in ({"required_fields": ["ok"], "draft_issue_scope": "none"},
                     {"required_fields": ["ok"], "recommended_fields": ["ok"]},
                     {"required_fields": ["ok"], "recommended_document_fields": "bad"},
                     {"required_fields": ["ok"], "policy_name": "INVALID NAME"}):
            with self.subTest(data=data), self.assertRaises(ValueError):
                ValidationPolicy.from_dict(data)

    def test_five_acceptance_groups(self):
        # Five required groups, plus warning; all calls use unchanged real A code.
        for mode in ("clean", "info", "warning", "conflict", "stale", "invalid_reference"):
            with self.subTest(mode=mode):
                app, request = scenario(mode)
                draft = formal_draft(app, request)
                confirm, export = actions(app, draft)
                if mode == "stale":
                    app["revision"] += 1
                elif mode == "invalid_reference":
                    request["facts"][1]["evidence_ids"] = ["ev_nonexistent"]
                before = deepcopy((app, request, draft, confirm, export))
                prepared, report = prepare_agent_draft_request(
                    request, policy=self.policy, application=app,
                    generation_request={"expected_revision": app["revision"]},
                )
                check_model(report, "validation.schema.json", "ValidationResult")
                blocking_ids = [item["issue_id"] for item in report["issues"] if item["severity"] == "blocking"]
                self.assertEqual(blocking_ids, prepared["validation_issue_ids"])
                allowed = mode in ("clean", "info", "warning")
                self.assertEqual(allowed, report["can_finalize"])
                if mode == "clean":
                    self.assertEqual([], report["issues"])
                elif mode in ("info", "warning"):
                    self.assertTrue(any(item["severity"] == mode for item in report["issues"]))
                    self.assertEqual([], prepared["validation_issue_ids"])
                elif mode == "conflict":
                    self.assertTrue(any(item["type"] == "inconsistent_amount" and item["severity"] == "blocking" for item in report["issues"]))
                response = {key: prepared[key] for key in ("schema_version", "application_id", "application_revision")}
                response.update(candidate_sections=sections_for_facts(request["facts"]), warnings=[DRAFT_WARNING])
                runner = Mock(return_value=response)
                a_service = AgentService(runner)
                with patch.object(socket, "socket", side_effect=AssertionError("Offline only")):
                    if allowed:
                        candidate = a_service.draft(prepared)
                        self.assertTrue(validate_agent_draft(request, candidate, policy=self.policy)["can_finalize"])
                        runner.assert_called_once()
                    else:
                        with self.assertRaises(AgentError):
                            a_service.draft(prepared)
                        runner.assert_not_called()
                confirming_app = dict(deepcopy(app), status="draft_ready")
                confirmation_result = validate_for_confirmation(request, confirming_app, draft, confirm, policy=self.policy)
                self.assertEqual(allowed, confirmation_result["can_finalize"])
                exported_app = dict(deepcopy(app), status="confirmed")
                confirmed_draft = dict(deepcopy(draft), status="confirmed", confirmed_at="2026-10-20T00:02:00Z")
                export_result = validate_for_export(request, exported_app, confirmed_draft, export, policy=self.policy)
                self.assertEqual(allowed, export_result["can_finalize"])
                for final in (confirmation_result, export_result):
                    check_model(final, "validation.schema.json", "ValidationResult")
                self.assertEqual(before, (app, request, draft, confirm, export))

    def test_policy_mapping_preserves_complete_issues_and_fact_confirmation(self):
        app, request = scenario("info")
        original = deepcopy(request)
        prepared, result = prepare_agent_draft_request(request, policy=self.policy)
        self.assertTrue(result["issues"])
        self.assertEqual([], prepared["validation_issue_ids"])
        self.assertEqual(original, request)
        self.assertEqual(request["facts"], prepared["candidate_facts"])

    def test_legacy_policy_still_retains_all_issue_ids(self):
        _, request = scenario("info")
        legacy = ValidationPolicy(required_fields=self.policy.required_fields,
                                  document_required_fields=self.policy.document_required_fields)
        prepared, result = prepare_agent_draft_request(request, policy=legacy)
        self.assertEqual([item["issue_id"] for item in result["issues"]], prepared["validation_issue_ids"])

    def test_neither_clean_ids_nor_client_confirmation_bypasses_blocking(self):
        app, request = scenario("conflict")
        prepared, result = prepare_agent_draft_request(request, policy=self.policy)
        self.assertTrue(prepared["validation_issue_ids"])
        self.assertFalse(result["can_finalize"])
        draft = formal_draft(app, request)
        confirm, export = actions(app, draft)
        app["status"] = "confirmed"
        draft.update(status="confirmed", confirmed_at="2026-10-20T00:02:00Z")
        self.assertFalse(validate_for_export(request, app, draft, export, policy=self.policy)["can_finalize"])

    def test_unknown_fact_and_evidence_ids_block_final_operations(self):
        for mode in ("fact", "evidence"):
            app, request = scenario()
            draft = formal_draft(app, request)
            confirm, export = actions(app, draft)
            if mode == "fact":
                draft["sections"][0]["fact_ids"] = ["fact_nonexistent"]
            else:
                request["facts"][0]["evidence_ids"] = ["ev_nonexistent"]
            with self.subTest(mode=mode):
                app["status"] = "draft_ready"
                self.assertFalse(validate_for_confirmation(request, app, draft, confirm, policy=self.policy)["can_finalize"])
                app["status"] = "confirmed"
                draft.update(status="confirmed", confirmed_at="2026-10-20T00:02:00Z")
                self.assertFalse(validate_for_export(request, app, draft, export, policy=self.policy)["can_finalize"])

    def test_unconfirmed_optional_fact_blocks_all_draft_stages(self):
        app, request = scenario()
        request["facts"][-1]["user_confirmed"] = False
        draft = formal_draft(app, request)
        confirm, export = actions(app, draft)
        self.assertFalse(prepare_agent_draft_request(request, policy=self.policy)[1]["can_finalize"])
        app["status"] = "draft_ready"
        self.assertFalse(validate_for_confirmation(request, app, draft, confirm, policy=self.policy)["can_finalize"])
        app["status"] = "confirmed"
        draft.update(status="confirmed", confirmed_at="2026-10-20T00:02:00Z")
        self.assertFalse(validate_for_export(request, app, draft, export, policy=self.policy)["can_finalize"])

    def test_unknown_diagnosis_is_allowed_as_attributed_explanation(self):
        _, request = scenario()
        self.assertIn("尚未确诊", request["facts"][0]["value"]["value"])
        self.assertTrue(validate(request, policy=self.policy)["can_finalize"])

    def test_user_summary_without_support_stays_attributed_and_nonblocking(self):
        _, request = scenario()
        request["facts"][0].update(source_type="user_input", evidence_ids=[])
        report = validate(request, policy=self.policy)
        self.assertTrue(report["can_finalize"])
        self.assertTrue(any(item["severity"] == "info" for item in report["issues"]))
        self.assertTrue(any(item["severity"] == "warning" for item in report["issues"]))

    def test_required_summary_estimate_and_processed_document_remain_required(self):
        for mode in ("summary", "estimate", "document"):
            _, request = scenario()
            if mode == "document":
                request["documents"] = []
            else:
                field = "patient.medical_summary" if mode == "summary" else "treatment.estimated_cost"
                request["facts"] = [fact for fact in request["facts"] if fact["field"] != field]
            with self.subTest(mode=mode):
                self.assertFalse(validate(request, policy=self.policy)["can_finalize"])

    def test_only_advisory_field_and_material_gaps_are_warning(self):
        _, request = scenario("warning")
        report = validate(request, policy=self.policy)
        self.assertTrue(report["can_finalize"])
        self.assertTrue(all(item["severity"] == "warning" for item in report["issues"]))

    def test_money_bad_type_or_negative_is_a_safe_contract_rejection(self):
        for value in (-1, True, 0.5):
            _, request = scenario()
            request["facts"][1]["value"]["value"]["amount_minor"] = value
            with self.subTest(value=value), self.assertRaises(ContractValidationError):
                validate(request, policy=self.policy)

    def test_generation_expected_revision_or_current_snapshot_mismatch_blocks(self):
        for mode in ("expected", "snapshot", "application_id"):
            app, request = scenario()
            action = {"expected_revision": app["revision"]}
            if mode == "expected":
                action["expected_revision"] += 1
            elif mode == "snapshot":
                request["application_revision"] += 1
            else:
                request["application_id"] = "app_other"
            with self.subTest(mode=mode):
                self.assertFalse(validate_for_generation(request, app, action, policy=self.policy)["can_finalize"])

    def test_generation_application_and_request_must_be_supplied_together(self):
        app, request = scenario()
        with self.assertRaises(AgentAdaptationError):
            prepare_agent_draft_request(request, policy=self.policy, application=app)

    def test_blank_display_name_blocks_when_current_application_is_available(self):
        app, request = scenario()
        app["patient_info"]["display_name"] = "  "
        self.assertFalse(validate_for_generation(request, app, {"expected_revision": 2}, policy=self.policy)["can_finalize"])
        app["status"] = "draft_ready"
        draft = formal_draft(app, request)
        self.assertFalse(validate_for_confirmation(request, app, draft, actions(app, draft)[0], policy=self.policy)["can_finalize"])

    def test_demo_v1_rejects_new_prose_without_numeric_changes(self):
        app, request = scenario()
        draft = formal_draft(app, request)
        draft["sections"][0]["content"] = "完全不同的医疗经历。"
        app["status"] = "draft_ready"
        self.assertFalse(validate_for_confirmation(request, app, draft, actions(app, draft)[0], policy=self.policy)["can_finalize"])

    def test_missing_confirmation_timestamp_and_wrong_draft_revision_block(self):
        app, request = scenario()
        draft = formal_draft(app, request)
        app["status"] = "confirmed"
        draft["status"] = "confirmed"
        export = actions(app, draft)[1]
        self.assertFalse(validate_for_export(request, app, draft, export, policy=self.policy)["can_finalize"])
        draft["confirmed_at"] = "2026-10-20T00:02:00Z"
        export["draft_revision"] += 1
        self.assertFalse(validate_for_export(request, app, draft, export, policy=self.policy)["can_finalize"])


if __name__ == "__main__":
    unittest.main()
