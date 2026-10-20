"""V1 application, upload, analysis, draft and export routes."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import logging
import os
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, File, Form, Header, UploadFile, status
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
    ErrorBody,
    ExportRequest,
    ExportResponse,
    UpdateApplicationRequest,
    UploadedDocument,
)
from ..services.agent import AgentIntegrationError, agent_service
from ..services.ocr import OcrProcessingError, ocr_service
from ..services.validation import ValidationIntegrationError, validation_service
from ..store import ApplicationRecord, UploadReceipt, store


router = APIRouter(tags=["Applications"])
logger = logging.getLogger(__name__)
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
SUPPORTED_MEDIA_TYPES = {"image/jpeg", "image/png", "application/pdf"}
ANALYSIS_WORKERS = max(1, int(os.getenv("CAREFUND_ANALYSIS_WORKERS", "2")))
analysis_executor = ThreadPoolExecutor(
    max_workers=ANALYSIS_WORKERS,
    thread_name_prefix="carefund-analysis",
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def get_record(application_id: str) -> ApplicationRecord:
    record = store.get(application_id)
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


def _job_failure(code: str, message: str) -> ErrorBody:
    return ErrorBody(code=code, message=message)


def _fail_analysis_job(application_id: str, job_id: str, code: str, message: str) -> None:
    lock = store.lock_for(application_id)
    with lock:
        record = store.get(application_id)
        if record is None or job_id not in record.jobs:
            return
        job = record.jobs[job_id]
        job.status = "failed"
        job.error = _job_failure(code, message)
        job.updated_at = now()
        store.save(record)


def _execute_analysis(
    application_id: str,
    job_id: str,
    application: Application,
    documents: list[UploadedDocument],
    evidence,
    candidate_facts,
    answers: dict[str, str],
) -> None:
    lock = store.lock_for(application_id)
    with lock:
        record = store.get(application_id)
        if record is None or job_id not in record.jobs:
            return
        job = record.jobs[job_id]
        if job.status != "queued":
            return
        job.status = "running"
        job.updated_at = now()
        store.save(record)

    try:
        facts, questions = agent_service.extract(
            application,
            documents,
            evidence,
            candidate_facts,
            answers,
        )
        validation = validation_service.validate(
            application,
            documents,
            evidence,
            facts,
            questions,
        )
    except AgentIntegrationError as exc:
        _fail_analysis_job(application_id, job_id, "AGENT_UNAVAILABLE", str(exc))
        return
    except ValidationIntegrationError as exc:
        _fail_analysis_job(application_id, job_id, "VALIDATION_FAILED", str(exc))
        return
    except Exception as exc:  # defensive boundary for a background worker
        logger.error("Analysis job %s failed with %s", job_id, type(exc).__name__)
        _fail_analysis_job(
            application_id,
            job_id,
            "INTERNAL_ERROR",
            "后台分析任务执行失败，请重试。",
        )
        return

    with lock:
        record = store.get(application_id)
        if record is None or job_id not in record.jobs:
            return
        job = record.jobs[job_id]
        if record.application.revision != application.revision:
            job.status = "failed"
            job.error = _job_failure(
                "STATE_CONFLICT",
                "申请已更新，本次旧版本分析结果未保存。",
            )
            job.updated_at = now()
            store.save(record)
            return
        record.facts = facts
        record.analysis = AnalysisResult(
            application_id=application_id,
            application_revision=application.revision,
            facts=facts,
            evidence=evidence,
            questions=questions,
            validation=validation,
        )
        record.application.status = "ready_for_draft" if validation.can_finalize else "reviewing"
        record.application.updated_at = now()
        job.status = "succeeded"
        job.error = None
        job.updated_at = now()
        store.save(record)


def queue_analysis(
    record: ApplicationRecord,
    idempotency_key: str,
    expected_revision: int | None = None,
) -> AnalysisJob:
    application_id = record.application.application_id
    lock = store.lock_for(application_id)
    with lock:
        current = get_record(application_id)
        if expected_revision is not None:
            require_revision(current, expected_revision)
        key = (current.application.revision, idempotency_key)
        existing_job_id = current.idempotency_jobs.get(key)
        if existing_job_id:
            return current.jobs[existing_job_id]

        timestamp = now()
        job = AnalysisJob(
            job_id=f"job_{uuid4().hex}",
            application_id=application_id,
            application_revision=current.application.revision,
            status="queued",
            created_at=timestamp,
            updated_at=timestamp,
        )
        current.jobs[job.job_id] = job
        current.idempotency_jobs[key] = job.job_id
        application_snapshot = current.application.model_copy(deep=True)
        documents_snapshot = [item.model_copy(deep=True) for item in current.documents]
        evidence_snapshot = [item.model_copy(deep=True) for item in current.evidence]
        facts_snapshot = [item.model_copy(deep=True) for item in current.facts]
        answers_snapshot = dict(current.answers)
        store.save(current)
        try:
            analysis_executor.submit(
                _execute_analysis,
                application_id,
                job.job_id,
                application_snapshot,
                documents_snapshot,
                evidence_snapshot,
                facts_snapshot,
                answers_snapshot,
            )
        except RuntimeError as exc:
            job.status = "failed"
            job.error = _job_failure("INTERNAL_ERROR", "后台执行器不可用。")
            job.updated_at = now()
            store.save(current)
            raise ApiError(500, "INTERNAL_ERROR", "Unable to queue analysis") from exc
        return job


def _process_upload(
    application_id: str,
    filename: str,
    media_type: str,
    content: bytes,
    expected_revision: int,
    idempotency_key: str,
) -> UploadedDocument:
    digest = sha256(content).hexdigest()
    lock = store.lock_for(application_id)
    with lock:
        record = get_record(application_id)
        receipt = record.upload_receipts.get(idempotency_key)
        if receipt is not None:
            if receipt.content_sha256 != digest:
                raise ApiError(
                    409,
                    "STATE_CONFLICT",
                    "Idempotency-Key was already used for different file content",
                )
            existing = next(
                (item for item in record.documents if item.document_id == receipt.document_id),
                None,
            )
            if existing is None:
                raise ApiError(500, "INTERNAL_ERROR", "Stored upload receipt is inconsistent")
            return existing

        require_revision(record, expected_revision)
        document = UploadedDocument(
            document_id=f"doc_{uuid4().hex}",
            application_id=application_id,
            filename=filename,
            media_type=media_type,
            size_bytes=len(content),
            uploaded_at=now(),
            processing_status="processed",
        )
        try:
            extracted_evidence = ocr_service.extract(document, content)
        except OcrProcessingError as exc:
            raise ApiError(422, "OCR_FAILED", str(exc)) from exc

        try:
            store.write_upload(document.document_id, content)
        except OSError as exc:
            raise ApiError(500, "INTERNAL_ERROR", "Unable to store uploaded file") from exc

        prior_revision = record.application.revision
        prior_status = record.application.status
        prior_updated_at = record.application.updated_at
        prior_analysis = record.analysis
        prior_draft_status = record.draft.status if record.draft else None
        evidence_count = len(record.evidence)
        record.documents.append(document)
        record.evidence.extend(extracted_evidence)
        record.upload_receipts[idempotency_key] = UploadReceipt(digest, document.document_id)
        record.application.revision += 1
        record.application.status = "collecting"
        record.application.updated_at = now()
        invalidate_derived_data(record)
        try:
            store.save(record)
        except Exception:
            record.documents.pop()
            del record.evidence[evidence_count:]
            record.upload_receipts.pop(idempotency_key, None)
            record.application.revision = prior_revision
            record.application.status = prior_status
            record.application.updated_at = prior_updated_at
            record.analysis = prior_analysis
            if record.draft and prior_draft_status:
                record.draft.status = prior_draft_status
            store.remove_upload(document.document_id)
            raise
        return document


@router.post(
    "/applications",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="create_application",
)
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
    store.add(record)
    return response(record)


@router.get(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    operation_id="get_application",
)
async def get_application(application_id: str) -> ApplicationResponse:
    return response(get_record(application_id))


@router.patch(
    "/applications/{application_id}",
    response_model=ApplicationResponse,
    operation_id="update_application",
)
async def update_application(application_id: str, payload: UpdateApplicationRequest) -> ApplicationResponse:
    lock = store.lock_for(application_id)
    with lock:
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
        store.save(record)
        return response(record)


@router.post(
    "/applications/{application_id}/documents",
    response_model=UploadedDocument,
    status_code=status.HTTP_201_CREATED,
    operation_id="upload_document",
)
async def upload_document(
    application_id: str,
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=128,
            pattern=r"^[A-Za-z0-9_-]+$",
        ),
    ],
    file: UploadFile = File(...),
    expected_revision: int = Form(..., ge=1),
) -> UploadedDocument:
    if file.content_type not in SUPPORTED_MEDIA_TYPES:
        raise ApiError(415, "UNSUPPORTED_FILE", "Only PDF, JPEG and PNG files are supported")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise ApiError(400, "INVALID_REQUEST", "Uploaded file is empty")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", "Uploaded file exceeds the 10 MiB limit")
    return await run_in_threadpool(
        _process_upload,
        application_id,
        file.filename or "upload",
        file.content_type,
        content,
        expected_revision,
        idempotency_key,
    )


@router.get(
    "/applications/{application_id}/documents",
    response_model=list[UploadedDocument],
    operation_id="list_documents",
)
async def list_documents(application_id: str) -> list[UploadedDocument]:
    return get_record(application_id).documents


@router.post(
    "/applications/{application_id}/analyze",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="start_analysis",
)
async def start_analysis(application_id: str, payload: AnalyzeRequest) -> AnalysisJob:
    record = get_record(application_id)
    return queue_analysis(record, payload.idempotency_key, payload.expected_revision)


@router.get(
    "/applications/{application_id}/analysis/jobs/{job_id}",
    response_model=AnalysisJob,
    operation_id="get_analysis_job",
)
async def get_analysis_job(application_id: str, job_id: str) -> AnalysisJob:
    record = get_record(application_id)
    job = record.jobs.get(job_id)
    if job is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "Analysis job not found")
    return job


@router.get(
    "/applications/{application_id}/analysis",
    response_model=AnalysisResult,
    operation_id="get_latest_analysis",
)
async def get_latest_analysis(application_id: str) -> AnalysisResult:
    record = get_record(application_id)
    if record.analysis is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "No current analysis result")
    if record.analysis.application_revision != record.application.revision:
        raise ApiError(409, "STATE_CONFLICT", "Analysis result is stale")
    return record.analysis


@router.post(
    "/applications/{application_id}/answers",
    response_model=AnalysisJob,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="submit_answers",
)
async def submit_answers(application_id: str, payload: AnswerSubmissionRequest) -> AnalysisJob:
    lock = store.lock_for(application_id)
    with lock:
        record = get_record(application_id)
        require_revision(record, payload.expected_revision)
        record.answers.update({answer.question_id: answer.answer for answer in payload.answers})
        for answer in payload.answers:
            if answer.question_id == "question_medical_summary":
                record.application.patient_info.medical_summary = answer.answer
        record.application.revision += 1
        record.application.updated_at = now()
        invalidate_derived_data(record)
        store.save(record)
        return queue_analysis(
            record,
            f"answers_{uuid4().hex}",
            record.application.revision,
        )


@router.post(
    "/applications/{application_id}/draft",
    response_model=Draft,
    status_code=status.HTTP_201_CREATED,
    operation_id="generate_draft",
)
async def generate_draft(application_id: str, payload: DraftGenerationRequest) -> Draft:
    lock = store.lock_for(application_id)
    with lock:
        record = get_record(application_id)
        require_revision(record, payload.expected_revision)
        analysis = record.analysis
        if (
            analysis is None
            or analysis.application_revision != record.application.revision
            or not analysis.validation.can_finalize
            or any(issue.severity == "blocking" for issue in analysis.validation.issues)
        ):
            raise ApiError(422, "VALIDATION_FAILED", "Current application is not ready for draft generation")
        application_snapshot = record.application.model_copy(deep=True)
        facts_snapshot = [item.model_copy(deep=True) for item in analysis.facts]
        issues_snapshot = [item.model_copy(deep=True) for item in analysis.validation.issues]
        prior_draft_revision = 0 if record.draft is None else record.draft.draft_revision

    try:
        sections = await run_in_threadpool(
            agent_service.draft_sections,
            application_snapshot,
            facts_snapshot,
            issues_snapshot,
        )
    except AgentIntegrationError as exc:
        raise ApiError(503, "AGENT_UNAVAILABLE", str(exc)) from exc

    with lock:
        record = get_record(application_id)
        if record.application.revision != application_snapshot.revision:
            raise ApiError(409, "STATE_CONFLICT", "Application changed during draft generation")
        record.draft = Draft(
            draft_id=f"draft_{uuid4().hex}",
            application_id=application_id,
            application_revision=record.application.revision,
            draft_revision=prior_draft_revision + 1,
            status="generated",
            sections=sections,
            created_at=now(),
        )
        record.application.status = "draft_ready"
        record.application.updated_at = now()
        store.save(record)
        return record.draft


@router.get(
    "/applications/{application_id}/draft",
    response_model=Draft,
    operation_id="get_latest_draft",
)
async def get_latest_draft(application_id: str) -> Draft:
    record = get_record(application_id)
    if record.draft is None:
        raise ApiError(404, "RESOURCE_NOT_FOUND", "No draft found")
    return record.draft


@router.post(
    "/applications/{application_id}/draft/confirm",
    response_model=Draft,
    operation_id="confirm_draft",
)
async def confirm_draft(application_id: str, payload: DraftConfirmationRequest) -> Draft:
    lock = store.lock_for(application_id)
    with lock:
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
            or record.analysis.application_revision != record.application.revision
            or not record.analysis.validation.can_finalize
        ):
            raise ApiError(409, "STATE_CONFLICT", "Draft is stale or cannot be confirmed")
        application_snapshot = record.application.model_copy(deep=True)
        documents_snapshot = [item.model_copy(deep=True) for item in record.documents]
        evidence_snapshot = [item.model_copy(deep=True) for item in record.evidence]
        facts_snapshot = [item.model_copy(deep=True) for item in record.facts]
        draft_snapshot = draft.model_copy(deep=True)

    try:
        final_validation = await run_in_threadpool(
            validation_service.validate_confirmation,
            application_snapshot,
            documents_snapshot,
            evidence_snapshot,
            facts_snapshot,
            draft_snapshot,
            payload,
        )
    except ValidationIntegrationError as exc:
        raise ApiError(422, "VALIDATION_FAILED", str(exc)) from exc

    with lock:
        record = get_record(application_id)
        draft = record.draft
        if (
            record.application.revision != application_snapshot.revision
            or draft is None
            or draft.draft_id != draft_snapshot.draft_id
            or draft.draft_revision != draft_snapshot.draft_revision
            or draft.status != "generated"
        ):
            raise ApiError(409, "STATE_CONFLICT", "Application changed during confirmation")
        if not final_validation.can_finalize:
            raise ApiError(422, "VALIDATION_FAILED", "Draft failed confirmation validation")
        draft.status = "confirmed"
        draft.confirmed_at = now()
        record.application.status = "confirmed"
        record.application.updated_at = now()
        store.save(record)
        return draft


@router.post(
    "/applications/{application_id}/export",
    response_model=ExportResponse,
    operation_id="export_application",
)
async def export_application(application_id: str, payload: ExportRequest) -> ExportResponse:
    lock = store.lock_for(application_id)
    with lock:
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
            or record.analysis.application_revision != record.application.revision
            or not record.analysis.validation.can_finalize
        ):
            raise ApiError(422, "EXPORT_BLOCKED", "A current confirmed and validated draft is required")
        application_snapshot = record.application.model_copy(deep=True)
        documents_snapshot = [item.model_copy(deep=True) for item in record.documents]
        evidence_snapshot = [item.model_copy(deep=True) for item in record.evidence]
        facts_snapshot = [item.model_copy(deep=True) for item in record.facts]
        draft_snapshot = draft.model_copy(deep=True)

    try:
        final_validation = await run_in_threadpool(
            validation_service.validate_export,
            application_snapshot,
            documents_snapshot,
            evidence_snapshot,
            facts_snapshot,
            draft_snapshot,
            payload,
        )
    except ValidationIntegrationError as exc:
        raise ApiError(422, "EXPORT_BLOCKED", str(exc)) from exc

    with lock:
        record = get_record(application_id)
        draft = record.draft
        if (
            record.application.revision != application_snapshot.revision
            or draft is None
            or draft.draft_id != draft_snapshot.draft_id
            or draft.draft_revision != draft_snapshot.draft_revision
            or draft.status != "confirmed"
        ):
            raise ApiError(409, "STATE_CONFLICT", "Application changed during export")
        if not final_validation.can_finalize:
            raise ApiError(422, "EXPORT_BLOCKED", "Draft failed export validation")
        record.application.status = "exported"
        record.application.updated_at = now()
        store.save(record)
        return ExportResponse(
            export_id=f"export_{uuid4().hex}",
            application_id=application_id,
            draft_id=draft.draft_id,
            created_at=now(),
            download_url=None,
        )
