"""Explicit local policy loading. Never silently replace missing configuration."""

import json
from pathlib import Path

from ..rules import ValidationPolicy


DEMO_V1_POLICY_PATH = Path(__file__).resolve().parent / "demo_v1.json"


def load_policy(path: str | Path) -> ValidationPolicy:
    """Load the named demo or an explicit path; I/O and format errors propagate."""
    source = DEMO_V1_POLICY_PATH if str(path) == "demo_v1" else Path(path)
    return ValidationPolicy.from_dict(json.loads(source.read_text(encoding="utf-8-sig")))
