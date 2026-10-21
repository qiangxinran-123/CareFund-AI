"""Validate against the shared contracts, resolving references locally only."""

from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, validators
from referencing import Registry, Resource


class ContractValidationError(ValueError):
    """A malformed input; the message deliberately excludes rejected values."""


_StrictValidator = validators.extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, instance: type(instance) is int,
    ),
)


@lru_cache(maxsize=1)
def _contracts() -> tuple[dict[str, dict], Registry]:
    directory = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in directory.glob("*.schema.json")
    }
    if len(schemas) != 6:
        raise RuntimeError("The six shared contracts/schemas files are required.")
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return schemas, registry


def check_model(instance: Any, filename: str, model: str) -> None:
    schemas, registry = _contracts()
    validator = _StrictValidator(
        {"$ref": f"{schemas[filename]['$id']}#/$defs/{model}"},
        registry=registry,
        format_checker=FormatChecker(),
    )
    error = next(validator.iter_errors(instance), None)
    if error is not None:
        path = "/" + "/".join(str(part) for part in error.absolute_path)
        raise ContractValidationError(
            f"{model}: invalid input at {path} (rule: {error.validator})."
        )
