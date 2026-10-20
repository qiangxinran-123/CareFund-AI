"""Build the current D-only GitHub upload, excluding other modules and secrets."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".venv", "venv", "__pycache__", ".git", ".local", ".pytest_cache"}
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".yaml"}
MANIFEST = "validation/verification/github-upload-manifest.json"


def build(output: Path) -> dict:
    if output.exists():
        raise FileExistsError("Choose a fresh delivery path; an earlier ZIP will not be overwritten.")
    command = [sys.executable, "-B", "-m", "unittest", "contracts.tests.test_contracts",
               "validation.tests.test_validation", "validation.tests.test_agent_adapter",
               "validation.tests.test_latest_agent", "validation.tests.test_demo_v1", "-v"]
    test = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if test.returncode:
        raise RuntimeError("Regression failed; package was not built.\n" + test.stdout + test.stderr)
    files = {}
    for path in sorted((ROOT / "validation").rglob("*")):
        relative = path.relative_to(ROOT)
        if not path.is_file() or set(relative.parts) & EXCLUDED:
            continue
        if path.suffix not in ALLOWED_SUFFIXES and path.name != ".gitkeep":
            continue
        if path.name.startswith(".env"):
            raise ValueError("Environment files must never be included.")
        if relative.as_posix() == MANIFEST:
            continue
        files[relative.as_posix()] = path.read_bytes()
    files["validation/verification/int07_int08/package-tests.txt"] = (test.stdout + test.stderr).encode("utf-8")
    manifest = {
        "scope": "validation/ only", "issues": ["INT-07", "INT-08"],
        "source": "CareFund-AI-main (2).zip plus D changes, 2026-10-20",
        "manifest_excludes_itself": True,
        "files": [{"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in sorted(files.items())],
    }
    files[MANIFEST] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None or len(archive.namelist()) != len(files):
            raise RuntimeError("ZIP integrity check failed.")
        for entry in manifest["files"]:
            data = archive.read(entry["path"])
            if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                raise RuntimeError("ZIP content verification failed.")
    return {"zip": str(output), "bytes": output.stat().st_size, "files": len(files),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "top_level": ["validation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=True))


if __name__ == "__main__":
    main()
