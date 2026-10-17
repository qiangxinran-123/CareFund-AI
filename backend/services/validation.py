"""Validation adapter boundary with deterministic backend-owned finalization rules."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ..models import AgentQuestion, Application, Fact, ValidationIssue, ValidationResult


class MockValidationService:
    def validate(
        self, application: Application, facts: list[Fact], questions: list[AgentQuestion]
    ) -> ValidationResult:
        issues: list[ValidationIssue] = []
        if not application.patient_info.medical_summary:
            issues.append(
                ValidationIssue(
                    issue_id=f"issue_{uuid4().hex}",
                    type="missing",
                    severity="blocking",
                    field="patient.medical_summary",
                    message="缺少申请人提供的病情情况说明。",
                    related_fact_ids=[],
                )
            )
        for fact in facts:
            if fact.source_type == "user_input":
                issues.append(
                    ValidationIssue(
                        issue_id=f"issue_{uuid4().hex}",
                        type="unsupported",
                        severity="info",
                        field=fact.field,
                        message="该信息来自用户陈述，不代表已由证明材料核实。",
                        related_fact_ids=[fact.fact_id],
                    )
                )

        can_finalize = not questions and not any(issue.severity == "blocking" for issue in issues)
        return ValidationResult(
            validation_id=f"validation_{uuid4().hex}",
            application_id=application.application_id,
            application_revision=application.revision,
            issues=issues,
            can_finalize=can_finalize,
            evaluated_at=datetime.now(timezone.utc),
        )


validation_service = MockValidationService()

