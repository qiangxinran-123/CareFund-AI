"""Independent checker of A cc29e6d's literal candidate layout, not a generator.

The labels/prefixes deliberately follow the supplied agent/draft_policy.py.
Any A layout change must be reviewed against this local integration rule.
"""

_LABELS = {
    "patient.relationship_to_applicant": "患者与申请人的关系",
    "patient.medical_summary": "病情及检查情况",
    "treatment.paid_cost": "已支付医疗费",
    "treatment.estimated_cost": "后续预估治疗费",
    "treatment.recorded_date": "治疗记录日期",
    "contact.city": "当前所在城市",
}
_PREFIXES = {
    "user_input": "用户自述，",
    "user_correction": "用户更正陈述，",
    "document": "提交材料记载（真伪未经本模块核验），",
}


def matches_literal_sections(facts: list[dict], sections: list[dict]) -> bool:
    if not facts or len(facts) != len(sections):
        return False
    for fact, section in zip(facts, sections):
        kind, value = fact["value"]["kind"], fact["value"]["value"]
        if kind == "money":
            currency, minor = value["currency"], value["amount_minor"]
            literal = f"人民币{minor // 100}.{minor % 100:02d}元" if currency == "CNY" else f"{currency} {minor}（最小货币单位）"
        elif kind == "boolean":
            literal = "true" if value else "false"
        elif kind == "text":
            literal = "“" + value + "”"
        else:
            literal = str(value)
        title = _LABELS.get(fact["field"], "补充事实")
        label = _LABELS.get(fact["field"], fact["field"])
        expected = _PREFIXES[fact["source_type"]] + label + "：" + literal
        if section != {"title": title, "content": expected, "fact_ids": [fact["fact_id"]]}:
            return False
    return True
