"""Verify a fresh extraction against this workstation's shared contracts.

Keeps an ignored extraction for inspection. Runs only offline checks and writes
an append-only verification receipt beside the ZIP; no Git or network action.
Recipients can instead merge agent/ into their team checkout and run the
commands in CURRENT_HANDOFF.md.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import uuid
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main(archive):
    archive = archive.resolve(strict=True)
    output = archive.with_suffix('.verified.json')
    if output.exists():
        raise SystemExit('Verification receipt exists; preserve the previous result.')
    stage_root = (ROOT / 'agent/.local').resolve(strict=True)
    stage = stage_root / ('delivery-check-' + uuid.uuid4().hex)
    assert stage.resolve().is_relative_to(stage_root)
    stage.mkdir()
    with zipfile.ZipFile(archive) as source:
        assert source.testzip() is None
        names = source.namelist()
        assert len(set(names)) == len(names)
        manifest = json.loads(source.read('PACKAGE_MANIFEST.json'))
        expected = {item['path'] for item in manifest['files']}
        assert set(names) == expected | {'PACKAGE_MANIFEST.json'}
        for name in names:
            path = PurePosixPath(name)
            assert not path.is_absolute() and '..' not in path.parts and '\\' not in name
            assert name.startswith('agent/') or name in ('PACKAGE_MANIFEST.json', 'RECEIVE_README.md')
            assert not set(path.parts).intersection({'.local', '.git', '.venv', '__pycache__'})
            target = stage.joinpath(*path.parts)
            assert target.resolve().is_relative_to(stage)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read(name))
        for item in manifest['files']:
            raw = (stage / item['path']).read_bytes()
            assert len(raw) == item['size_bytes'] and sha(raw) == item['sha256']
    for rel, digest in manifest['current_contract_schema_fingerprints'].items():
        assert sha((ROOT / rel).read_bytes()) == digest
    # Shared contracts come from the existing team checkout, never from the ZIP.
    shutil.copytree(ROOT / 'contracts', stage / 'contracts', ignore=shutil.ignore_patterns('__pycache__'))
    checks = json.loads((stage / 'agent/verification/content-fix-20261017/local-checks.json').read_bytes())
    for rel, digest in checks['runtime_sha256'].items():
        assert sha((stage / rel).read_bytes()) == digest
    for rel, digest in checks['frozen_evidence_sha256'].items():
        assert sha((ROOT / rel).read_bytes()) == digest
    environment = {k: v for k, v in os.environ.items() if not k.startswith(('DIFY_', 'DEEPSEEK_', 'OPENAI_'))}
    commands = [
        (['-m', 'unittest', 'discover', '-s', 'agent/tests'], 108),
        (['-m', 'unittest', 'discover', '-s', 'contracts/tests'], 10),
        (['-m', 'unittest', 'discover', '-s', 'agent/verification/full-csv-20261017', '-p', 'test_full_csv.py'], 20),
    ]

    def test(job):
        args, expected_count = job
        result = subprocess.run([sys.executable, *args], cwd=stage, env=environment,
                                capture_output=True, timeout=300)
        text = result.stderr.decode('utf-8', errors='replace')
        match = re.search(r'Ran (\d+) tests?', text)
        assert result.returncode == 0 and match and int(match[1]) == expected_count, text
        return dict(command='python ' + ' '.join(args), tests=expected_count, passed=True,
                    output_sha256=sha(result.stdout + result.stderr))

    with ThreadPoolExecutor(max_workers=3) as pool:
        tests = list(pool.map(test, commands))
    replay = subprocess.run([sys.executable, 'agent/verification/content-fix-20261017/verify_saved.py'],
                            cwd=stage, env=environment, capture_output=True, timeout=300)
    assert replay.returncode == 0, replay.stderr.decode(errors='replace')
    replay_report = json.loads(replay.stdout)
    assert replay_report['new_model_calls'] == 0 and replay_report['code_policy_regression_passed']
    for rel, digest in checks['frozen_evidence_sha256'].items():
        assert sha((ROOT / rel).read_bytes()) == digest
    report = dict(verified_at=datetime.now(timezone.utc).isoformat(), archive=str(archive),
        archive_sha256=sha(archive.read_bytes()), extracted_to=str(stage),
        entries=len(names), manifest_verified=True, supplied_shared_contracts_from_existing_checkout=True,
        tests=tests, saved_synthetic_replay=replay_report, new_model_calls=0,
        frozen_evidence_unchanged=True, credentials_removed_from_child_environment=True,
        committed_or_pushed=False)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    args = parser.parse_args()
    main(args.archive)
