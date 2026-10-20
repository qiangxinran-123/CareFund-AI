"""V1 application, upload, analysis, draft and export routes."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ..errors import ApiError
from ..models import (
    AnalysisJob,
    AnalysisResult,
    AnalyzeRequest,
    AnswerSubmissionRequest,
    Application,
    ApplicationResponse,
    CreateApplicationRequest,
    Draft,
    DraftConfirmationRequest,
    DraftGenerationRequest,
    ExportRequest,
    ExportResponse,
    UpdateApplicationRequest,
    UploadedDocument,
)
from ..services.agent import AgentIntegrationError, agent_service
from ..services.ocr import OcrProcessingError, ocr_service
from ..services.validation import ValidationIntegrationError, validation_service
from ..store import ApplicationRecord, store


router = APIRouter(tags=["Applications"])
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_record(application_id: str) -> ApplicationRecord:
    record = store.applications.get(application_id)
    if record is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Application not found")
    return record


def require_revision(record: ApplicationRecord, expected_revision: int) -> None:
    if record.application.revision != expected_revision:
        raise ApiError(
            409,
            "STATE_CONFLICT",
            "Application revision does not match expected_revision",
            [{"field": "expected_revision", "message": "stale revision", "value": expected_revision}],
        )


def response(record: ApplicationRecord) -> ApplicationResponse:
    return ApplicationResponse(
        application=record.application,
        documents=record.documents,
        evidence=record.evidence,
    )


def invalidate_derived_data(record: ApplicationRecord) -> None:
    record.analysis = None
    if record.draft:
        record.draft.status = "stale"


async def run_analysis(record: ApplicationRecord, idempotency_key: str) -> AnalysisJob:
    key = (record.application.revision, idempotency_key)
    existing_job_id = record.idempotency_jobs.get(key)
    if existing_job_id:
        return record.jobs[existing_job_id]

    timestamp = now()
    job = AnalysisJob(
        job_id=f"job_{uuid4().hex}",
        application_id=record.application.application_id,
        application_revision=record.application.revision,
        status="running",
        created_at=timestamp,
        updated_at=timestamp,
    )
    record.jobs[job.job_id] = job
    record.idempotency_jobs[key] = job.job_id

    try:
        facts, questions = await run_in_threadpool(
            agent_service.extract,
            record.application,
            record.documents,
            record.evidence,
            record.facts,
            record.answers,
        )
        validation = await run_in_threadpool(
            validation_service.validate,
            record.application,
            record.documents,
            record.evidence,
            facts,
            questions,
        )
    except AgentIntegrationError as exc:
        job.status = "failed"
        job.updated_at = now()
        raise ApiError(503, "AGENT_UNAVAILABLE", str(exc)) from exc
    except ValidationIntegrationError as exc:
        job.status = "failed"
        job.updated_at = now()
        raise ApiError(422, "VALIDATION_FAILED", str(exc)) from exc
    record.facts = facts
    record.analysis = AnalysisResult(
        application_id=record.application.application_id,
        application_revision=record.application.revision,
        facts=facts,
        evidence=record.evidence,
        questions=questions,
        validation=validation,
    )
    record.application.status = "ready_for_draft" if validation.can_finalize else "reviewing"
    record.application.updated_at = now()
    job.status = "succeeded"
    job.updated_at = now()
    return job


@router.post("/applications", response_model=ApplicationResponse, status_code=status.HTTP_201_CREATED)
async def create_application(payload: CreateApplicationRequest) -> ApplicationResponse:
    timestamp = now()
    application = Application(
        application_id=f"app_{uuid4().hex}",
        revision=1,
        status="collecting",
        patient_info=payload.patient_info,
        created_at=timestamp,
        updated_at=timestamp,
    )
    record = ApplicationRecord(application=application)
    store.applications[application.application_id] = record
    return response(record)


@router.get("/applications/{application_id}", response_model=ApplicationResponse)
async def get_application(application_id: str) -> ApplicationResponse:
    return response(get_record(application_id))


@router.patch("/applications/{application_id}", response_model=ApplicationResponse)
async def update_application(application_id: str, payload: UpdateApplicationRequest) -> ApplicationResponse:
    record = get_record(application_id)
    require_revision(record, payload.expected_revision)
    patch = payload.patient_info.model_dump(exclude_unset=True)
    current = record.application.patient_info.model_dump()
    current.update(patch)
    record.application.patient_info = type(record.application.patient_info)(**current)
    record.application.revision += 1
    record.application.status = "collecting"
    record.application.updated_at = now()
    invalidate_derived_data(record)
    return response(record)


@router.post(
    "/applications/{application_id}/documents",
    response_model=UploadedDocument,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    application_id: str,
    file: UploadFile = File(...),
    expected_revision: int = Form(..., ge=1),
) -> UploadedDocument:
    record = get_record(application_id)
    require_revision(record, expected_revision)
    if file.content_type not in SUPPORTED_MEDIA_TYPES:
        raise ApiError(415, "UNSUPPORTED_FILE", "Only PDF, JPEG and PNG files are supported")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise ApiError(400, "INVALID_REQUEST", "Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "Uploaded file exceeds the 10 MiB limit")

    document = UploadedDocument(
        document_id=f"doc_{uuid4().hex}",
        application_id=application_id,
        filename=file.filename or "upload",
        media_type=file.content_type,
        size_bytes=len(content),
        uploaded_at=now(),
        processing_status="processed",
    )
    try:
        extracted_evidence = await run_in_threadpool(ocr_service.extract, document, content)
    except OcrProcessingError as exc:
        raise ApiError(422, "OCR_FAILED", str(exc)) from exc
    record.documents.append(document)
    record.evidence.extend(extracted_evidence)
    record.application.revision += 1
    record.application.status = "collecting"
    record.application.updated_at = now()
    invalidate_derived_data(record)
    return document


@router.get("/applications/{application_id}/documents", response_model=list[UploadedDocument])
async def list_documents(application_id: str) -> list[UploadedDocument]:
    return get_record(application_id).documents


@router.post(
    "/applications/{application_id}/analyze",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_analysis(application_id: str, payload: AnalyzeRequest) -> AnalysisJob:
    record = get_record(application_id)
    require_revision(record, payload.expected_revision)
    return await run_analysis(record, payload.idempotency_key)


@router.get("/applications/{application_id}/analysis/jobs/{job_id}", response_model=AnalysisJob)
async def get_analysis_job(application_id: str, job_id: str) -> AnalysisJob:
    record = get_record(application_id)
    job = record.jobs.get(job_id)
    if job is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Analysis job not found")
    return job


@router.get("/applications/{application_id}/analysis", response_model=AnalysisResult)
async def get_latest_analysis(application_id: str) -> AnalysisResult:
    record = get_record(application_id)
    if record.analysis is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "No current analysis result")
    return record.analysis


@router.post(
    "/applications/{application_id}/answers",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit_answers(application_id: str, payload: AnswerSubmissionRequest) -> AnalysisJob:
    record = get_record(application_id)
    require_revision(record, payload.expected_revision)
    record.answers.update({answer.question_id: answer.answer for answer in payload.answers})
    for answer in payload.answers:
        if answer.question_id == "question_medical_summary":
            record.application.patient_info.medical_summary = answer.answer
    record.application.revision += 1
    record.application.updated_at = now()
    invalidate_derived_data(record)
    return await run_analysis(record, f"answers_{uuid4().hex}")


@router.post(
    "/applications/{application_id}/draft",
    response_model=Draft,
    status_code=status.HTTP_201_CREATED,
)
async def generate_draft(application_id: str, payload: DraftGenerationRequest) -> Draft:
    record = get_record(application_id)
    require_revision(record, payload.expected_revision)
    if record.analysis is None or not record.analysis.validation.can_finalize:
        raise ApiError(422, "VALIDATION_FAILED", "Current application is not ready for draft generation")
    draft_revision = 1 if record.draft is None else record.draft.draft_revision + 1
    try:
        sections = await run_in_threadpool(
            agent_service.draft_sections,
            record.application,
            record.analysis.facts,
            record.analysis.validation.issues,
        )
    except AgentIntegrationError as exc:
        raise ApiError(503, "AGENT_UNAVAILABLE", str(exc)) from exc
    record.draft = Draft(
        draft_id=f"draft_{uuid4().hex}",
        application_id=application_id,
        application_revision=record.application.revision,
        draft_revision=draft_revision,
        status="generated",
        sections=sections,
        created_at=now(),
    )
    record.application.status = "draft_ready"
    record.application.updated_at = now()
    return record.draft


@router.get("/applications/{application_id}/draft", response_model=Draft)
async def get_latest_draft(application_id: str) -> Draft:
    record = get_record(application_id)
    if record.draft is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "No draft found")
    return record.draft


@router.post("/applications/{application_id}/draft/confirm", response_model=Draft)
async def confirm_draft(application_id: str, payload: DraftConfirmationRequest) -> Draft:
    record = get_record(application_id)
    require_revision(record, payload.expected_application_revision)
    draft = record.draft
    if (
        draft is None
        or draft.draft_id != payload.draft_id
        or draft.draft_revision != payload.draft_revision
        or draft.application_revision != record.application.revision
        or draft.status != "generated"
        or record.analysis is None
        or not record.analysis.validation.can_finalize
    ):
        raise ApiError(409, "STATE_CONFLICT", "Draft is stale or cannot be confirmed")
    try:
        final_validation = await run_in_threadpool(
            validation_service.validate_confirmation,
            record.application,
            record.documents,
            record.evidence,
            record.facts,
            draft,
            payload,
        )
    except ValidationIntegrationError as exc:
        raise ApiError(422, "VALIDATION_FAILED", str(exc)) from exc
    if not final_validation.can_finalize:
        raise ApiError(422, "VALIDATION_FAILED", "Draft failed confirmation validation")
    draft.status = "confirmed"
    draft.confirmed_at = now()
    record.application.status = "confirmed"
    record.application.updated_at = now()
    return draft


@router.post("/applications/{application_id}/export", response_model=ExportResponse)
async def export_application(application_id: str, payload: ExportRequest) -> ExportResponse:
    record = get_record(application_id)
    require_revision(record, payload.expected_application_revision)
    draft = record.draft
    if (
        draft is None
        or draft.draft_id != payload.draft_id
        or draft.draft_revision != payload.draft_revision
        or draft.application_revision != record.application.revision
        or draft.status != "confirmed"
        or record.analysis is None
        or not record.analysis.validation.can_finalize
    ):
        raise ApiError(422, "EXPORT_BLOCKED", "A current confirmed and validated draft is required")
    try:
        final_validation = await run_in_threadpool(
            validation_service.validate_export,
            record.application,
            record.documents,
            record.evidence,
            record.facts,
            draft,
            payload,
        )
    except ValidationIntegrationError as exc:
        raise ApiError(422, "EXPORT_BLOCKED", str(exc)) from exc
    if not final_validation.can_finalize:
        raise ApiError(422, "EXPORT_BLOCKED", "Draft failed export validation")
    record.application.status = "exported"
    record.application.updated_at = now()
    return ExportResponse(
        export_id=f"export_{uuid4().hex}",
        application_id=application_id,
        draft_id=draft.draft_id,
        created_at=now(),
        download_url=None,
    )

