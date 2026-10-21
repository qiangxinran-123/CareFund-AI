"""Regression guard against broken conflict resolution in the D package."""

import ast
from contextlib import redirect_stdout
import io
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from validation import load_policy
from validation.__main__ import main
from validation.tests.fixture_integrity import original_fixture_bytes

ROOT = Path(__file__).resolve().parents[1]


class ImportIntegrityTests(unittest.TestCase):
    def test_all_validation_python_sources_parse_without_conflict_markers(self):
        for path in ROOT.rglob("*.py"):
            if set(path.relative_to(ROOT).parts) & {".venv", "__pycache__"}:
                continue
            with self.subTest(file=str(path.relative_to(ROOT))):
                source = path.read_text(encoding="utf-8-sig")
                ast.parse(source, filename=str(path))
                self.assertFalse(any(line.startswith(("<<<<<<<", "=======", ">>>>>>>")) for line in source.splitlines()))

    def test_policy_has_one_initializer_and_validates_recommended_fields(self):
        tree = ast.parse((ROOT / "rules/policy.py").read_text(encoding="utf-8-sig"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ValidationPolicy")
        self.assertEqual(1, sum(isinstance(node, ast.FunctionDef) and node.name == "__post_init__" for node in cls.body))
        data = json.loads((ROOT / "policies/demo_v1.json").read_text(encoding="utf-8-sig"))
        from validation import ValidationPolicy
        for key in ("recommended_fields", "recommended_document_fields"):
            with self.subTest(key=key):
                invalid = dict(data, **{key: ["INVALID FIELD"]})
                with self.assertRaises(ValueError):
                    ValidationPolicy.from_dict(invalid)

    def test_cli_demo_v1_option_is_registered_once_and_executes_named_policy(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = main([str(ROOT / "examples/request.demo.json"), "--policy", "demo_v1"])
        report = json.loads(output.getvalue())
        self.assertEqual(0, code)
        self.assertTrue(report["can_finalize"])
        self.assertEqual("demo_v1", load_policy("demo_v1").policy_name)

    def test_accidental_nested_validation_package_is_absent(self):
        self.assertFalse((ROOT / "validation").exists(), "Remove duplicate validation/validation after preserving current outer files.")

    def test_fixture_hash_allows_git_checkout_newlines(self):
        original = b"first\nsecond\n"
        entry = {"path": "synthetic.txt", "bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
        with patch.object(Path, "read_bytes", return_value=original.replace(b"\n", b"\r\n")):
            self.assertEqual(original, original_fixture_bytes(ROOT, entry))

    def test_fixture_hash_still_rejects_content_changes(self):
        original = b"first\nsecond\n"
        entry = {"path": "synthetic.txt", "bytes": len(original), "sha256": hashlib.sha256(original).hexdigest()}
        with patch.object(Path, "read_bytes", return_value=b"first\r\nchanged\r\n"):
            with self.assertRaises(ValueError):
                original_fixture_bytes(ROOT, entry)


if __name__ == "__main__":
    unittest.main()
