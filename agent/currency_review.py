"""Partial prose review for evaluations, not a runtime fact or policy validator.

A match requests contextual review. It also matches attributed or negated claims:
those may be legitimate, so a match must never be treated as proof of a violation.
Historical batch_check.semantic_checks is intentionally unchanged.
"""
import re

PLATFORM_CURRENCY_FLAG = 'platform_currency_claim_needs_context_review'
_CLAIM = re.compile(
    r'平台[^。！？\n；]{0,24}(?:常用|通常|默认|惯用|习惯|接受|支持)'
    r'[^。！？\n；]{0,18}(?:人民币|美元|欧元|港币|日元|币种|货币|CNY|USD|EUR|RMB)',
    re.IGNORECASE,
)


def currency_review_flags(result):
    """Scan generated warnings and questions; return labels, never original text."""
    prose = list(result.get('warnings', []))
    prose.extend(q.get(k, '') for q in result.get('questions', []) for k in ('question', 'reason'))
    return [PLATFORM_CURRENCY_FLAG] if any(_CLAIM.search(t) for t in prose) else []
