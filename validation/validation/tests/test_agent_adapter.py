"""Replay the actual supplied A service boundary with saved synthetic responses.

No Dify credentials, live calls or automatic confirmation are used here.
"""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import unittest

from validation import (
    AgentAdaptationError, ContractValidationError, ValidationPolicy,
    build_validation_request, prepare_agent_draft_request, validate,
    validate_agent_draft, validate_for_confirmation, validate_for_export,
)
from validation.schema import check_model
from .fixtures.a_handoff.agent.agent_service import AgentError, AgentService
from .fixtures.a_handoff.agent.draft_policy import DRAFT_WARNING, sections_for_facts


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures" / "a_handoff"
CASES = ("01_uncertain_paid", "02_preserve_existing", "03_document_evidence", "04_conflicting_amount")


def read(relative):
    return json.loads((FIXTURES / relative).read_text(encoding="utf-8"))


def extract_pair(name):
    base = f"agent/verification/extract/{name}"
    return read(base + ".request.json"), read(base + ".response.json")


def handoff_policy():
    return ValidationPolicy.from_dict(json.loads(
        (ROOT / "validation/examples/policy.a-handoff-demo.json").read_text(encoding="utf-8"),
    ))


def service(runner):
    return AgentService(runner, schema_dir=ROOT / "contracts/schemas")


def document_only_demo():
    """Explicitly constructed synthetic test snapshot, NOT an adapter transform.

    It models B having a current document-only application with a confirmed fact.
    No real user action is inferred from the original saved candidate response.
    """
    request, response = extract_pair("03_document_evidence")
    mapped = build_validation_request(request, response)
    mapped["facts"] = [deepcopy(mapped["facts"][1])]
    mapped["facts"][0]["user_confirmed"] = True
    policy = ValidationPolicy(
        required_fields=("treatment.estimated_cost",),
        document_required_fields=("treatment.estimated_cost",),
        field_kinds={"treatment.estimated_cost": "money"},
    )
    return mapped, policy


class ExtractAdapterTests(unittest.TestCase):
    def test_fixture_hashes_match_original_a_manifest(self):
        provenance = read("PROVENANCE.json")
        self.assertEqual("cc29e6de047c49d20c79d628ed4dfa6a839c104c", provenance["source_commit"])
        for entry in provenance["files"]:
            with self.subTest(path=entry["path"]):
                content = (FIXTURES / entry["path"]).read_bytes()
                self.assertEqual(entry["bytes"], len(content))
                self.assertEqual(entry["sha256"], hashlib.sha256(content).hexdigest())

    def test_all_four_saved_responses_pass_actual_a_boundary_and_map_exactly(self):
        for case in CASES:
            with self.subTest(case=case):
                request, response = extract_pair(case)
                actual = service(lambda operation, payload: deepcopy(response)).extract(request)
                mapped = build_validation_request(request, actual)
                expected = read(f"adaptation_cases/{case}.validation-request.json")
                self.assertEqual(expected, mapped)
                result = validate(mapped, policy=handoff_policy())
                check_model(result, "validation.schema.json", "ValidationResult")
                self.assertFalse(result["can_finalize"])
                known = {fact["fact_id"] for fact in mapped["facts"]}
                self.assertTrue(all(set(item["related_fact_ids"]) <= known for item in result["issues"]))

    def test_existing_fact_confirmation_and_revision_are_preserved(self):
        request, response = extract_pair("02_preserve_existing")
        mapped = build_validation_request(request, response)
        self.assertEqual(2, mapped["application_revision"])
        old_fact = request["candidate_facts"][0]
        self.assertEqual(old_fact, next(f for f in mapped["facts"] if f["fact_id"] == old_fact["fact_id"]))
        self.assertTrue(old_fact["user_confirmed"])

    def test_uncertainty_and_paid_amount_are_preserved(self):
        request, response = extract_pair("01_uncertain_paid")
        mapped = build_validation_request(request, response)
        self.assertEqual(response["candidate_facts"], mapped["facts"])
        summary = next(f for f in mapped["facts"] if f["field"] == "patient.medical_summary")
        self.assertIn("未确诊", summary["value"]["value"])
        self.assertEqual(2000000, mapped["facts"][2]["value"]["value"]["amount_minor"])

    def test_conflicting_amounts_are_not_deduplicated_or_resolved(self):
        request, response = extract_pair("04_conflicting_amount")
        mapped = build_validation_request(request, response)
        costs = [f for f in mapped["facts"] if f["field"] == "treatment.estimated_cost"]
        self.assertEqual([3000000, 5000000], [f["value"]["value"]["amount_minor"] for f in costs])
        report = validate(mapped, policy=handoff_policy())
        self.assertTrue(any(issue["type"] == "inconsistent_amount" for issue in report["issues"]))

    def test_snapshot_and_flags_are_not_modified_or_aliased(self):
        request, response = extract_pair("03_document_evidence")
        before = deepcopy((request, response))
        mapped = build_validation_request(request, response)
        validate(mapped, policy=handoff_policy())
        self.assertEqual(before, (request, response))
        mapped["facts"][0]["user_confirmed"] = True
        mapped["evidence"][0]["page"] = None
        self.assertEqual(before, (request, response))

    def test_identity_and_revision_mismatch_rejected(self):
        for key, value in (("application_id", "app_other"), ("application_revision", 99)):
            request, response = extract_pair("03_document_evidence")
            response[key] = value
            with self.subTest(key=key), self.assertRaises(AgentAdaptationError):
                build_validation_request(request, response)

    def test_response_missing_existing_fact_rejected(self):
        request, response = extract_pair("02_preserve_existing")
        response["candidate_facts"] = response["candidate_facts"][1:]
        with self.assertRaises(AgentAdaptationError):
            build_validation_request(request, response)

    def test_response_modifying_existing_fact_rejected(self):
        request, response = extract_pair("02_preserve_existing")
        response["candidate_facts"][0]["user_confirmed"] = False
        with self.assertRaises(AgentAdaptationError):
            build_validation_request(request, response)

    def test_new_fact_cannot_confirm_or_verify_itself(self):
        for key, value in (("user_confirmed", True), ("verification_status", "supported")):
            request, response = extract_pair("03_document_evidence")
            response["candidate_facts"][1][key] = value
            with self.subTest(key=key), self.assertRaises(AgentAdaptationError):
                build_validation_request(request, response)

    def test_missing_and_wrong_parent_evidence_rejected(self):
        for mode in ("missing", "wrong_document", "foreign_application"):
            request, response = extract_pair("03_document_evidence")
            if mode == "missing":
                response["candidate_facts"][1]["evidence_ids"] = ["ev_missing"]
            elif mode == "wrong_document":
                request["extracted_documents"][0]["evidence"][0]["document_id"] = "doc_other"
            else:
                request["extracted_documents"][0]["document"]["application_id"] = "app_other"
            with self.subTest(mode=mode), self.assertRaises(AgentAdaptationError):
                build_validation_request(request, response)

    def test_duplicate_document_evidence_fact_or_question_id_rejected(self):
        for mode in ("document", "evidence", "fact", "question"):
            request, response = extract_pair("03_document_evidence")
            if mode == "document":
                request["extracted_documents"].append(deepcopy(request["extracted_documents"][0]))
            elif mode == "evidence":
                request["extracted_documents"][0]["evidence"].append(deepcopy(request["extracted_documents"][0]["evidence"][0]))
            else:
                collection = "candidate_facts" if mode == "fact" else "questions"
                response[collection].append(deepcopy(response[collection][0]))
            with self.subTest(mode=mode), self.assertRaises(AgentAdaptationError):
                build_validation_request(request, response)

    def test_same_revision_documents_and_facts_are_all_retained(self):
        request, response = extract_pair("03_document_evidence")
        second = deepcopy(request["extracted_documents"][0])
        second["document"]["document_id"] = "doc_second"
        second["evidence"][0].update(document_id="doc_second", evidence_id="ev_second")
        request["extracted_documents"].append(second)
        mapped = build_validation_request(request, response)
        self.assertEqual(2, len(mapped["documents"]))
        self.assertEqual(2, len(mapped["evidence"]))
        self.assertEqual(response["candidate_facts"], mapped["facts"])

    def test_schema_mismatch_rejected_without_patient_value(self):
        request, response = extract_pair("03_document_evidence")
        response["candidate_facts"][0]["source_type"] = "SECRET_PATIENT_TEXT"
        with self.assertRaises(ContractValidationError) as raised:
            build_validation_request(request, response)
        self.assertNotIn("SECRET_PATIENT_TEXT", str(raised.exception))


class DraftAdapterTests(unittest.TestCase):
    def test_pending_but_literally_supported_document_can_enter_a_after_user_confirmation(self):
        mapped, policy = document_only_demo()
        draft_request, report = prepare_agent_draft_request(mapped, policy=policy)
        self.assertTrue(report["can_finalize"])
        self.assertEqual([], draft_request["validation_issue_ids"])
        self.assertEqual("pending", draft_request["candidate_facts"][0]["verification_status"])
        self.assertEqual({mapped["facts"][0]["fact_id"]}, service(None).validate_draft_request(draft_request))

    def test_info_is_retained_even_when_d_can_finalize_so_a_gate_is_visible(self):
        mapped, policy = document_only_demo()
        mapped["facts"].append({
            "fact_id": "fact_user_demo", "field": "patient.medical_summary",
            "value": {"kind": "text", "value": "仍在检查，尚未确诊。"},
            "source_type": "user_input", "evidence_ids": [],
            "verification_status": "pending", "user_confirmed": True,
        })
        draft_request, report = prepare_agent_draft_request(mapped, policy=policy)
        self.assertTrue(report["can_finalize"])
        self.assertTrue(report["issues"])
        self.assertTrue(all(issue["severity"] == "info" for issue in report["issues"]))
        self.assertEqual([item["issue_id"] for item in report["issues"]], draft_request["validation_issue_ids"])
        with self.assertRaises(AgentError):
            service(None).validate_draft_request(draft_request)

    def test_unconfirmed_optional_fact_is_not_silently_filtered(self):
        mapped, policy = document_only_demo()
        extra = deepcopy(mapped["facts"][0])
        extra.update(fact_id="fact_other", field="treatment.other_cost", user_confirmed=False)
        mapped["facts"].append(extra)
        draft_request, report = prepare_agent_draft_request(mapped, policy=policy)
        self.assertFalse(report["can_finalize"])
        self.assertEqual(mapped["facts"], draft_request["candidate_facts"])

    def test_a_exact_value_gate_remains_stricter_than_normalized_text_comparison(self):
        mapped, _ = document_only_demo()
        fact = deepcopy(mapped["facts"][0])
        fact.update(field="patient.medical_summary", value={"kind": "text", "value": "Demo"})
        mapped["evidence"][0]["text_excerpt"] = "Demo"
        mapped["facts"] = [fact, dict(deepcopy(fact), fact_id="fact_other", value={"kind": "text", "value": "demo"})]
        policy = ValidationPolicy(required_fields=("patient.medical_summary",))
        self.assertTrue(validate(mapped, policy=policy)["can_finalize"])
        _, report = prepare_agent_draft_request(mapped, policy=policy)
        self.assertFalse(report["can_finalize"])

    def test_missing_policy_and_empty_facts_block_draft_preparation(self):
        mapped, policy = document_only_demo()
        _, report = prepare_agent_draft_request(mapped)
        self.assertFalse(report["can_finalize"])
        mapped["facts"] = []
        _, report = prepare_agent_draft_request(mapped, policy=policy)
        self.assertFalse(report["can_finalize"])

    def test_candidate_draft_check_accepts_actual_a_service_output(self):
        mapped, policy = document_only_demo()
        draft_request, _ = prepare_agent_draft_request(mapped, policy=policy)
        response = {key: draft_request[key] for key in ("schema_version", "application_id", "application_revision")}
        response.update(candidate_sections=sections_for_facts(mapped["facts"]), warnings=[DRAFT_WARNING])
        actual = service(lambda operation, payload: deepcopy(response)).draft(draft_request)
        report = validate_agent_draft(mapped, actual, policy=policy)
        self.assertTrue(report["can_finalize"])
        self.assertEqual("pending", mapped["facts"][0]["verification_status"])

    def test_candidate_edited_cost_paid_label_or_fake_fact_id_block(self):
        mapped, policy = document_only_demo()
        for mutation in ("amount", "paid", "reference", "title", "missing", "extra"):
            response = {key: mapped[key] for key in ("schema_version", "application_id", "application_revision")}
            response.update(candidate_sections=sections_for_facts(mapped["facts"]), warnings=[DRAFT_WARNING])
            section = response["candidate_sections"][0]
            if mutation == "amount":
                section["content"] = section["content"].replace("30000.00", "50000.00")
            elif mutation == "paid":
                section["content"] = section["content"].replace("后续预估治疗费", "已支付医疗费")
            elif mutation == "reference":
                section["fact_ids"] = ["fact_unknown"]
            elif mutation == "title":
                section["title"] = "已通过平台审核"
            elif mutation == "missing":
                response["candidate_sections"] = []
            else:
                response["candidate_sections"].append(deepcopy(section))
            with self.subTest(mutation=mutation):
                self.assertFalse(validate_agent_draft(mapped, response, policy=policy)["can_finalize"])

    def test_candidate_draft_wrong_revision_or_application_blocks(self):
        mapped, policy = document_only_demo()
        for key, value in (("application_revision", 7), ("application_id", "app_other")):
            response = {key: mapped[key] for key in ("schema_version", "application_id", "application_revision")}
            response.update(candidate_sections=sections_for_facts(mapped["facts"]), warnings=[])
            response[key] = value
            with self.subTest(key=key):
                self.assertFalse(validate_agent_draft(mapped, response, policy=policy)["can_finalize"])

    def test_draft_adapters_do_not_mutate_or_alias_fact_snapshot(self):
        mapped, policy = document_only_demo()
        before = deepcopy(mapped)
        draft_request, _ = prepare_agent_draft_request(mapped, policy=policy)
        draft_request["candidate_facts"][0]["user_confirmed"] = False
        self.assertEqual(before, mapped)

    def test_unknown_foreign_currency_literal_preserves_minor_units(self):
        mapped, _ = document_only_demo()
        fact = mapped["facts"][0]
        fact["value"]["value"] = {"currency": "USD", "amount_minor": 12345}
        mapped["evidence"][0]["text_excerpt"] = "虚构费用预估：USD 123.45。"
        policy = ValidationPolicy(required_fields=("treatment.estimated_cost",))
        draft_request, report = prepare_agent_draft_request(mapped, policy=policy)
        self.assertTrue(report["can_finalize"])
        response = {key: draft_request[key] for key in ("schema_version", "application_id", "application_revision")}
        response.update(candidate_sections=sections_for_facts(mapped["facts"]), warnings=[DRAFT_WARNING])
        actual = service(lambda operation, payload: deepcopy(response)).draft(draft_request)
        self.assertTrue(validate_agent_draft(mapped, actual, policy=policy)["can_finalize"])
        self.assertIn("USD 12345（最小货币单位）", actual["candidate_sections"][0]["content"])

    def test_b_save_confirmation_export_and_revision_invalidation_offline(self):
        mapped, policy = document_only_demo()
        draft_request, report = prepare_agent_draft_request(mapped, policy=policy)
        response = {key: draft_request[key] for key in ("schema_version", "application_id", "application_revision")}
        response.update(candidate_sections=sections_for_facts(mapped["facts"]), warnings=[DRAFT_WARNING])
        candidate = service(lambda operation, payload: deepcopy(response)).draft(draft_request)
        self.assertTrue(validate_agent_draft(mapped, candidate, policy=policy)["can_finalize"])
        application = {
            "application_id": mapped["application_id"], "schema_version": "1.0",
            "revision": mapped["application_revision"], "status": "draft_ready",
            "patient_info": {"display_name": "虚构联调案例", "medical_summary": None},
            "created_at": "2026-10-16T00:00:00Z", "updated_at": "2026-10-16T00:00:00Z",
        }
        draft = {
            **{key: candidate[key] for key in ("schema_version", "application_id", "application_revision")},
            "draft_id": "draft_offline_demo", "draft_revision": 1, "status": "generated",
            "sections": [dict(section_id=f"section_demo_{i}", **section) for i, section in enumerate(candidate["candidate_sections"])],
            "created_at": "2026-10-16T00:00:00Z", "confirmed_at": None,
        }
        action = {"draft_id": draft["draft_id"], "draft_revision": 1, "expected_application_revision": application["revision"]}
        self.assertTrue(validate_for_confirmation(mapped, application, draft, action, policy=policy)["can_finalize"])
        application["status"] = "confirmed"
        draft.update(status="confirmed", confirmed_at="2026-10-16T00:01:00Z")
        action["format"] = "json"
        self.assertTrue(validate_for_export(mapped, application, draft, action, policy=policy)["can_finalize"])
        application["revision"] += 1
        self.assertFalse(validate_for_export(mapped, application, draft, action, policy=policy)["can_finalize"])


if __name__ == "__main__":
    unittest.main()
