"""Offline CLI. Stdout is JSON; 0=allowed, 1=blocked, 2=invalid input."""

import argparse
import json
from pathlib import Path
import sys
from uuid import uuid4

from . import ContractValidationError, load_policy, validate, validate_for_export


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Check CareFund-AI facts locally.")
    parser.add_argument("request", type=Path, help="ValidationRequest JSON file")
    parser.add_argument("--policy", help="Explicit policy JSON path or demo_v1; no implicit fallback")
    parser.add_argument("--application", type=Path)
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--export-request", type=Path)
    args = parser.parse_args(argv)
    if any((args.application, args.draft, args.export_request)) and not all(
        (args.application, args.draft, args.export_request)
    ):
        parser.error("export checking requires --application, --draft and --export-request together")

    def read(path):
        return json.loads(path.read_text(encoding="utf-8-sig"))

    try:
        policy = load_policy(args.policy) if args.policy else None
        request = read(args.request)
        if args.export_request:
            response = validate_for_export(
                request, read(args.application), read(args.draft), read(args.export_request), policy=policy,
            )
        else:
            response = validate(request, policy=policy)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        message = str(exc) if isinstance(exc, ContractValidationError) else "Invalid JSON input, policy or file."
        response = {
            "error": {"code": "INVALID_REQUEST", "message": message, "details": []},
            "request_id": "request_" + uuid4().hex,
        }
        print(json.dumps(response, ensure_ascii=True))
        return 2
    print(json.dumps(response, ensure_ascii=True, indent=2))
    return 0 if response["can_finalize"] else 1


if __name__ == "__main__":
    sys.exit(main())
