"""Local A/D adapters using the unchanged shared contracts. No network calls."""

from copy import deepcopy
import json

from .fact_checker import validate
from .issues import issue, result
from .rules import ValidationPolicy
from .rules.agent_literal import matches_literal_sections
from .rules.agent_boundary import EXTRACT_FIELDS, QUESTION_FIELDS
from .schema import ContractValidationError, check_model


_IDENTITY = ("schema_version", "application_id", "application_revision")


class AgentAdaptationError(ContractValidationError):
    """An inconsistent Agent snapshot. Never include patient values in errors."""


def _unique(items: list[dict], key: str) -> dict:
    indexed = {item[key]: item for item in items}
    if len(indexed) != len(items):
        raise AgentAdaptationError("Duplicate " + key + " in Agent snapshot.")
    return indexed


def build_validation_request(extract_request: dict, extract_response: dict) -> dict:
    """Map a complete same-revision extraction snapshot to ValidationRequest.

    This validates the saved A boundary too; it does not infer missing history,
    assign IDs, merge increments, choose conflicts or promote verification flags.
    """
    check_model(extract_request, "agent.schema.json", "AgentExtractRequest")
    check_model(extract_response, "agent.schema.json", "AgentExtractResponse")
    if any(extract_request[key] != extract_response[key] for key in _IDENTITY):
        raise AgentAdaptationError("Agent request/response identity or revision mismatch.")
    documents, evidence = [], []
    for entry in extract_request["extracted_documents"]:
        document = entry["document"]
        if document["application_id"] != extract_request["application_id"]:
            raise AgentAdaptationError("Document belongs to a different application.")
        if any(item["document_id"] != document["document_id"] for item in entry["evidence"]):
            raise AgentAdaptationError("Evidence is attached to the wrong document.")
        documents.append(document)
        evidence.extend(entry["evidence"])
    _unique(documents, "document_id")
    evidence_by_id = _unique(evidence, "evidence_id")
    previous = _unique(extract_request["candidate_facts"], "fact_id")
    returned = _unique(extract_response["candidate_facts"], "fact_id")
    _unique(extract_response["questions"], "question_id")
    if not previous.keys() <= returned.keys() or any(returned[key] != fact for key, fact in previous.items()):
        raise AgentAdaptationError("Agent omitted or modified an existing fact.")
    for fact in list(previous.values()) + list(returned.values()):
        if not set(fact["evidence_ids"]) <= evidence_by_id.keys():
            raise AgentAdaptationError("Agent fact references missing evidence.")
    for key in returned.keys() - previous.keys():
        fact = returned[key]
        if fact["field"] not in EXTRACT_FIELDS:
            raise AgentAdaptationError("New Agent candidate field is outside the current extraction scope.")
        if fact["user_confirmed"] or fact["verification_status"] != "pending":
            raise AgentAdaptationError("New Agent candidates cannot confirm or verify themselves.")
    if any(question["field"] not in QUESTION_FIELDS for question in extract_response["questions"]):
        raise AgentAdaptationError("Agent question field is outside the current extraction scope.")
    mapped = {key: extract_response[key] for key in _IDENTITY}
    mapped.update(documents=documents, evidence=evidence, facts=extract_response["candidate_facts"])
    mapped = deepcopy(mapped)
    check_model(mapped, "validation.schema.json", "ValidationRequest")
    return mapped


def _draft_issues(request: dict, policy: ValidationPolicy | None) -> list[dict]:
    issues = validate(request, policy=policy)["issues"]
    if not request["facts"]:
        issues.append(issue("missing", "facts", "草稿生成需要至少一条当前有效事实。"))
    unconfirmed = [fact["fact_id"] for fact in request["facts"] if not fact["user_confirmed"]]
    if unconfirmed:
        issues.append(issue("missing", "facts", "A 的草稿入口要求所有传入事实均经用户确认。", unconfirmed))
    by_field = {}
    for fact in request["facts"]:
        by_field.setdefault(fact["field"], []).append(fact)
    for field, facts in by_field.items():
        # Match A's exact comparison as well as D's normalized conflict checks.
        if len({json.dumps(f["value"], sort_keys=True, ensure_ascii=True) for f in facts}) > 1:
            if not any(item["field"] == field and item["severity"] == "blocking" for item in issues):
                issues.append(issue("conflict", field, "A 的草稿入口暂不接受同字段不同原始值。", [f["fact_id"] for f in facts]))
    return issues


def prepare_agent_draft_request(
    request: dict, *, policy: ValidationPolicy | None = None,

    application: dict | None = None, generation_request: dict | None = None,
) -> tuple[dict, dict]:
    """Return (AgentDraftRequest, ValidationResult) with explicit ID semantics.

    Legacy policies retain all IDs. demo_v1 explicitly sends blocking IDs only;
    the full, unmodified issue list stays in the paired result for UI/audit.
    B must never call A if can_finalize is false. To check generation revision,
    supply the current stored application and formal DraftGenerationRequest.
    """
    if (application is None) != (generation_request is None):
        raise AgentAdaptationError("Provide application and generation_request together.")
    report = (
        validate_for_generation(request, application, generation_request, policy=policy)
        if application is not None else result(request, _draft_issues(request, policy))
    )
    draft_request = {key: request[key] for key in _IDENTITY}
    draft_request.update(
        candidate_facts=deepcopy(request["facts"]),
        validation_issue_ids=[
            item["issue_id"] for item in report["issues"]
            if policy is None or policy.draft_issue_scope == "all" or item["severity"] == "blocking"
        ],
=======
) -> tuple[dict, dict]:
    """Return (AgentDraftRequest, current ValidationResult), preserving ALL issues.

    A 755a0c2 blocks every nonempty issue list, including info/warning. B must
    pause if can_finalize is false OR validation_issue_ids is nonempty. No issue
    is silently dropped to circumvent A's current gate.
    """
    report = result(request, _draft_issues(request, policy))
    draft_request = {key: request[key] for key in _IDENTITY}
    draft_request.update(
        candidate_facts=deepcopy(request["facts"]),
        validation_issue_ids=[item["issue_id"] for item in report["issues"]],

    )
    check_model(report, "validation.schema.json", "ValidationResult")
    check_model(draft_request, "agent.schema.json", "AgentDraftRequest")
    return draft_request, report



def validate_for_generation(
    request: dict, application: dict, generation_request: dict,
    *, policy: ValidationPolicy | None = None,
) -> dict:
    """Check a fresh stored Application snapshot and expected revision before A."""
    check_model(application, "application.schema.json", "Application")
    check_model(generation_request, "draft.schema.json", "DraftGenerationRequest")
    issues = _draft_issues(request, policy)
    if not (
        application["application_id"] == request["application_id"]
        and application["revision"] == request["application_revision"] == generation_request["expected_revision"]
    ):
        issues.append(issue("conflict", "application.revision", "生成请求或分析快照版本过期，需读取当前申请并重新校验。"))
    if not application["patient_info"]["display_name"].strip():
        issues.append(issue("missing", "patient.display_name", "申请人显示名称不能为空白。"))
    report = result(request, issues)
    check_model(report, "validation.schema.json", "ValidationResult")
    return report



def validate_agent_draft(
    request: dict, draft_response: dict, *, policy: ValidationPolicy | None = None,
) -> dict:
    """Check candidate sections without pretending B has saved a formal Draft.

    The literal layout matches the supplied A snapshot, not a new wire schema.
    For B's saved Draft, continue to use confirmation/export checks separately.
    """
    check_model(draft_response, "agent.schema.json", "AgentDraftResponse")
    issues = _draft_issues(request, policy)
    if any(draft_response[key] != request[key] for key in _IDENTITY):
        issues.append(issue("conflict", "draft.revision", "候选草稿不属于当前申请版本。"))
    if not matches_literal_sections(request["facts"], draft_response["candidate_sections"]):
        issues.append(issue("unsupported", "draft.sections", "候选草稿未按 A 当前逐事实格式完整保留原值、来源或限定词。"))
    response = result(request, issues)
    check_model(response, "validation.schema.json", "ValidationResult")
    return response
