"""Load the frozen CareFund policy or an explicitly supplied policy file."""

import json
from pathlib import Path

from ..rules import ValidationPolicy


CAREFUND_V1_POLICY_PATH = Path(__file__).resolve().parent / "carefund_v1.json"


def load_policy(path: str | Path) -> ValidationPolicy:
    """Load the named CareFund V1 policy or an explicit JSON path."""
    source = CAREFUND_V1_POLICY_PATH if str(path) == "carefund_v1" else Path(path)
    return ValidationPolicy.from_dict(json.loads(source.read_text(encoding="utf-8-sig")))
