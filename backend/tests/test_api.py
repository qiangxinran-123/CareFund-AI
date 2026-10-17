from fastapi.testclient import TestClient

from backend.main import app
from backend.store import store


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
        data={"expected_revision": 1},
        files={"file": ("synthetic.pdf", b"synthetic content", "application/pdf")},
    )
    assert upload.status_code == 201

    analysis_job = client.post(
        f"/api/v1/applications/{application_id}/analyze",
        json={"expected_revision": 2, "idempotency_key": "analysis_test_001"},
    )
    assert analysis_job.status_code == 202
    assert analysis_job.json()["status"] == "succeeded"

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
    analysis = client.get(f"/api/v1/applications/{application_id}/analysis").json()
    assert analysis["validation"]["can_finalize"] is True


def test_rejects_unsupported_file_type() -> None:
    created = create_application()
    application_id = created["application"]["application_id"]
    response = client.post(
        f"/api/v1/applications/{application_id}/documents",
        data={"expected_revision": 1},
        files={"file": ("notes.txt", b"text", "text/plain")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE"

