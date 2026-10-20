
"""Build the current D-only GitHub upload, excluding other modules and secrets."""

import argparse
import hashlib
import json
from pathlib import Path

"""Build a scoped D delivery with original contract references and hashes."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform

import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".venv", "venv", "__pycache__", ".git", ".local", ".pytest_cache"}
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".yaml"}
MANIFEST = "validation/verification/github-upload-manifest.json"


ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".venv", "venv", "__pycache__", ".git", ".local", ".pytest_cache"}
ALLOWED_SUFFIXES = {".py", ".md", ".json", ".txt", ".yaml"}
PACKAGE_README = """# D 模块与最新版 A 适配交付包

先读 validation/CURRENT_STATUS.md，再读 validation/A_D_HANDOFF.md 的详细接入示例。

本包包含完整 validation/、未修改的 contracts/ 参考、合成测试夹具、离线回放结果及 SHA256 清单。
已有团队仓库请核对契约后只引入 validation/，在真实 feature/validation 分支提 PR；不要覆盖其他模块。
本包不是完整后端或可直接上线的系统，不含密钥、虚拟环境、真实患者数据或 Git 历史。

复现：在本目录执行 python -m pip install -r validation/requirements.txt，然后运行：

```powershell
python -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter validation.tests.test_latest_agent -v
python -B -m validation.tools.replay_latest_a --output local-replay-results
```

A 最新交付仍拒绝任何非空 validation_issue_ids，包括 D 的 info 提示；本次保留全部 ID，未绕过。
包含用户自述的草稿流程可能因此被暂停，需 A/B/D 确认严重性规则后统一。
测试为离线边界回放和 Mock 状态验证，没有新模型调用或真实后端事务验证。

FILE_MANIFEST.json 记录本包其他全部文件的大小及 SHA256（自身除外）。
DELIVERY_CHECKS.json 与 validation/verification/a_20261018/ 提供最新检查结果。
validation/verification/a_handoff/ 是 10 月 16 日的历史记录。
"""



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

        raise FileExistsError("Delivery already exists; choose a new --output path.")
    checks_directory = ROOT / "validation/verification/a_20261018"
    replay_summary = json.loads((checks_directory / "summary.json").read_text(encoding="utf-8"))
    contract_baseline = json.loads((checks_directory / "contract-baseline.json").read_text(encoding="utf-8"))
    for entry in contract_baseline:
        if hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Shared contracts changed from the A handoff.")
    command = [sys.executable, "-B", "-m", "unittest", "contracts.tests.test_contracts",
               "validation.tests.test_validation", "validation.tests.test_agent_adapter",
               "validation.tests.test_latest_agent", "-v"]
    test = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if test.returncode:
        raise RuntimeError("Local regression failed; delivery was not built.\n" + test.stderr)

    files = {}
    for directory in ("validation", "contracts"):
        for path in sorted((ROOT / directory).rglob("*")):
            relative = path.relative_to(ROOT)
            if not path.is_file() or set(relative.parts) & EXCLUDED:
                continue
            if path.suffix not in ALLOWED_SUFFIXES and path.name != ".gitkeep":
                continue
            if path.name.startswith(".env"):
                raise ValueError("Environment file must not be included.")
            files[relative.as_posix()] = path.read_bytes()
    files["README_先读我.md"] = PACKAGE_README.encode("utf-8")
    files["verification/d-contract-adapter-tests.txt"] = (test.stdout + test.stderr).encode("utf-8")
    source_checks = json.loads((checks_directory / "source-package-checks.json").read_text(encoding="utf-8"))
    checks = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "python": platform.python_version(), "source_label": replay_summary["source_label"],
        "source_zip_sha256": replay_summary["source_zip_sha256"],
        "shared_contract_files_unchanged": len(contract_baseline),
        "source_package_checks": source_checks,
        "d_contract_adapter_tests": {"command": "python -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter validation.tests.test_latest_agent -v", "exit_code": test.returncode, "log": "verification/d-contract-adapter-tests.txt"},
        "latest_replay_counts": replay_summary["counts"],
        "online_calls": 0, "scope": "validation only; contracts are unmodified references",
        "pending": ["A blocks all nonempty issue IDs including info; no filtering performed", "production completeness rules require team agreement", "backend transactions, real OCR and online workflow integration untested"],
    }
    files["DELIVERY_CHECKS.json"] = (json.dumps(checks, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    manifest = {"files": [{"path": path, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                           for path, content in sorted(files.items())]}
    files["FILE_MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    package_prefix = output.stem + "/"
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in sorted(files.items()):
            archive.writestr(package_prefix + path, content)
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("Archive CRC check failed.")
        for entry in manifest["files"]:
            content = archive.read(package_prefix + entry["path"])
            if hashlib.sha256(content).hexdigest() != entry["sha256"]:
                raise RuntimeError("Archive hash check failed.")
    return {"zip": str(output), "bytes": output.stat().st_size, "files": len(files),
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), ensure_ascii=True))


if __name__ == "__main__":
    main()
