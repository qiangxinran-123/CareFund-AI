import os
import time
from concurrent.futures import ThreadPoolExecutor

os.environ["CAREFUND_AGENT_MODE"] = "mock"
os.environ["CAREFUND_VALIDATION_MODE"] = "mock"

import pymupdf
from fastapi.testclient import TestClient

from backend.main import app
from backend.models import AnalysisJob
from backend.routes import applications as application_routes
from backend.services.agent import AgentIntegrationError
from backend.store import PersistentStore, store


client = TestClient(app)


def setup_function() -> None:
    store.clear()


def create_application(medical_summary: str | None = "这是由用户提供的合成测试病情说明。") -> dict:
    response = client.post(
        "/api/v1/applications",
        json={
            "patient_info": {
                "display_name": "合成测试用户",
                "age_group": "adult",
                "medical_summary": medical_summary,
            }
        },
    )
    assert response.status_code == 201
    return response.json()


def make_text_pdf(text: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def upload_headers(key: str = "upload_test_001") -> dict[str, str]:
    return {"Idempotency-Key": key}


def wait_for_job(application_id: str, job_id: str, timeout: float = 3.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(
            f"/api/v1/applications/{application_id}/analysis/jobs/{job_id}"
        )
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"succeeded", "failed"}:
            return body
        time.sleep(0.01)
    raise AssertionError("analysis job did not reach a terminal state")


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["schema_version"] == "1.0"


def test_mock_happy_path_reaches_export() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]

    upload = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers(),
        data={"expected_revision": 1},
        files={
            "file": (
                "synthetic.pdf",
                make_text_pdf("Synthetic medical material for OCR pipeline test."),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 201

    analysis_job = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 2, "idempotency_key": "analysis_test_001"},
    )
    assert analysis_job.status_code == 202
    completed = wait_for_job(application_id, analysis_job.json()["job_id"])
    assert completed["status"] == "succeeded"

    analysis = client.get(f"/api/v1/applications/{application_id}/analysis")
    assert analysis.status_code == 200
    assert analysis.json()["validation"]["can_finalize"] is True

    draft = client.post(
        f"/api/v1/applications/{application_id}/draft",
        json={"expected_revision": 2},
    )
    assert draft.status_code == 201
    draft_body = draft.json()

    confirmed = client.post(
        f"/api/v1/applications/{application_id}/draft/confirm",
        json={
            "draft_id": draft_body["draft_id"],
            "draft_revision": draft_body["draft_revision"],
            "expected_application_revision": 2,
        },
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"

    exported = client.post(
        f"/api/v1/applications/{application_id}/export",
        json={
            "draft_id": draft_body["draft_id"],
            "draft_revision": draft_body["draft_revision"],
            "expected_application_revision": 2,
            "format": "json",
        },
    )
    assert exported.status_code == 200
    assert exported.json()["format"] == "json"


def test_stale_revision_has_contract_error_shape() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    response = client.patch(
        f"/api/v1/applications/{application_id}",
        json={"expected_revision": 99, "patient_info": {"display_name": "新名称"}},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_CONFLICT"
    assert response.json()["request_id"].startswith("req_")


def test_missing_summary_blocks_draft() -> None:
    created = create_application(medical_summary=None)
    application_id = created["application"]["application_id"]
    job = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 1, "idempotency_key": "analysis_test_002"},
    )
    assert job.status_code == 202
    completed = wait_for_job(application_id, job.json()["job_id"])
    assert completed["status"] == "succeeded"
    analysis = client.get(f"/api/v1/applications/{application_id}/analysis").json()
    assert analysis["validation"]["can_finalize"] is False

    draft = client.post(
        f"/api/v1/applications/{application_id}/draft",
        json={"expected_revision": 1},
    )
    assert draft.status_code == 422
    assert draft.json()["error"]["code"] == "VALIDATION_FAILED"


def test_answering_required_summary_reanalyzes_new_revision() -> None:
    created = create_application(medical_summary=None)
    application_id = created["application"]["application_id"]
    client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 1, "idempotency_key": "analysis_test_003"},
    )

    job = client.post(
        f"/api/v1/applications/{application_id}/answers",
        json={
            "expected_revision": 1,
            "answers": [
                {
                    "question_id": "question_medical_summary",
                    "answer": "这是用户补充的合成测试病情说明。",
                }
            ],
        },
    )
    assert job.status_code == 202
    assert job.json()["application_revision"] == 2
    assert wait_for_job(application_id, job.json()["job_id"])["status"] == "succeeded"
    analysis = client.get(f"/api/v1/applications/{application_id}/analysis").json()
    assert analysis["validation"]["can_finalize"] is True


def test_rejects_unsupported_file_type() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_test_unsupported"),
        data={"expected_revision": 1},
        files={"file": ("notes.txt", b"text", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE"


def test_extracts_native_pdf_text_with_page_source() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_test_native"),
        data={"expected_revision": 1},
        files={
            "file": (
                "native-text.pdf",
                make_text_pdf("Hospital cost estimate: CNY 12500 (synthetic test)."),
                "application/pdf",
            )
        },
    )
    assert response.status_code == 201
    application = client.get(f"/api/v1/applications/{application_id}").json()
    evidence = application["evidence"]
    assert evidence[0]["page"] == 1
    assert evidence[0]["extraction_method"] == "structured_import"
    assert "12500" in evidence[0]["text_excerpt"]


def test_corrupt_pdf_returns_ocr_failed_without_saving_document() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_test_broken"),
        data={"expected_revision": 1},
        files={"file": ("broken.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "OCR_FAILED"
    application = client.get(f"/api/v1/applications/{application_id}").json()
    assert application["documents"] == []


def test_upload_idempotency_reuses_document_and_rejects_different_content() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    first_content = make_text_pdf("First synthetic medical document.")
    first = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_retry_001"),
        data={"expected_revision": 1},
        files={"file": ("first.pdf", first_content, "application/pdf")},
    )
    assert first.status_code == 201

    retry = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_retry_001"),
        data={"expected_revision": 1},
        files={"file": ("first.pdf", first_content, "application/pdf")},
    )
    assert retry.status_code == 201
    assert retry.json()["document_id"] == first.json()["document_id"]
    snapshot = client.get(f"/api/v1/applications/{application_id}").json()
    assert snapshot["application"]["revision"] == 2
    assert len(snapshot["documents"]) == 1

    conflict = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_retry_001"),
        data={"expected_revision": 2},
        files={
            "file": (
                "different.pdf",
                make_text_pdf("Different synthetic medical document."),
                "application/pdf",
            )
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "STATE_CONFLICT"


def test_concurrent_upload_retries_create_one_document() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    content = make_text_pdf("Concurrent synthetic upload retry.")

    def upload_once():
        return client.post(
            f"/api/v1/applications/{application_id}/documents",
            headers=upload_headers("upload_concurrent_001"),
            data={"expected_revision": 1},
            files={"file": ("concurrent.pdf", content, "application/pdf")},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _item: upload_once(), range(2)))

    assert [item.status_code for item in responses] == [201, 201]
    assert responses[0].json()["document_id"] == responses[1].json()["document_id"]
    snapshot = client.get(f"/api/v1/applications/{application_id}").json()
    assert snapshot["application"]["revision"] == 2
    assert len(snapshot["documents"]) == 1


def test_analysis_idempotency_returns_same_job() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    payload = {"expected_revision": 1, "idempotency_key": "analysis_retry_001"}
    first = client.post(f"/api/v1/applications/{application_id}/analyze", json=payload)
    second = client.post(f"/api/v1/applications/{application_id}/analyze", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert wait_for_job(application_id, first.json()["job_id"])["status"] == "succeeded"


def test_analysis_returns_before_slow_agent_finishes(monkeypatch) -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    original = application_routes.agent_service

    class SlowAgent:
        def extract(self, *args, **kwargs):
            time.sleep(0.5)
            return original.extract(*args, **kwargs)

        def draft_sections(self, *args, **kwargs):
            return original.draft_sections(*args, **kwargs)

    monkeypatch.setattr(application_routes, "agent_service", SlowAgent())
    started = time.monotonic()
    response = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 1, "idempotency_key": "analysis_slow_001"},
    )
    elapsed = time.monotonic() - started
    assert response.status_code == 202
    assert elapsed < 0.3
    assert response.json()["status"] in {"queued", "running"}
    assert wait_for_job(application_id, response.json()["job_id"])["status"] == "succeeded"


def test_background_failure_is_pollable(monkeypatch) -> None:
    created = create_application()
    application_id = created["application"]["application_id"]

    class FailingAgent:
        def extract(self, *args, **kwargs):
            raise AgentIntegrationError("synthetic agent outage")

    monkeypatch.setattr(application_routes, "agent_service", FailingAgent())
    response = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 1, "idempotency_key": "analysis_fail_001"},
    )
    assert response.status_code == 202
    completed = wait_for_job(application_id, response.json()["job_id"])
    assert completed["status"] == "failed"
    assert completed["error"]["code"] == "AGENT_UNAVAILABLE"


def test_old_revision_analysis_cannot_overwrite_new_application(monkeypatch) -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    original = application_routes.agent_service

    class SlowAgent:
        def extract(self, *args, **kwargs):
            time.sleep(0.25)
            return original.extract(*args, **kwargs)

    monkeypatch.setattr(application_routes, "agent_service", SlowAgent())
    queued = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 1, "idempotency_key": "analysis_stale_001"},
    )
    updated = client.patch(
        f"/api/v1/applications/{application_id}",
        json={"expected_revision": 1, "patient_info": {"display_name": "更新后的名称"}},
    )
    assert updated.status_code == 200
    completed = wait_for_job(application_id, queued.json()["job_id"])
    assert completed["status"] == "failed"
    assert completed["error"]["code"] == "STATE_CONFLICT"
    assert client.get(f"/api/v1/applications/{application_id}/analysis").status_code == 404


def test_runtime_operation_ids_match_contract() -> None:
    expected = {
        "create_application",
        "get_application",
        "update_application",
        "upload_document",
        "list_documents",
        "start_analysis",
        "get_analysis_job",
        "get_latest_analysis",
        "submit_answers",
        "generate_draft",
        "get_latest_draft",
        "confirm_draft",
        "export_application",
        "get_health",
    }
    operations = {
        operation["operationId"]
        for path in app.openapi()["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert operations == expected
    assert len(operations) == 14


def test_saved_application_and_upload_survive_store_restart() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    uploaded = client.post(
        f"/api/v1/applications/{application_id}/documents",
        headers=upload_headers("upload_restart_001"),
        data={"expected_revision": 1},
        files={
            "file": (
                "restart.pdf",
                make_text_pdf("Synthetic restart persistence material."),
                "application/pdf",
            )
        },
    )
    assert uploaded.status_code == 201
    queued = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 2, "idempotency_key": "analysis_restart_001"},
    )
    assert wait_for_job(application_id, queued.json()["job_id"])["status"] == "succeeded"
    draft = client.post(
        f"/api/v1/applications/{application_id}/draft",
        json={"expected_revision": 2},
    )
    assert draft.status_code == 201

    reloaded = PersistentStore(store.data_dir)
    restored = reloaded.get(application_id)
    assert restored is not None
    assert restored.application.revision == 2
    assert restored.documents[0].document_id == uploaded.json()["document_id"]
    assert restored.analysis is not None
    assert restored.draft is not None
    assert restored.draft.draft_id == draft.json()["draft_id"]
    assert reloaded.upload_path(restored.documents[0].document_id).is_file()


def test_restart_marks_incomplete_analysis_job_failed() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    record = store.get(application_id)
    assert record is not None
    timestamp = application_routes.now()
    record.jobs["job_interrupted_001"] = AnalysisJob(
        job_id="job_interrupted_001",
        application_id=application_id,
        application_revision=1,
        status="running",
        created_at=timestamp,
        updated_at=timestamp,
    )
    store.save(record)

    reloaded = PersistentStore(store.data_dir)
    recovered = reloaded.get(application_id)
    assert recovered is not None
    job = recovered.jobs["job_interrupted_001"]
    assert job.status == "failed"
    assert job.error is not None
    assert job.error.code == "INTERNAL_ERROR"

