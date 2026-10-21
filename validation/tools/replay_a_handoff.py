"""Reproduce A/D checks from the unmodified synthetic handoff fixtures."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from validation.tests.fixture_integrity import original_fixture_bytes

from validation import build_validation_request, prepare_agent_draft_request, validate, validate_agent_draft
from validation.rules.agent_literal import matches_literal_sections
from validation.tests.test_agent_adapter import (
    CASES, FIXTURES, document_only_demo, extract_pair, handoff_policy, read, service,
)


def run(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    provenance = read("PROVENANCE.json")
    for entry in provenance["files"]:
        content = original_fixture_bytes(FIXTURES, entry)
        if len(content) != entry["bytes"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError("Original A fixture hash mismatch.")

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "mode": "offline_replay_no_network",
        "source_commit": provenance["source_commit"],
        "source_zip_sha256": provenance["source_zip_sha256"],
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "policy": "validation/examples/policy.a-handoff-demo.json (illustrative, not team-approved business rules)",
        "extract_cases": [], "saved_draft_cases": [],
    }
    for name in CASES:
        request, response = extract_pair(name)
        before = deepcopy((request, response))
        actual = service(lambda op, payload: deepcopy(response)).extract(request)
        mapped = build_validation_request(request, actual)
        if mapped != read(f"adaptation_cases/{name}.validation-request.json"):
            raise ValueError("Mapped request differs from A handoff.")
        report = validate(mapped, policy=handoff_policy())
        if (request, response) != before:
            raise ValueError("Input mutation during adaptation.")
        save(name + ".validation-request.json", mapped)
        save(name + ".validation-result.json", report)
        summary["extract_cases"].append({
            "case": name, "a_boundary_replay": "passed", "mapping_matches_handoff": True,
            "input_unchanged": True, "can_finalize": report["can_finalize"],
            "issues_by_severity": {level: sum(i["severity"] == level for i in report["issues"]) for level in ("blocking", "warning", "info")},
            "issue_types": sorted({i["type"] for i in report["issues"]}),
            "validation_result": name + ".validation-result.json",
        })
    for name in ("draft-request", "draft-uncertain-request", "draft-injection-request"):
        request = read(f"agent/verification/draft/{name}.request.json")
        response = read(f"agent/verification/draft/{name}.response.json")
        actual = service(lambda op, payload: deepcopy(response)).draft(request)
        # A's draft payload does NOT contain original documents/evidence. Do not
        # invent those missing objects or pretend this is a complete B snapshot.
        incomplete = {key: request[key] for key in ("schema_version", "application_id", "application_revision")}
        incomplete.update(documents=[], evidence=[], facts=deepcopy(request["candidate_facts"]))
        report = validate_agent_draft(incomplete, actual, policy=handoff_policy())
        save(name + ".candidate-validation-result.json", report)
        summary["saved_draft_cases"].append({
            "case": name, "a_boundary_replay": "passed",
            "literal_format_compatible": matches_literal_sections(request["candidate_facts"], actual["candidate_sections"]),
            "d_input": "incomplete: source draft request has no document/evidence snapshot",
            "can_finalize": report["can_finalize"],
            "validation_result": name + ".candidate-validation-result.json",
        })

    # Constructed Mock state, explicitly separate from all saved live responses.
    current, policy = document_only_demo()
    draft_request, report = prepare_agent_draft_request(current, policy=policy)
    eligible = service(None).validate_draft_request(draft_request)
    summary["constructed_document_only_mock"] = {
        "data_origin": "derived synthetic test snapshot; user confirmation is simulated only in this test",
        "d_can_finalize": report["can_finalize"], "a_draft_gate": "passed",
        "eligible_fact_count": len(eligible), "verification_status_preserved": "pending",
    }
    user_fact = {
        "fact_id": "fact_info_gate_demo", "field": "patient.medical_summary",
        "value": {"kind": "text", "value": "虚构演示：仍在检查，尚未确诊。"},
        "source_type": "user_input", "evidence_ids": [],
        "verification_status": "pending", "user_confirmed": True,
    }
    current["facts"].append(user_fact)
    draft_request, report = prepare_agent_draft_request(current, policy=policy)
    summary["info_gate_compatibility"] = {
        "d_can_finalize": report["can_finalize"],
        "all_issue_ids_preserved": draft_request["validation_issue_ids"] == [item["issue_id"] for item in report["issues"]],
        "a_current_behavior": "blocks every nonempty validation_issue_ids list, including info",
        "status": "requires A/B/D agreement before relaxing; no IDs dropped",
    }
    save("summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run(args.output)
    print(json.dumps({"extract_replayed": len(summary["extract_cases"]), "draft_replayed": len(summary["saved_draft_cases"]), "online_calls": 0, "report": str(args.output / "summary.json")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
