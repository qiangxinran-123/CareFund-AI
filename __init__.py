"""CareFund-AI D module: deterministic evidence and fact validation."""

from .export_checker import validate_for_confirmation, validate_for_export
from .fact_checker import validate
from .rules import ValidationPolicy
from .schema import ContractValidationError
from .agent_adapter import (
    AgentAdaptationError, build_validation_request, prepare_agent_draft_request,
    validate_agent_draft,
    validate_for_generation,
)
from .policies import DEMO_V1_POLICY_PATH, load_policy

__all__ = [
    "validate", "validate_for_confirmation", "validate_for_export",
    "ValidationPolicy", "ContractValidationError",
    "AgentAdaptationError", "build_validation_request", "prepare_agent_draft_request",
    "validate_agent_draft",
    "validate_for_generation", "load_policy", "DEMO_V1_POLICY_PATH",
]

