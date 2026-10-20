from datetime import datetime, timezone
from pathlib import Path

from agent.agent_service import AgentError, AgentService
from agent.draft_policy import DRAFT_WARNING, sections_for_facts

from backend.models import (
    Application,
    Evidence,
    Fact,
    Money,
    MoneyValue,
    PatientInfo,
    TextValue,
    UploadedDocument,
)
from backend.services.agent import RealAgentService
from backend.services.validation import RealValidationService


NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


def application() -> Application:
    return Application(
        application_id="app_integration_001",
        revision=1,
        status="reviewing",
        patient_info=PatientInfo(
            display_name="合成测试用户",
            age_group="adult",
            medical_summary="用户自述正在接受示例性治疗。",
        ),
        created_at=NOW,
        updated_at=NOW,
    )


def test_backend_adapter_calls_real_agent_service_contract() -> None:
    captured: dict = {}

    def runner(operation: str, request: dict) -> dict:
        captured["operation"] = operation
        captured["request"] = request
        return {
            "schema_version": request["schema_version"],
            "application_id": request["application_id"],
            "application_revision": request["application_revision"],
            "candidate_facts": request["candidate_facts"],
            "questions": [],
            "warnings": ["候选结果需要后端和用户复核。"],
        }

    service = AgentService(runner)
    adapter = RealAgentService()
    adapter._service = lambda _application_id: (service, AgentError)
    existing = Fact(
        fact_id="fact_integration_001",
        field="patient.medical_summary",
        value=TextValue(value="用户自述正在接受示例性治疗。"),
        source_type="user_input",
        evidence_ids=[],
        verification_status="pending",
        user_confirmed=False,
    )

    facts, questions = adapter.extract(application(), [], [], [existing], {})

    assert captured["operation"] == "extract"
    assert captured["request"]["user_input"]["description"] == existing.value.value
    assert facts == [existing]
    assert len(questions) <= 3
    assert all(question.required is False for question in questions)


def test_backend_adapter_calls_real_agent_draft_boundary() -> None:
    fact = Fact(
        fact_id="fact_integration_002",
        field="patient.medical_summary",
        value=TextValue(value="用户确认的合成测试信息。"),
        source_type="user_input",
        evidence_ids=[],
        verification_status="pending",
        user_confirmed=True,
    )

    def runner(operation: str, request: dict) -> dict:
        assert operation == "draft"
        return {
            "schema_version": request["schema_version"],
            "application_id": request["application_id"],
            "application_revision": request["application_revision"],
            "candidate_sections": sections_for_facts(request["candidate_facts"]),
            "warnings": [DRAFT_WARNING],
        }

    adapter = RealAgentService()
    adapter._service = lambda _application_id: (AgentService(runner), AgentError)
    sections = adapter.draft_sections(application(), [fact], [])

    assert len(sections) == 1
    assert sections[0].fact_ids == [fact.fact_id]
    assert "用户确认的合成测试信息" in sections[0].content


def test_backend_adapter_calls_real_validation_module(monkeypatch) -> None:
    policy_path = Path("backend/config/validation-policy.integration.json").resolve()
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", str(policy_path))
    app = application()
    document = UploadedDocument(
        document_id="doc_integration_001",
        application_id=app.application_id,
        filename="synthetic-estimate.pdf",
        media_type="application/pdf",
        size_bytes=128,
        uploaded_at=NOW,
        processing_status="processed",
    )
    evidence = Evidence(
        evidence_id="ev_integration_001",
        document_id=document.document_id,
        page=1,
        text_excerpt="后续预估治疗费用为人民币 12,500.00 元。",
        extraction_method="structured_import",
    )
    facts = [
        Fact(
            fact_id="fact_integration_003",
            field="patient.medical_summary",
            value=TextValue(value=app.patient_info.medical_summary or ""),
            source_type="user_input",
            evidence_ids=[],
            verification_status="pending",
            user_confirmed=True,
        ),
        Fact(
            fact_id="fact_integration_004",
            field="treatment.estimated_cost",
            value=MoneyValue(value=Money(currency="CNY", amount_minor=1_250_000)),
            source_type="document",
            evidence_ids=[evidence.evidence_id],
            verification_status="pending",
            user_confirmed=True,
        ),
    ]

    result = RealValidationService().validate(
        app, [document], [evidence], facts, []
    )

    assert result.application_id == app.application_id
    assert result.application_revision == app.revision
    assert result.can_finalize is True
    assert all(issue.severity != "blocking" for issue in result.issues)


def test_real_validation_uses_backend_integration_policy_by_default(monkeypatch) -> None:
    monkeypatch.delenv("CAREFUND_VALIDATION_POLICY", raising=False)
    service = RealValidationService()
    assert service._policy is not None
