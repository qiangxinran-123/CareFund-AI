"""Conservative rejection of visible generation instructions in draft facts.

This is a bounded lexical guard, not general prompt-injection detection or a
medical classifier. It never edits a fact or interprets a clinical statement.
"""
import re

_PATTERNS = (
    r'(?:忽略|无视|绕过)(?:以上|之前|原有|原|所有|系统|先前|前面)?[^。\n]{0,10}(?:规则|指令|提示词|限制)',
    r'(?:编造|捏造|伪造)[^。\n]{0,24}(?:费用|金额|确诊|诊断|病情|证据)',
    r'(?:声明|声称|输出|宣布)[^。\n]{0,8}(?:已审核通过|审核通过|批准导出)',
    r'<\s*/?\s*(?:system|developer)\b[^>]*>',
    r'\b(?:ignore|disregard|override)\b[^.\n]{0,40}\b(?:instructions?|rules?|prompts?)\b',
    r'\b(?:fabricate|invent|forge)\b[^.\n]{0,40}\b(?:diagnosis|costs?|payments?|evidence|approval)\b',
)
_NEGATED = re.compile(r'(?:不要|不得|禁止|不能|不应|未|没有|拒绝|不|never|do not|don.t)\s*$', re.I)


def contains_generation_instruction(facts):
    for fact in facts:
        if fact['value']['kind'] != 'text':
            continue
        text = fact['value']['value']
        for pattern in _PATTERNS:
            for match in re.finditer(pattern, text, re.I):
                if not _NEGATED.search(text[max(0, match.start() - 12):match.start()]):
                    return True
    return False
