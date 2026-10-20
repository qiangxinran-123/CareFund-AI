"""Replay the 2026-10-18 A ZIP's 27 synthetic cases; no API or private CSV."""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
from unittest.mock import Mock, patch

from validation import build_validation_request, validate, validate_agent_draft
from validation.rules import ValidationPolicy
from validation.rules.agent_literal import matches_literal_sections
from validation.schema import check_model
from validation.tests.fixtures.a_20261018.agent.agent_service import AgentService, AgentError

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "validation/tests/fixtures/a_20261018"


def read(relative):
    return json.loads((FIXTURE / relative).read_text(encoding="utf-8"))


def service(runner):
    return AgentService(runner, schema_dir=ROOT / "contracts/schemas")


def evaluate() -> tuple[dict, dict]:
    provenance = read("PROVENANCE.json")
    for item in provenance["files"]:
        content = (FIXTURE / item["path"]).read_bytes()
        if len(content) != item["bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("Latest A fixture fingerprint mismatch.")
    suite = read("agent/verification/content-review-20261017/synthetic-replay.json")
    if suite["data_class"] != "synthetic_only" or len(suite["cases"]) != 27:
        raise ValueError("Expected the 27 shareable synthetic cases.")
    policy = ValidationPolicy.from_dict(json.loads(
        (ROOT / "validation/examples/policy.a-handoff-demo.json").read_text(encoding="utf-8"),
    ))
    counts, cases, artifacts = Counter(), [], {}
    with patch.object(socket, "socket", side_effect=AssertionError("Network forbidden in offline A/D replay")):
        for entry in suite["cases"]:
            case, raw = entry["case"], entry["response"]
            before = deepcopy(entry)
            if case["data_class"] != "synthetic":
                raise ValueError("Private case is not permitted in shareable replay.")
            canonical = json.dumps({"case": case, "response": raw}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            if hashlib.sha256(canonical).hexdigest() != entry["payload_sha256"]:
                raise ValueError("Saved case fingerprint mismatch.")
            request = case["request"]
            runner = Mock(return_value=deepcopy(raw))
            a_service = service(runner)
            item = {"review_id": entry["review_id"], "operation": case["operation"]}
            if case["operation"] == "extract":
                rendered = a_service.extract(request)
                runner.assert_called_once()
                if rendered["candidate_facts"] != raw["candidate_facts"] or a_service.last_extract_raw_response != raw:
                    raise ValueError("A presentation changed the facts or raw audit snapshot.")
                mapped = build_validation_request(request, rendered)
                report = validate(mapped, policy=policy)
                counts["extract_mapped_facts_unchanged"] += 1
                item.update(a_boundary="passed", facts_unchanged=True,
                            public_questions=len(rendered["questions"]),
                            input_snapshot="complete extraction request")
                artifacts[entry["review_id"] + ".validation-request.json"] = mapped
            else:
                # Draft inputs do not carry original evidence. Preserve this
                # known gap, rather than fabricate a document or claim export.
                mapped = {key: request[key] for key in ("schema_version", "application_id", "application_revision")}
                mapped.update(documents=[], evidence=[], facts=deepcopy(request["candidate_facts"]))
                try:
                    rendered = a_service.draft(request)
                except AgentError:
                    runner.assert_not_called()
                    if entry["review_id"] != "S014":
                        raise
                    counts["a_instruction_blocked_before_runner"] += 1
                    report = validate_agent_draft(mapped, raw, policy=policy)
                    if report["can_finalize"] or not any("指令" in problem["message"] for problem in report["issues"]):
                        raise ValueError("D failed to block the instruction-bearing candidate independently.")
                    counts["d_instruction_blocked"] += 1
                    item.update(a_boundary="instruction rejected before runner", d_instruction_blocked=True)
                else:
                    runner.assert_called_once()
                    if not matches_literal_sections(mapped["facts"], rendered["candidate_sections"]):
                        raise ValueError("A/D literal layout disagreement.")
                    report = validate_agent_draft(mapped, rendered, policy=policy)
                    counts["eligible_draft_layout_compatible"] += 1
                    item.update(a_boundary="passed", literal_format_compatible=True)
                item["input_snapshot"] = "incomplete evidence: AgentDraftRequest has no documents/evidence"
            check_model(report, "validation.schema.json", "ValidationResult")
            known = {fact["fact_id"] for fact in mapped["facts"]}
            if any(set(problem["related_fact_ids"]) - known for problem in report["issues"]):
                raise ValueError("D result referenced an unknown Fact.")
            if report["application_revision"] != mapped["application_revision"] or entry != before:
                raise ValueError("Revision mismatch or input mutation.")
            counts["d_results_schema_and_references_valid"] += 1
            item.update(can_finalize=report["can_finalize"], input_unchanged=True,
                        issues_by_severity=dict(Counter(problem["severity"] for problem in report["issues"])),
                        issue_types=sorted({problem["type"] for problem in report["issues"]}))
            artifacts[entry["review_id"] + ".validation-result.json"] = report
            cases.append(item)
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "mode": "offline_synthetic_saved_response_replay", "new_api_calls": 0,
        "source_label": provenance["source_label"], "source_zip_sha256": provenance["source_zip_sha256"],
        "counts": dict(counts), "cases": cases,
        "policy": "illustrative only: policy.a-handoff-demo.json; not production acceptance",
        "limitations": ["No private 1341-response batch is available to reproduce here", "No clinical accuracy measurement", "No live Dify, real OCR, B transactions or front-end verification", "A still blocks all nonempty issue IDs; none filtered"],
    }, artifacts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary, artifacts = evaluate()
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in {**artifacts, "summary.json": summary}.items():
        (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"counts": summary["counts"], "new_api_calls": 0, "report": str(args.output / "summary.json")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
