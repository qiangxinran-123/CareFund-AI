"""Business completeness rules must be explicitly chosen by the team."""

from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class ValidationPolicy:
    required_fields: tuple[str, ...]
    document_required_fields: tuple[str, ...] = ()
    require_processed_document: bool = True
    require_user_confirmation: bool = True
    field_kinds: Mapping[str, str] = field(default_factory=dict)
    recommended_fields: tuple[str, ...] = ()
    recommended_document_fields: tuple[str, ...] = ()
    policy_name: str | None = None
    notice: str = ""
    draft_issue_scope: str = "all"

    def __post_init__(self) -> None:
        for name in ("required_fields", "document_required_fields", "recommended_fields", "recommended_document_fields"):
            fields = getattr(self, name)
            if not isinstance(fields, (tuple, list)) or any(
                not isinstance(field, str) or not re.fullmatch(r"[a-z][a-z0-9_.]{1,127}", field)
                for field in fields
            ):
                raise ValueError(f"{name} must contain contract-compatible fact field names.")
            if len(set(fields)) != len(fields):
                raise ValueError(f"{name} contains duplicate field names.")
            object.__setattr__(self, name, tuple(fields))
        if not self.required_fields:
            raise ValueError("An explicit, non-empty required_fields policy is required.")
        if not set(self.document_required_fields) <= set(self.required_fields):
            raise ValueError("document_required_fields must be a subset of required_fields.")
        if set(self.recommended_fields) & set(self.required_fields):
            raise ValueError("recommended_fields must not duplicate required_fields.")
        if self.policy_name is not None and (
            not isinstance(self.policy_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", self.policy_name)
        ):
            raise ValueError("policy_name must be a stable local rule-set name.")
        if not isinstance(self.notice, str) or self.draft_issue_scope not in ("all", "blocking"):
            raise ValueError("Invalid policy notice or draft_issue_scope.")
        for name in ("require_processed_document", "require_user_confirmation"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be a boolean.")
        if not isinstance(self.field_kinds, Mapping) or any(
            not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_.]{1,127}", name)
            or kind not in ("text", "date", "money", "integer", "boolean")
            for name, kind in self.field_kinds.items()
        ):
            raise ValueError("field_kinds must map fact fields to supported FactValue kinds.")
        object.__setattr__(self, "field_kinds", MappingProxyType(dict(self.field_kinds)))

    @classmethod
    def from_dict(cls, value: dict) -> "ValidationPolicy":
        allowed = {
            "required_fields", "document_required_fields",
            "require_processed_document", "require_user_confirmation",
            "field_kinds",
            "recommended_fields", "recommended_document_fields", "policy_name", "notice", "draft_issue_scope",
        }
        if not isinstance(value, dict) or set(value) - allowed or "required_fields" not in value:
            raise ValueError("Invalid validation policy keys; required_fields is mandatory.")
        return cls(**value)
