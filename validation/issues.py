"""Construct only fields and enums defined by ValidationIssue/Result."""

from datetime import datetime, timezone
from uuid import uuid4


def issue(kind: str, field: str, message: str, fact_ids=(), *, severity="blocking") -> dict:
    return {
        "issue_id": "issue_" + uuid4().hex,
        "type": kind,
        "severity": severity,
        "field": field,
        "message": message,
        "related_fact_ids": list(dict.fromkeys(fact_ids)),
    }


def result(request: dict, issues: list[dict]) -> dict:
    return {
        "schema_version": request["schema_version"],
        "validation_id": "validation_" + uuid4().hex,
        "application_id": request["application_id"],
        "application_revision": request["application_revision"],
        "issues": issues,
        "can_finalize": not any(item["severity"] == "blocking" for item in issues),
        "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
