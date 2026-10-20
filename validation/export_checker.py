"""Recheck snapshots immediately before Backend confirmation/export transactions."""

from datetime import datetime


from .fact_checker import validate

from .issues import issue, result
from .rules import ValidationPolicy
from .rules.agent_literal import matches_literal_sections
from .rules.values import date_mentions, fact_numbers, money_mentions, normalize, numeric_mentions
from .schema import check_model

from .agent_adapter import _draft_issues




def _check(
    request: dict, application: dict, draft: dict, action: dict,
    *, exporting: bool, policy: ValidationPolicy | None,
) -> dict:
    check_model(application, "application.schema.json", "Application")
    check_model(draft, "draft.schema.json", "Draft")
    check_model(action, "draft.schema.json", "ExportRequest" if exporting else "DraftConfirmationRequest")

    # Share A's fact confirmation/value gate across generation and final checks.
    issues = _draft_issues(request, policy)
    if not application["patient_info"]["display_name"].strip():
        issues.append(issue("missing", "patient.display_name", "申请人显示名称不能为空白。"))

    issues = validate(request, policy=policy)["issues"]

    if not (
        application["application_id"] == request["application_id"] == draft["application_id"]
        and application["revision"] == request["application_revision"] == draft["application_revision"]
        and action["expected_application_revision"] == application["revision"]
        and action["draft_id"] == draft["draft_id"]
        and action["draft_revision"] == draft["draft_revision"]
    ):
        issues.append(issue("conflict", "draft.revision", "申请、草稿或请求版本不匹配，旧结果不得确认或导出。"))
    expected_statuses = ("confirmed", "exported") if exporting else ("draft_ready",)
    expected_draft_status = "confirmed" if exporting else "generated"
    if application["status"] not in expected_statuses or draft["status"] != expected_draft_status:
        issues.append(issue("conflict", "draft.status", "当前申请或草稿状态不允许该操作。"))
    if exporting:
        confirmed_at = draft.get("confirmed_at")
        if confirmed_at is None or datetime.fromisoformat(confirmed_at) < datetime.fromisoformat(draft["created_at"]):
            issues.append(issue("missing", "draft.confirmed_at", "缺少有效的草稿确认记录。"))

    facts = {fact["fact_id"]: fact for fact in request["facts"]}
    literal_layout = matches_literal_sections(request["facts"], [
        {key: section[key] for key in ("title", "content", "fact_ids")}
        for section in draft["sections"]
    ])

    if policy is not None and policy.policy_name == "demo_v1" and not literal_layout:
        issues.append(issue("unsupported", "draft.sections", "demo_v1 要求草稿完整保留当前事实原值、来源和限定词；编辑后需重新核验。"))

    section_ids = set()
    for section in draft["sections"]:
        if section["section_id"] in section_ids:
            issues.append(issue("invalid_format", "draft.sections", "草稿章节标识重复。"))
        section_ids.add(section["section_id"])
        referenced = [facts[ref] for ref in section["fact_ids"] if ref in facts]
        if len(referenced) != len(section["fact_ids"]):
            issues.append(issue("unsupported", "draft.sections", "草稿引用了不存在的事实。"))
        if any(not fact["user_confirmed"] for fact in referenced):
            issues.append(issue("missing", "draft.sections", "草稿使用的事实尚未由用户确认。", [f["fact_id"] for f in referenced]))
        amounts = set()
        dates = set()
        numbers = set()
        source_texts = []
        for fact in referenced:
            value = fact["value"]
            numbers.update(fact_numbers(value))
            if value["kind"] == "money":
                amounts.add((value["value"]["currency"], value["value"]["amount_minor"]))
            elif value["kind"] == "date":
                dates.add(value["value"])
            elif value["kind"] == "text":
                source_texts.append(normalize(value["value"]))
                amounts.update(money_mentions(value["value"]))
                dates.update(date_mentions(value["value"]))
        # Both titles and prose can contain factual claims.
        prose = section["title"] + "\n" + section["content"]
        if not literal_layout and money_mentions(prose) - amounts:
            issues.append(issue("inconsistent_amount", "draft.sections", "草稿含有其引用事实未支持的金额或币种。", [f["fact_id"] for f in referenced]))
        if not literal_layout and date_mentions(prose) - dates:
            issues.append(issue("inconsistent_date", "draft.sections", "草稿含有其引用事实未支持的日期。", [f["fact_id"] for f in referenced]))
        if not literal_layout and numeric_mentions(prose) - numbers:
            issues.append(issue("unsupported", "draft.sections", "草稿含有其引用事实未支持的数字，请核实或删除。", [f["fact_id"] for f in referenced]))
        # A small explicit guard, not a general medical-language classifier.
        risky_phrases = ("确诊", "晚期", "危重", "病危", "生命垂危", "抢救", "治愈", "无法负担", "倾家荡产")
        if not literal_layout and any(phrase in normalize(prose) and not any(phrase in text for text in source_texts) for phrase in risky_phrases):
            issues.append(issue("unsupported", "draft.sections", "草稿新增了引用事实未支持的病情或困难程度表述。", [f["fact_id"] for f in referenced]))

    response = result(request, issues)
    check_model(response, "validation.schema.json", "ValidationResult")
    return response


def validate_for_confirmation(
    request: dict, application: dict, draft: dict, confirmation_request: dict,
    *, policy: ValidationPolicy | None = None,
) -> dict:
    return _check(request, application, draft, confirmation_request, exporting=False, policy=policy)


def validate_for_export(
    request: dict, application: dict, draft: dict, export_request: dict,
    *, policy: ValidationPolicy | None = None,
) -> dict:
    return _check(request, application, draft, export_request, exporting=True, policy=policy)
