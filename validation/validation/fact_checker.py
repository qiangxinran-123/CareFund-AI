"""Backend-facing ValidationRequest -> ValidationResult implementation."""

from collections import defaultdict

from .evidence_tracker import EvidenceTracker
from .issues import issue, result
from .rules import ValidationPolicy
from .rules.values import canonical, supported_by, supports_cost_field
from .rules.agent_boundary import has_generation_instruction
from .schema import check_model


def validate(request: dict, *, policy: ValidationPolicy | None = None) -> dict:
    """Raise on invalid structure; return business issues using the shared schema."""
    check_model(request, "validation.schema.json", "ValidationRequest")
    tracker = EvidenceTracker(request)
    issues = tracker.check()
    by_field = defaultdict(list)
    for fact in request["facts"]:
        by_field[fact["field"]].append(fact)
        fact_ids = [fact["fact_id"]]
        status = fact["verification_status"]
        if has_generation_instruction(fact):
            issues.append(issue("unsupported", fact["field"], "事实文本包含生成或篡改指令，需核对来源，不能据此生成申请。", fact_ids))
        if fact["value"]["kind"] == "text" and not fact["value"]["value"].strip():
            issues.append(issue("invalid_format", fact["field"], "事实文本不能只有空白。", fact_ids))
        if policy is not None and fact["field"] in policy.field_kinds:
            if fact["value"]["kind"] != policy.field_kinds[fact["field"]]:
                issues.append(issue("invalid_format", fact["field"], "事实取值类型与已配置的字段规则不一致。", fact_ids))
        if status in ("conflicting", "unsupported"):
            kind = "conflict" if status == "conflicting" else "unsupported"
            issues.append(issue(kind, fact["field"], "事实尚有冲突或缺乏支持，需澄清后复核。", fact_ids))
        if fact["source_type"] == "document":
            sources = tracker.sources_for(fact)
            # A must return new candidates as pending. Independently check their
            # references/text here, without promoting or modifying the Fact.
            if not sources or not all(supported_by(fact["value"], source["text_excerpt"]) for source in sources):
                issues.append(issue("unsupported", fact["field"], "引用文本未明确支持该事实；不得猜测或夸大。", fact_ids))
            elif not all(supports_cost_field(fact["field"], fact["value"], source["text_excerpt"]) for source in sources):
                issues.append(issue("unsupported", fact["field"], "材料未明确支持该费用的已支付或预估含义，金额相同也不能混用。", fact_ids))
        elif status == "supported":
            sources = tracker.sources_for(fact)
            if not sources or not all(supported_by(fact["value"], source["text_excerpt"]) for source in sources):
                issues.append(issue("unsupported", fact["field"], "用户陈述不能仅凭确认标记为材料支持。", fact_ids))
            elif not all(supports_cost_field(fact["field"], fact["value"], source["text_excerpt"]) for source in sources):
                issues.append(issue("unsupported", fact["field"], "引用材料不能支持用户陈述所标注的费用含义。", fact_ids))
        elif not fact["evidence_ids"]:
            issues.append(issue(
                "unsupported", fact["field"], "该事实仅来自用户陈述，不代表材料证明或平台审核通过。",
                fact_ids, severity="info",
            ))

    for field, facts in by_field.items():
        if len({canonical(fact["value"]) for fact in facts}) > 1:
            kinds = {fact["value"]["kind"] for fact in facts}
            kind = {frozenset({"money"}): "inconsistent_amount", frozenset({"date"}): "inconsistent_date"}.get(
                frozenset(kinds), "conflict",
            )
            issues.append(issue(kind, field, "同一事实字段存在不同取值，需人工澄清，系统不自动择一。", [f["fact_id"] for f in facts]))

    if policy is None:
        issues.append(issue("missing", "validation.policy", "尚未配置经团队确认的必填事实与材料规则，禁止直接确认导出。"))
    else:
        for field in policy.recommended_document_fields:
            if not any(fact["source_type"] == "document" and fact["evidence_ids"] for fact in by_field[field]):
                issues.append(issue(
                    "missing", field, "演示建议补充该信息的材料来源；当前可保留为用户陈述，不作材料已证实结论。",
                    [fact["fact_id"] for fact in by_field[field]], severity="warning",
                ))
        for field in policy.recommended_fields:
            if not by_field[field]:
                issues.append(issue(
                    "missing", field, "未提供演示建议补充的信息；可保留未知，不是平台审批要求。",
                    severity="warning",
                ))
        if policy.require_processed_document and not any(
            doc["processing_status"] == "processed" for doc in request["documents"]
        ):
            issues.append(issue("missing", "documents", "缺少已完成解析的证明材料。"))
        for field in policy.required_fields:
            facts = by_field[field]
            if not facts:
                issues.append(issue("missing", field, "缺少规则要求的事实，请补充信息或材料。"))
                continue
            if policy.require_user_confirmation and any(not fact["user_confirmed"] for fact in facts):
                issues.append(issue("missing", field, "关键事实尚未由用户确认。", [f["fact_id"] for f in facts]))
            if field in policy.document_required_fields and not any(
                fact["source_type"] == "document" and fact["evidence_ids"] for fact in facts
            ):
                issues.append(issue("unsupported", field, "该关键事实需要材料来源，用户自述不能替代。", [f["fact_id"] for f in facts]))

    response = result(request, issues)
    check_model(response, "validation.schema.json", "ValidationResult")
    return response
