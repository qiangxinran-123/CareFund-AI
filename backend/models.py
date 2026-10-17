"""Pydantic models mirroring the stable V1 contracts used by the backend."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{2,127}$")]
FieldName = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_.]{1,127}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatientInfo(StrictModel):
    display_name: Annotated[str, Field(min_length=1, max_length=100)]
    age_group: Literal["child", "adult", "older_adult", "unknown"] | None = None
    medical_summary: Annotated[str, Field(min_length=1, max_length=2000)] | None


class PatientInfoPatch(StrictModel):
    display_name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    age_group: Literal["child", "adult", "older_adult", "unknown"] | None = None
    medical_summary: Annotated[str, Field(min_length=1, max_length=2000)] | None = None

    @model_validator(mode="before")
    @classmethod
    def require_at_least_one_field(cls, data: object) -> object:
        if not isinstance(data, dict) or not data:
            raise ValueError("patient_info must contain at least one field")
        return data


class Application(StrictModel):
    application_id: Identifier
    schema_version: Literal["1.0"] = "1.0"
    revision: Annotated[int, Field(ge=1)]
    status: Literal[
        "collecting", "reviewing", "ready_for_draft", "draft_ready", "confirmed", "exported"
    ]
    patient_info: PatientInfo
    created_at: datetime
    updated_at: datetime


class CreateApplicationRequest(StrictModel):
    patient_info: PatientInfo


class UpdateApplicationRequest(StrictModel):
    expected_revision: Annotated[int, Field(ge=1)]
    patient_info: PatientInfoPatch


class UploadedDocument(StrictModel):
    document_id: Identifier
    application_id: Identifier
    filename: Annotated[str, Field(min_length=1, max_length=255)]
    media_type: Literal["image/jpeg", "image/png", "application/pdf"]
    size_bytes: Annotated[int, Field(ge=1)]
    uploaded_at: datetime
    processing_status: Literal["uploaded", "processing", "processed", "failed"]


class Evidence(StrictModel):
    evidence_id: Identifier
    document_id: Identifier
    source_type: Literal["document"] = "document"
    page: Annotated[int, Field(ge=1)] | None
    text_excerpt: Annotated[str, Field(min_length=1, max_length=2000)]
    extraction_method: Literal["ocr", "manual", "structured_import"]


class ApplicationResponse(StrictModel):
    application: Application
    documents: list[UploadedDocument] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class TextValue(StrictModel):
    kind: Literal["text"] = "text"
    value: Annotated[str, Field(min_length=1, max_length=5000)]


class DateValue(StrictModel):
    kind: Literal["date"] = "date"
    value: str


class BooleanValue(StrictModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class IntegerValue(StrictModel):
    kind: Literal["integer"] = "integer"
    value: int


class Money(StrictModel):
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    amount_minor: Annotated[int, Field(ge=0)]


class MoneyValue(StrictModel):
    kind: Literal["money"] = "money"
    value: Money


FactValue = Annotated[
    TextValue | DateValue | BooleanValue | IntegerValue | MoneyValue,
    Field(discriminator="kind"),
]


class Fact(StrictModel):
    fact_id: Identifier
    field: FieldName
    value: FactValue
    source_type: Literal["user_input", "document", "user_correction"]
    evidence_ids: list[Identifier] = Field(default_factory=list)
    verification_status: Literal["pending", "supported", "unsupported", "conflicting"]
    user_confirmed: bool


class AgentQuestion(StrictModel):
    question_id: Identifier
    field: FieldName
    question: Annotated[str, Field(min_length=1, max_length=500)]
    reason: Annotated[str, Field(min_length=1, max_length=500)]
    required: bool


class ValidationIssue(StrictModel):
    issue_id: Identifier
    type: Literal[
        "missing", "conflict", "unsupported", "invalid_format", "inconsistent_amount", "inconsistent_date"
    ]
    severity: Literal["info", "warning", "blocking"]
    field: FieldName
    message: Annotated[str, Field(min_length=1, max_length=1000)]
    related_fact_ids: list[Identifier] = Field(default_factory=list)


class ValidationResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    validation_id: Identifier
    application_id: Identifier
    application_revision: Annotated[int, Field(ge=1)]
    issues: list[ValidationIssue] = Field(default_factory=list)
    can_finalize: bool
    evaluated_at: datetime


class AnalysisResult(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    application_id: Identifier
    application_revision: Annotated[int, Field(ge=1)]
    facts: list[Fact] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    questions: list[AgentQuestion] = Field(default_factory=list)
    validation: ValidationResult


class AnalyzeRequest(StrictModel):
    expected_revision: Annotated[int, Field(ge=1)]
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")]


class Answer(StrictModel):
    question_id: Identifier
    answer: Annotated[str, Field(min_length=1, max_length=2000)]


class AnswerSubmissionRequest(StrictModel):
    expected_revision: Annotated[int, Field(ge=1)]
    answers: Annotated[list[Answer], Field(min_length=1)]


class ErrorBody(StrictModel):
    code: Literal[
        "INVALID_REQUEST", "RESOURCE_NOT_FOUND", "UNSUPPORTED_FILE", "FILE_TOO_LARGE",
        "OCR_FAILED", "AGENT_UNAVAILABLE", "VALIDATION_FAILED", "STATE_CONFLICT",
        "EXPORT_BLOCKED", "INTERNAL_ERROR",
    ]
    message: str
    details: list[dict[str, object]] = Field(default_factory=list)


class AnalysisJob(StrictModel):
    job_id: Identifier
    application_id: Identifier
    application_revision: Annotated[int, Field(ge=1)]
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    updated_at: datetime
    error: ErrorBody | None = None


class DraftSection(StrictModel):
    section_id: Identifier
    title: Annotated[str, Field(min_length=1, max_length=200)]
    content: Annotated[str, Field(min_length=1, max_length=10000)]
    fact_ids: list[Identifier] = Field(default_factory=list)


class Draft(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    draft_id: Identifier
    application_id: Identifier
    application_revision: Annotated[int, Field(ge=1)]
    draft_revision: Annotated[int, Field(ge=1)]
    status: Literal["generated", "confirmed", "stale"]
    sections: Annotated[list[DraftSection], Field(min_length=1)]
    created_at: datetime
    confirmed_at: datetime | None = None


class DraftGenerationRequest(StrictModel):
    expected_revision: Annotated[int, Field(ge=1)]


class DraftConfirmationRequest(StrictModel):
    draft_id: Identifier
    draft_revision: Annotated[int, Field(ge=1)]
    expected_application_revision: Annotated[int, Field(ge=1)]


class ExportRequest(StrictModel):
    draft_id: Identifier
    draft_revision: Annotated[int, Field(ge=1)]
    expected_application_revision: Annotated[int, Field(ge=1)]
    format: Literal["json"]


class ExportResponse(StrictModel):
    export_id: Identifier
    application_id: Identifier
    draft_id: Identifier
    format: Literal["json"] = "json"
    created_at: datetime
    download_url: HttpUrl | None = None


class HealthResponse(StrictModel):
    status: Literal["ok"] = "ok"
    schema_version: Literal["1.0"] = "1.0"
    time: datetime

