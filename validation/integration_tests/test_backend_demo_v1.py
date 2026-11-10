"""Use B/A's unmodified adapters; no model API, OCR engine or HTTP server."""

import pytest

from agent.agent_service import AgentError, AgentService
from agent.draft_policy import DRAFT_WARNING, sections_for_facts
from backend.models import Application, Draft, DraftConfirmationRequest, Evidence, ExportRequest, Fact, UploadedDocument
from backend.services.agent import RealAgentService
from backend.services.validation import RealValidationService, ValidationIntegrationError
from validation import DEMO_V1_POLICY_PATH
from validation.tests.test_demo_v1 import actions, formal_draft, scenario


def models(request):
    return ([UploadedDocument.model_validate(x) for x in request["documents"]],
            [Evidence.model_validate(x) for x in request["evidence"]],
            [Fact.model_validate(x) for x in request["facts"]])


def test_original_backend_loads_demo_v1_from_explicit_environment(monkeypatch):
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", str(DEMO_V1_POLICY_PATH))
    adapter = RealValidationService()
    assert adapter._policy.policy_name == "demo_v1"
    for mode in ("clean", "info", "warning", "conflict"):
        app, request = scenario(mode)
        result = adapter.validate(Application.model_validate(app), *models(request), [])
        assert result.can_finalize is (mode != "conflict")
        assert result.application_revision == app["revision"]
        if mode in ("info", "warning"):
            assert any(issue.severity == mode for issue in result.issues)


def test_original_backend_confirmation_export_execute_current_d_checks(monkeypatch):
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", str(DEMO_V1_POLICY_PATH))
    adapter = RealValidationService()
    app, request = scenario("info")
    draft = formal_draft(app, request)
    confirmation, export = actions(app, draft)
    app["status"] = "draft_ready"
    confirmed = adapter.validate_confirmation(
        Application.model_validate(app), *models(request), Draft.model_validate(draft),
        DraftConfirmationRequest.model_validate(confirmation),
    )
    assert confirmed.can_finalize is True
    assert any(issue.severity == "info" for issue in confirmed.issues)
    app["status"] = "confirmed"
    draft.update(status="confirmed", confirmed_at="2026-10-20T00:02:00Z")
    assert adapter.validate_export(Application.model_validate(app), *models(request),
                                   Draft.model_validate(draft), ExportRequest.model_validate(export)).can_finalize
    # Stale draft and stale request cannot export against a newer stored version.
    app["revision"] += 1
    assert not adapter.validate_export(Application.model_validate(app), *models(request),
                                       Draft.model_validate(draft), ExportRequest.model_validate(export)).can_finalize


def test_bad_policy_is_rejected_and_backend_default_is_explicit(monkeypatch):
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", "validation/policies/not_present.json")
    with pytest.raises(RuntimeError):
        RealValidationService()
    monkeypatch.delenv("CAREFUND_VALIDATION_POLICY", raising=False)
    # B now deliberately loads its reviewed integration policy if the env var
    # is absent. Respect that change; a missing Policy passed to D still blocks.
    default = RealValidationService()
    assert default._policy is not None
    app, request = scenario()
    from validation import validate
    report = validate(request, policy=None)
    assert not report["can_finalize"]
    assert any(issue["field"] == "validation.policy" for issue in report["issues"])


def test_original_backend_adapter_maps_invalid_calendar_date_to_safe_error(monkeypatch):
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", str(DEMO_V1_POLICY_PATH))
    app, request = scenario()
    # Pydantic's permissive calendar string still must be rejected at D boundary.
    request["facts"][-1]["value"]["value"] = "2026-02-30"
    with pytest.raises(ValidationIntegrationError):
        RealValidationService().validate(Application.model_validate(app), *models(request), [])


def test_backend_pairs_full_validation_and_projects_nonblocking_issues(monkeypatch):
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", str(DEMO_V1_POLICY_PATH))
    app, request = scenario("info")
    d_adapter = RealValidationService()
    application = Application.model_validate(app)
    report = d_adapter.validate(application, *models(request), [])
    assert report.can_finalize and report.issues
    captured = {}

    def runner(operation, value):
        captured["operation"] = operation
        captured["request"] = value
        response = {key: value[key] for key in ("schema_version", "application_id", "application_revision")}
        response.update(
            candidate_sections=sections_for_facts(value["candidate_facts"]),
            warnings=[DRAFT_WARNING],
        )
        return response

    a_adapter = RealAgentService()
    a_adapter._service = lambda app_id: (AgentService(runner), AgentError)
    sections = a_adapter.draft_sections(application, models(request)[2], report)

    assert captured["operation"] == "draft"
    assert captured["request"]["validation_issue_ids"] == []
    assert sections
