"""Local guards aligned to the A 755a0c2 handoff, not new shared schema.

Keep the bounded instruction patterns aligned with A's draft_input_policy.py.
This never rewrites source facts, calls A, or claims complete semantic coverage.
"""

import re

EXTRACT_FIELDS = frozenset({
    "patient.relationship_to_applicant", "patient.medical_summary",
    "treatment.paid_cost", "treatment.estimated_cost", "treatment.recorded_date",
    "contact.city",
})
QUESTION_FIELDS = EXTRACT_FIELDS | {"documents.diagnosis_proof"}

_INSTRUCTIONS = tuple(re.compile(pattern, re.I) for pattern in (
    r"(?:忽略|无视|绕过)(?:以上|之前|原有|原|所有|系统|先前|前面)?[^。\n]{0,10}(?:规则|指令|提示词|限制)",
    r"(?:编造|捏造|伪造)[^。\n]{0,24}(?:费用|金额|确诊|诊断|病情|证据)",
    r"(?:声明|声称|输出|宣布)[^。\n]{0,8}(?:已审核通过|审核通过|批准导出)",
    r"<\s*/?\s*(?:system|developer)\b[^>]*>",
    r"\b(?:ignore|disregard|override)\b[^.\n]{0,40}\b(?:instructions?|rules?|prompts?)\b",
    r"\b(?:fabricate|invent|forge)\b[^.\n]{0,40}\b(?:diagnosis|costs?|payments?|evidence|approval)\b",
))
_NEGATED = re.compile(r"(?:不要|不得|禁止|不能|不应|未|没有|拒绝|不|never|do not|don.t)\s*$", re.I)


def has_generation_instruction(fact: dict) -> bool:
    if fact["value"]["kind"] != "text":
        return False
    text = fact["value"]["value"]
    return any(
        not _NEGATED.search(text[max(0, match.start() - 12):match.start()])
        for pattern in _INSTRUCTIONS for match in pattern.finditer(text)
    )
