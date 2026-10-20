"""Lightweight contract tests for CareFund-AI V1.

JSON Schema validates shape and local constraints. The helpers below deliberately
separate cross-object referential integrity and Backend-owned state/revision rules.
"""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any, Iterable

try:
    from jsonschema import Draft202012Validator, FormatChecker, RefResolver
    from jsonschema.exceptions import ValidationError
except ImportError as exc:  # pragma: no cover - gives a clear setup failure
    raise RuntimeError(
        'Contract tests require the lightweight dependency "jsonschema>=4.18,<5". '
        'Install it in your test environment with: '
        'python -m pip install "jsonschema>=4.18,<5"'
    ) from exc


CONTRACTS_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = CONTRACTS_DIR / "schemas"
EXAMPLE_DIR = CONTRACTS_DIR / "examples"
OPENAPI_PATH = CONTRACTS_DIR / "openapi.yaml"

SCHEMA_FILES = sorted(SCHEMA_DIR.glob("*.schema.json"))
EXAMPLE_TARGETS = {
    "application.example.json": ("application.schema.json", "ApplicationResponse"),
    "agent-response.example.json": ("agent.schema.json", "AgentExtractResponse"),
    "validation-result.example.json": ("validation.schema.json", "ValidationResult"),
    "draft.example.json": ("draft.schema.json", "Draft"),
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_json_pointer(document: Any, fragment: str) -> Any:
    if fragment in ("", "#"):
        return document
    if not fragment.startswith("#/"):
        raise AssertionError(f"Unsupported JSON Pointer fragment: {fragment}")
    current = document
    for raw_part in fragment[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def iter_refs(node: Any) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from iter_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from iter_refs(item)


def assert_file_refs_resolve(test: unittest.TestCase, source_path: Path, document: Any) -> None:
    for ref in iter_refs(document):
        if ref.startswith("https://"):
            continue
        file_part, separator, fragment_part = ref.partition("#")
        target_path = source_path if not file_part else (source_path.parent / file_part).resolve()
        test.assertTrue(target_path.is_file(), f"Missing $ref file from {source_path.name}: {ref}")
        target_doc = load_json(target_path)
        fragment = f"#{fragment_part}" if separator else ""
        try:
            resolve_json_pointer(target_doc, fragment)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            test.fail(f"Unresolvable $ref from {source_path.name}: {ref}: {exc}")


def assert_reference_integrity(
    application_example: dict[str, Any],
    agent_example: dict[str, Any],
    validation_example: dict[str, Any],
    draft_example: dict[str, Any],
) -> None:
    application_id = application_example["application"]["application_id"]
    application_revision = application_example["application"]["revision"]

    assert agent_example["application_id"] == application_id
    assert validation_example["application_id"] == application_id
    assert draft_example["application_id"] == application_id
    assert agent_example["application_revision"] == application_revision
    assert validation_example["application_revision"] == application_revision
    assert draft_example["application_revision"] == application_revision

    document_ids = {item["document_id"] for item in application_example["documents"]}
    evidence_by_id = {item["evidence_id"]: item for item in application_example["evidence"]}
    for evidence in evidence_by_id.values():
        assert evidence["document_id"] in document_ids, (
            f"Evidence {evidence['evidence_id']} references missing document "
            f"{evidence['document_id']}"
        )

    fact_by_id = {item["fact_id"]: item for item in agent_example["candidate_facts"]}
    for fact in fact_by_id.values():
        missing_evidence = set(fact["evidence_ids"]) - evidence_by_id.keys()
        assert not missing_evidence, (
            f"Fact {fact['fact_id']} references missing evidence: {sorted(missing_evidence)}"
        )

    for issue in validation_example["issues"]:
        missing_facts = set(issue["related_fact_ids"]) - fact_by_id.keys()
        assert not missing_facts, (
            f"Issue {issue['issue_id']} references missing facts: {sorted(missing_facts)}"
        )

    for section in draft_example["sections"]:
        missing_facts = set(section["fact_ids"]) - fact_by_id.keys()
        assert not missing_facts, (
            f"Draft section {section['section_id']} references missing facts: "
            f"{sorted(missing_facts)}"
        )


def confirmation_preconditions_met(
    application: dict[str, Any],
    draft: dict[str, Any],
    validation: dict[str, Any],
    requested_draft_revision: int,
) -> bool:
    """Representative Backend rule; JSON Schema alone cannot enforce this."""
    return (
        application["application_id"] == draft["application_id"]
        and application["revision"] == draft["application_revision"]
        and validation["application_revision"] == application["revision"]
        and draft["draft_revision"] == requested_draft_revision
        and draft["status"] == "generated"
        and validation["can_finalize"] is True
    )


def export_preconditions_met(
    application: dict[str, Any], draft: dict[str, Any], validation: dict[str, Any]
) -> bool:
    """Representative Backend rule for a current, confirmed, validated export."""
    return (
        application["application_id"] == draft["application_id"]
        and application["revision"] == draft["application_revision"]
        and validation["application_revision"] == application["revision"]
        and draft["status"] == "confirmed"
        and validation["can_finalize"] is True
    )


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schemas = {path.name: load_json(path) for path in SCHEMA_FILES}
        cls.store: dict[str, Any] = {}
        for path in SCHEMA_FILES:
            schema = cls.schemas[path.name]
            cls.store[schema["$id"]] = schema
            cls.store[path.resolve().as_uri()] = schema
        cls.examples = {name: load_json(EXAMPLE_DIR / name) for name in EXAMPLE_TARGETS}

    def validate_model(self, instance: Any, schema_file: str, model_name: str) -> None:
        schema = self.schemas[schema_file]
        wrapper = {"$ref": f"{schema['$id']}#/$defs/{model_name}"}
        resolver = RefResolver.from_schema(wrapper, store=self.store)
        Draft202012Validator(
            wrapper,
            resolver=resolver,
            format_checker=FormatChecker(),
        ).validate(instance)

    def test_all_json_schemas_are_valid_draft_2020_12(self) -> None:
        self.assertEqual(6, len(SCHEMA_FILES))
        for path in SCHEMA_FILES:
            with self.subTest(schema=path.name):
                schema = self.schemas[path.name]
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
                Draft202012Validator.check_schema(schema)
                assert_file_refs_resolve(self, path, schema)

    def test_openapi_structure_and_refs(self) -> None:
        openapi = load_json(OPENAPI_PATH)
        self.assertEqual("3.1.0", openapi["openapi"])
        self.assertEqual("1.0.0", openapi["info"]["version"])
        expected_paths = {
            "/api/v1/applications",
            "/api/v1/applications/{application_id}",
            "/api/v1/applications/{application_id}/documents",
            "/api/v1/applications/{application_id}/analyze",
            "/api/v1/applications/{application_id}/analysis",
            "/api/v1/applications/{application_id}/analysis/jobs/{job_id}",
            "/api/v1/applications/{application_id}/answers",
            "/api/v1/applications/{application_id}/draft",
            "/api/v1/applications/{application_id}/draft/confirm",
            "/api/v1/applications/{application_id}/export",
            "/api/v1/health",
        }
        self.assertEqual(expected_paths, set(openapi["paths"]))
        assert_file_refs_resolve(self, OPENAPI_PATH, openapi)

    def test_examples_validate(self) -> None:
        for example_name, (schema_file, model_name) in EXAMPLE_TARGETS.items():
            with self.subTest(example=example_name):
                self.validate_model(self.examples[example_name], schema_file, model_name)

    def test_example_reference_integrity(self) -> None:
        assert_reference_integrity(
            self.examples["application.example.json"],
            self.examples["agent-response.example.json"],
            self.examples["validation-result.example.json"],
            self.examples["draft.example.json"],
        )

    def test_missing_evidence_reference_is_rejected_by_cross_object_check(self) -> None:
        agent = copy.deepcopy(self.examples["agent-response.example.json"])
        agent["candidate_facts"][0]["evidence_ids"] = ["ev_missing_001"]
        with self.assertRaises(AssertionError):
            assert_reference_integrity(
                self.examples["application.example.json"],
                agent,
                self.examples["validation-result.example.json"],
                self.examples["draft.example.json"],
            )

    def test_illegal_enum_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.examples["validation-result.example.json"])
        invalid["issues"][0]["severity"] = "critical"
        with self.assertRaises(ValidationError):
            self.validate_model(invalid, "validation.schema.json", "ValidationResult")

    def test_negative_money_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.examples["agent-response.example.json"])
        invalid["candidate_facts"][1]["value"]["value"]["amount_minor"] = -1
        with self.assertRaises(ValidationError):
            self.validate_model(invalid, "agent.schema.json", "AgentExtractResponse")

    def test_invalid_date_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.examples["agent-response.example.json"])
        invalid["candidate_facts"][2]["value"]["value"] = "2026-02-30"
        with self.assertRaises(ValidationError):
            self.validate_model(invalid, "agent.schema.json", "AgentExtractResponse")

    def test_missing_required_field_is_rejected(self) -> None:
        invalid = copy.deepcopy(self.examples["draft.example.json"])
        del invalid["draft_id"]
        with self.assertRaises(ValidationError):
            self.validate_model(invalid, "draft.schema.json", "Draft")

    def test_stale_revision_fails_confirmation_and_export_preconditions(self) -> None:
        application = copy.deepcopy(self.examples["application.example.json"]["application"])
        draft = copy.deepcopy(self.examples["draft.example.json"])
        validation = copy.deepcopy(self.examples["validation-result.example.json"])
        validation["can_finalize"] = True

        application["revision"] += 1
        self.assertFalse(confirmation_preconditions_met(application, draft, validation, 1))

        draft["status"] = "confirmed"
        self.assertFalse(export_preconditions_met(application, draft, validation))


if __name__ == "__main__":
    unittest.main()
