"""Adapter between Backend models and D's deterministic validation module."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

from ..models import (
    AgentQuestion,
    Application,
    Draft,
    DraftConfirmationRequest,
    Evidence,
    ExportRequest,
    Fact,
    UploadedDocument,
    ValidationIssue,
    ValidationResult,
)


class ValidationIntegrationError(RuntimeError):
    """Safe backend-facing error for malformed validation integration calls."""


class MockValidationService:
    def validate(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
        questions: list[AgentQuestion],
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

    def validate_confirmation(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
        draft: Draft,
        request: DraftConfirmationRequest,
    ) -> ValidationResult:
        return self.validate(application, documents, evidence, facts, [])

    def validate_export(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
        draft: Draft,
        request: ExportRequest,
    ) -> ValidationResult:
        return self.validate(application, documents, evidence, facts, [])


class RealValidationService:
    def __init__(self) -> None:
        self._policy = self._load_policy()

    @staticmethod
    def _load_policy():
        policy_path = os.getenv("CAREFUND_VALIDATION_POLICY")
        if not policy_path:
            return None
        try:
            from validation import ValidationPolicy

            value = json.loads(Path(policy_path).read_text(encoding="utf-8"))
            return ValidationPolicy.from_dict(value)
        except (ImportError, OSError, ValueError, json.JSONDecodeError) as exc:
            raise RuntimeError("无法加载 CAREFUND_VALIDATION_POLICY") from exc

    @staticmethod
    def _request(
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
    ) -> dict:
        return {
            "schema_version": "1.0",
            "application_id": application.application_id,
            "application_revision": application.revision,
            "documents": [item.model_dump(mode="json") for item in documents],
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "facts": [item.model_dump(mode="json") for item in facts],
        }

    def validate(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
        questions: list[AgentQuestion],
    ) -> ValidationResult:
        try:
            from validation import ContractValidationError, validate

            result = validate(
                self._request(application, documents, evidence, facts),
                policy=self._policy,
            )
        except (ImportError, ValueError) as exc:
            raise ValidationIntegrationError("校验模块拒绝了当前数据结构") from exc
        return ValidationResult.model_validate(result)

    def validate_confirmation(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
        draft: Draft,
        request: DraftConfirmationRequest,
    ) -> ValidationResult:
        try:
            from validation import ContractValidationError, validate_for_confirmation

            result = validate_for_confirmation(
                self._request(application, documents, evidence, facts),
                application.model_dump(mode="json"),
                draft.model_dump(mode="json"),
                request.model_dump(mode="json"),
                policy=self._policy,
            )
        except (ImportError, ValueError) as exc:
            raise ValidationIntegrationError("确认前校验失败") from exc
        return ValidationResult.model_validate(result)

    def validate_export(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        facts: list[Fact],
        draft: Draft,
        request: ExportRequest,
    ) -> ValidationResult:
        try:
            from validation import ContractValidationError, validate_for_export

            result = validate_for_export(
                self._request(application, documents, evidence, facts),
                application.model_dump(mode="json"),
                draft.model_dump(mode="json"),
                request.model_dump(mode="json"),
                policy=self._policy,
            )
        except (ImportError, ValueError) as exc:
            raise ValidationIntegrationError("导出前校验失败") from exc
        return ValidationResult.model_validate(result)


def build_validation_service():
    mode = os.getenv("CAREFUND_VALIDATION_MODE", "real").lower()
    if mode == "mock":
        return MockValidationService()
    if mode != "real":
        raise RuntimeError("CAREFUND_VALIDATION_MODE must be 'real' or 'mock'")
    return RealValidationService()


validation_service = build_validation_service()

