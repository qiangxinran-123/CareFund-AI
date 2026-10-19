"""Conservative literal checks; no diagnosis, authenticity claim or LLM call."""

from datetime import date
from decimal import Decimal, localcontext
import re
import unicodedata


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


def canonical(value: dict) -> tuple:
    kind, raw = value["kind"], value["value"]
    if kind == "money":
        return kind, raw["currency"], raw["amount_minor"]
    return kind, normalize(raw).strip() if kind == "text" else raw


_NUMBER = r"(?<![\d.,+\-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\d.,])"
_MONEY = re.compile(
    rf"(?P<prefix>人民币|CNY|RMB|￥|¥|USD|US\$|\$|美元|EUR|€|欧元|GBP|£|英镑|JPY|日元)\s*"
    rf"(?P<before>{_NUMBER})\s*(?P<before_unit>万|亿)?(?:\s*元)?"
    rf"|(?P<after>{_NUMBER})\s*(?P<after_unit>万|亿)?\s*"
    r"(?P<suffix>人民币|美元|欧元|英镑|日元|元)",
    re.IGNORECASE,
)
_CURRENCIES = {
    "人民币": ("CNY", 100), "cny": ("CNY", 100), "rmb": ("CNY", 100),
    "¥": ("CNY", 100), "元": ("CNY", 100),
    "usd": ("USD", 100), "美元": ("USD", 100),
    "us$": ("USD", 100), "$": ("USD", 100),
    "eur": ("EUR", 100), "欧元": ("EUR", 100),
    "€": ("EUR", 100),
    "gbp": ("GBP", 100), "英镑": ("GBP", 100),
    "£": ("GBP", 100),
    "jpy": ("JPY", 1), "日元": ("JPY", 1),
}


def money_mentions(text: str) -> set[tuple[str, int]]:
    mentions = set()
    for match in _MONEY.finditer(normalize(text)):
        marker = match["prefix"] or match["suffix"]
        currency, scale = _CURRENCIES[marker]
        digits = (match["before"] or match["after"]).replace(",", "")
        unit = match["before_unit"] or match["after_unit"]
        with localcontext() as context:
            context.prec = max(28, len(digits) + 12)
            amount = Decimal(digits) * {None: 1, "万": 10000, "亿": 100000000}[unit] * scale
        if amount == amount.to_integral_value():
            mentions.add((currency, int(amount)))
    return mentions


_DATE = re.compile(r"(?<!\d)(\d{4})(?:[-/.年])(\d{1,2})(?:[-/.月])(\d{1,2})日?(?!\d)")


def date_mentions(text: str) -> set[str]:
    mentions = set()
    for match in _DATE.finditer(normalize(text)):
        try:
            mentions.add(date(*(int(part) for part in match.groups())).isoformat())
        except ValueError:
            continue
    return mentions


def numeric_mentions(text: str) -> set[Decimal]:
    """Numbers outside dates, including amounts whose currency unit was omitted."""
    def hide_valid_date(match):
        try:
            date(*(int(part) for part in match.groups()))
        except ValueError:
            return match[0]
        return " "

    text = _DATE.sub(hide_valid_date, normalize(text))
    mentions = set()
    for match in re.finditer(rf"(?P<number>{_NUMBER})\s*(?P<unit>万|亿)?", text):
        digits = match["number"].replace(",", "")
        with localcontext() as context:
            context.prec = max(28, len(digits) + 12)
            mentions.add(Decimal(digits) * {None: 1, "万": 10000, "亿": 100000000}[match["unit"]])
    return mentions


def fact_numbers(value: dict) -> set[Decimal]:
    kind, raw = value["kind"], value["value"]
    if kind == "money":
        # Only these currencies have an implemented unit conversion in V1.
        scale = {"CNY": 100, "USD": 100, "EUR": 100, "GBP": 100, "JPY": 1}.get(raw["currency"])
        if scale is not None:
            with localcontext() as context:
                context.prec = max(28, len(str(raw["amount_minor"])) + 12)
                return {Decimal(raw["amount_minor"]) / scale}
    elif kind == "integer":
        return {Decimal(raw)}
    elif kind == "text":
        return numeric_mentions(raw)
    return set()


def supported_by(value: dict, excerpt: str) -> bool:
    """Only literal support. Ambiguity is sent back for clarification."""
    kind, raw = value["kind"], value["value"]
    if kind == "money":
        return (raw["currency"], raw["amount_minor"]) in money_mentions(excerpt)
    if kind == "date":
        return raw in date_mentions(excerpt)
    text = normalize(excerpt)
    if kind == "integer":
        return re.search(rf"(?<![\w.\-]){raw}(?![\w.])", text) is not None
    if kind == "boolean":
        literal = "true" if raw else "false"
        return re.search(rf"(?<!\w){literal}(?!\w)", text) is not None
    needle = normalize(raw).strip()
    # Entire, identical excerpts preserve punctuation, negation and uncertainty.
    # Splitting first would reject faithful multi-sentence or punctuated facts.
    if needle and needle == text.strip():
        return True
    qualifiers = ("无", "未见", "否认", "排除", "疑似", "可能", "考虑", "待排", "未确诊", "不支持")
    for sentence in re.split(r"[。！？!?;；\n]", text):
        if needle and needle in sentence:
            # Preserve nearby negation and uncertainty instead of turning it into a diagnosis.
            if not any(word in sentence and word not in needle for word in qualifiers):
                return True
    return False


def supports_cost_field(field: str, value: dict, excerpt: str) -> bool:
    """Require explicit cost meaning in the same clause as the claimed amount.

    A matching number alone must not turn an estimate into a payment (or vice
    versa). Ambiguous/unsupported wording stays blocked for manual clarification.
    These local rules cover only the two existing treatment cost fields.
    """
    if field not in ("treatment.paid_cost", "treatment.estimated_cost"):
        return True
    if value["kind"] != "money":
        return False
    paid = ("已支付", "已付", "已缴", "已交", "已结算", "实付", "实缴", "支付成功", "缴费成功")
    estimated = ("预估", "预计", "估算", "预算", "估计", "预期费用")
    wanted, other = (paid, estimated) if field == "treatment.paid_cost" else (estimated, paid)
    negative = ("未支付", "未付款", "未付", "未缴", "未交", "未结算", "未实付", "尚未", "没有", "并非", "不是", "不代表", "不等于", "不含", "不包括", "不计", "尚无", "暂无", "非预估", "非预计")
    for clause in re.split(r"[。！？!?;；\n]|(?<!\d),|,(?!\d)", normalize(excerpt)):
        if any(marker in clause for marker in negative):
            continue
        if any(marker in clause for marker in wanted) and not any(marker in clause for marker in other):
            if supported_by(value, clause):
                return True
    return False
