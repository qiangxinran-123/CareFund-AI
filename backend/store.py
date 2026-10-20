"""Local persistent repository for the single-machine demo.

The public repository boundary stays deliberately small so routes do not need
to know about SQLite. Application state is stored as contract-shaped JSON in
SQLite, while uploaded file bytes live in a controlled local directory.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
from threading import RLock
from uuid import uuid4

from .models import (
    AnalysisJob,
    AnalysisResult,
    Application,
    Draft,
    ErrorBody,
    Evidence,
    Fact,
    UploadedDocument,
)


@dataclass(frozen=True)
class UploadReceipt:
    content_sha256: str
    document_id: str


@dataclass
class ApplicationRecord:
    application: Application
    documents: list[UploadedDocument] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    jobs: dict[str, AnalysisJob] = field(default_factory=dict)
    idempotency_jobs: dict[tuple[int, str], str] = field(default_factory=dict)
    upload_receipts: dict[str, UploadReceipt] = field(default_factory=dict)
    analysis: AnalysisResult | None = None
    draft: Draft | None = None
    answers: dict[str, str] = field(default_factory=dict)


class PersistentStore:
    """SQLite-backed store with per-application mutation locks."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        configured = data_dir or os.getenv("CAREFUND_DATA_DIR")
        self.data_dir = (
            Path(configured).expanduser().resolve()
            if configured
            else (Path(__file__).resolve().parent / "instance")
        )
        self.upload_dir = self.data_dir / "uploads"
        self.db_path = self.data_dir / "carefund.sqlite3"
        self._lock = RLock()
        self._record_locks: dict[str, RLock] = {}
        self.applications: dict[str, ApplicationRecord] = {}
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
        self._load()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize_database(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS application_records (
                    application_id TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _serialize(record: ApplicationRecord) -> str:
        payload = {
            "application": record.application.model_dump(mode="json"),
            "documents": [item.model_dump(mode="json") for item in record.documents],
            "evidence": [item.model_dump(mode="json") for item in record.evidence],
            "facts": [item.model_dump(mode="json") for item in record.facts],
            "jobs": {
                key: value.model_dump(mode="json") for key, value in record.jobs.items()
            },
            "idempotency_jobs": [
                {"revision": revision, "key": key, "job_id": job_id}
                for (revision, key), job_id in record.idempotency_jobs.items()
            ],
            "upload_receipts": {
                key: {
                    "content_sha256": value.content_sha256,
                    "document_id": value.document_id,
                }
                for key, value in record.upload_receipts.items()
            },
            "analysis": record.analysis.model_dump(mode="json") if record.analysis else None,
            "draft": record.draft.model_dump(mode="json") if record.draft else None,
            "answers": record.answers,
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _deserialize(payload_json: str) -> ApplicationRecord:
        payload = json.loads(payload_json)
        return ApplicationRecord(
            application=Application.model_validate(payload["application"]),
            documents=[UploadedDocument.model_validate(item) for item in payload["documents"]],
            evidence=[Evidence.model_validate(item) for item in payload["evidence"]],
            facts=[Fact.model_validate(item) for item in payload["facts"]],
            jobs={
                key: AnalysisJob.model_validate(value)
                for key, value in payload.get("jobs", {}).items()
            },
            idempotency_jobs={
                (item["revision"], item["key"]): item["job_id"]
                for item in payload.get("idempotency_jobs", [])
            },
            upload_receipts={
                key: UploadReceipt(**value)
                for key, value in payload.get("upload_receipts", {}).items()
            },
            analysis=(
                AnalysisResult.model_validate(payload["analysis"])
                if payload.get("analysis")
                else None
            ),
            draft=Draft.model_validate(payload["draft"]) if payload.get("draft") else None,
            answers=dict(payload.get("answers", {})),
        )

    def _load(self) -> None:
        recovered: list[ApplicationRecord] = []
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT application_id, payload_json FROM application_records"
            ).fetchall()
        with self._lock:
            for application_id, payload_json in rows:
                record = self._deserialize(payload_json)
                self.applications[application_id] = record
                self._record_locks.setdefault(application_id, RLock())
                interrupted = False
                for job in record.jobs.values():
                    if job.status in {"queued", "running"}:
                        job.status = "failed"
                        job.error = ErrorBody(
                            code="INTERNAL_ERROR",
                            message="分析任务因服务重启中断，请重新发起分析。",
                        )
                        job.updated_at = datetime.now(timezone.utc)
                        interrupted = True
                if interrupted:
                    recovered.append(record)
        for record in recovered:
            self.save(record)

    def lock_for(self, application_id: str) -> RLock:
        with self._lock:
            return self._record_locks.setdefault(application_id, RLock())

    def get(self, application_id: str) -> ApplicationRecord | None:
        with self._lock:
            return self.applications.get(application_id)

    def add(self, record: ApplicationRecord) -> None:
        application_id = record.application.application_id
        with self._lock:
            self.applications[application_id] = record
            self._record_locks.setdefault(application_id, RLock())
        self.save(record)

    def save(self, record: ApplicationRecord) -> None:
        payload_json = self._serialize(record)
        application_id = record.application.application_id
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO application_records(application_id, payload_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(application_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (application_id, payload_json, datetime.now(timezone.utc).isoformat()),
            )

    def upload_path(self, document_id: str) -> Path:
        return self.upload_dir / f"{document_id}.bin"

    def write_upload(self, document_id: str, content: bytes) -> Path:
        destination = self.upload_path(document_id)
        temporary = self.upload_dir / f".{document_id}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
        return destination

    def remove_upload(self, document_id: str) -> None:
        self.upload_path(document_id).unlink(missing_ok=True)

    def clear(self) -> None:
        """Clear runtime state. Intended for tests and explicit local reset only."""
        with self._lock, self._connect() as connection:
            connection.execute("DELETE FROM application_records")
            self.applications.clear()
            self._record_locks.clear()
        if self.upload_dir.exists():
            shutil.rmtree(self.upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)


store = PersistentStore()
