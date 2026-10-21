"""Use B/A's unmodified adapters; no model API, OCR engine or HTTP server."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from agent.agent_service import AgentError, AgentService
from agent.draft_policy import DRAFT_WARNING, sections_for_facts
from backend.models import Application, Draft, DraftConfirmationRequest, Evidence, ExportRequest, Fact, UploadedDocument
from backend.services.agent import AgentIntegrationError, RealAgentService
from backend.services.validation import RealValidationService, ValidationIntegrationError
from validation import DEMO_V1_POLICY_PATH, prepare_agent_draft_request
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


def test_unmodified_backend_all_ids_mapping_is_reproduced_not_hidden(monkeypatch):
    monkeypatch.setenv("CAREFUND_VALIDATION_POLICY", str(DEMO_V1_POLICY_PATH))
    app, request = scenario("info")
    d_adapter = RealValidationService()
    application = Application.model_validate(app)
    report = d_adapter.validate(application, *models(request), [])
    assert report.can_finalize and report.issues
    runner = Mock()
    a_adapter = RealAgentService()
    a_adapter._service = lambda app_id: (AgentService(runner), AgentError)
    # B currently forwards all IDs. This expected error records the owner action.
    with pytest.raises(AgentIntegrationError):
        a_adapter.draft_sections(application, models(request)[2], report.issues)
    runner.assert_not_called()
    # The documented, explicit D policy mapping works with the same A service.
    prepared, fresh = prepare_agent_draft_request(
        request, policy=d_adapter._policy, application=app,
        generation_request={"expected_revision": app["revision"]},
    )
    assert fresh["can_finalize"] is True
    assert fresh["issues"] and not prepared["validation_issue_ids"]
    result = {key: prepared[key] for key in ("schema_version", "application_id", "application_revision")}
    result.update(candidate_sections=sections_for_facts(prepared["candidate_facts"]), warnings=[DRAFT_WARNING])
    generated = AgentService(lambda op, value: deepcopy(result)).draft(prepared)
    assert generated["candidate_sections"]
