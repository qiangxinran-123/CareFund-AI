"""Reproduce D's integration acceptance without credentials or model calls."""

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from validation import load_policy, prepare_agent_draft_request, validate_for_confirmation, validate_for_export
from validation.tests.test_demo_v1 import actions, formal_draft, scenario

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--with-backend", action="store_true", help="Requires backend and pytest dependencies")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    commands = [[sys.executable, "-B", "-m", "unittest", "contracts.tests.test_contracts",
                 "validation.tests.test_validation", "validation.tests.test_agent_adapter",
                 "validation.tests.test_latest_agent", "validation.tests.test_demo_v1", "-v"]]
    if args.with_backend:
        # B's API tests configure Mock globals at module-import time. Keep them
        # in their own process so collection order cannot leak a Real singleton.
        commands.append([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         "validation/integration_tests"])
        commands.append([sys.executable, "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider",
                         "backend/tests"])
    executed = []
    for index, command in enumerate(commands):
        process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        log = process.stdout + process.stderr
        name = ("validation-contract-tests.txt", "backend-integration-tests.txt", "backend-original-tests.txt")[index]
        (args.output / name).write_text(log, encoding="utf-8")
        match = re.search(r"Ran (\d+) tests|\b(\d+) passed", log)
        count = int(next(value for value in match.groups() if value)) if match else None
        executed.append({"command": " ".join(["python"] + command[1:]), "exit_code": process.returncode,
                         "tests_passed": count if process.returncode == 0 else None, "log": name})
        if process.returncode:
            print(log)
            raise SystemExit(process.returncode)
    policy = load_policy("demo_v1")
    cases = []
    for mode in ("clean", "info", "warning", "conflict", "stale", "invalid_reference"):
        app, request = scenario(mode)
        draft = formal_draft(app, request)
        confirm, export = actions(app, draft)
        if mode == "stale":
            app["revision"] += 1
        elif mode == "invalid_reference":
            request["facts"][1]["evidence_ids"] = ["ev_nonexistent"]
        prepared, report = prepare_agent_draft_request(
            request, policy=policy, application=app,
            generation_request={"expected_revision": app["revision"]},
        )
        current = dict(deepcopy(app), status="draft_ready")
        confirming = validate_for_confirmation(request, current, draft, confirm, policy=policy)
        current["status"] = "confirmed"
        stored = dict(deepcopy(draft), status="confirmed", confirmed_at="2026-10-20T00:02:00Z")
        exporting = validate_for_export(request, current, stored, export, policy=policy)
        expected = mode in ("clean", "info", "warning")
        if any(result["can_finalize"] != expected for result in (report, confirming, exporting)):
            raise AssertionError("Unexpected stage gate result for " + mode)
        cases.append({"case": mode, "data_class": "synthetic_only", "application": app,
                      "validation_request": request, "agent_draft_request": prepared,
                      "generation_validation": report, "confirmation_validation": confirming,
                      "export_validation": exporting, "expected_allowed": expected})
    (args.output / "scenarios.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "issues": ["INT-07", "INT-08"], "policy": "validation/policies/demo_v1.json",
        "new_api_calls": 0, "tests": executed,
        "acceptance_cases": [{"case": c["case"], "generate": c["generation_validation"]["can_finalize"],
                              "confirm": c["confirmation_validation"]["can_finalize"],
                              "export": c["export_validation"]["can_finalize"]} for c in cases],
        "backend_owner_action": "Load demo_v1 and use D's explicit blocking-ID mapping. Existing all-ID forwarding still rejects info; reproduced by test, not silently changed.",
        "not_verified": ["Human A/B agreement", "Live Dify/OCR/UI end-to-end", "Backend transactions and durable storage"],
    }
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"tests": [item["tests_passed"] for item in executed], "cases": len(cases),
                      "new_api_calls": 0, "report": str(args.output / "summary.json")}, ensure_ascii=True))


if __name__ == "__main__":
    main()
