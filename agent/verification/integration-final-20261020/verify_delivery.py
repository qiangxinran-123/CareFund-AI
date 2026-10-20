"""Verify the final ZIP from a fresh ignored extraction; no real API calls."""
import argparse
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--team-root', type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    receipt = archive.with_suffix('.verified.json')
    if receipt.exists():
        raise SystemExit('Preserve the existing verification receipt.')
    stage_root = (ROOT / 'agent/.local').resolve()
    stage = stage_root / ('delivery-int-final-' + uuid.uuid4().hex)
    assert stage.resolve().is_relative_to(stage_root)
    stage.mkdir()
    sha = lambda raw: hashlib.sha256(raw).hexdigest()
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        names = bundle.namelist()
        manifest = json.loads(bundle.read('PACKAGE_MANIFEST.json'))
        assert len(names) == len(set(names))
        assert set(names) == {i['path'] for i in manifest['files']} | {'PACKAGE_MANIFEST.json'}
        for name in names:
            rel = PurePosixPath(name)
            assert not rel.is_absolute() and '..' not in rel.parts and '\\' not in name
            assert name.startswith('agent/') or name in ('PACKAGE_MANIFEST.json', 'RECEIVE_README.md')
            assert not set(rel.parts).intersection({'.local', '.git', '.venv', '__pycache__'})
            target = stage.joinpath(*rel.parts)
            assert target.resolve().is_relative_to(stage)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bundle.read(name))
        for item in manifest['files']:
            raw = (stage / item['path']).read_bytes()
            assert len(raw) == item['size_bytes'] and sha(raw) == item['sha256']
    for rel, digest in manifest['current_contract_schema_fingerprints'].items():
        assert sha((ROOT / rel).read_bytes()) == digest
    shutil.copytree(ROOT / 'contracts', stage / 'contracts', ignore=shutil.ignore_patterns('__pycache__'))
    checks = json.loads((stage / 'agent/verification/integration-final-20261020/local-checks.json').read_bytes())
    for rel, digest in checks['runtime_sha256'].items():
        assert sha((stage / rel).read_bytes()) == digest
    environment = {k: v for k, v in os.environ.items() if not k.startswith(('DIFY_', 'DEEPSEEK_', 'OPENAI_'))}
    tests = []
    for command, count in [(['-m', 'unittest', 'discover', '-s', 'agent/tests'], 132),
                           (['-m', 'unittest', 'discover', '-s', 'contracts/tests'], 10),
                           (['-m', 'unittest', 'discover', '-s', 'agent/verification/full-csv-20261017', '-p', 'test_full_csv.py'], 20)]:
        result = subprocess.run([sys.executable, *command], cwd=stage, env=environment, capture_output=True, timeout=120)
        stderr = result.stderr.decode(errors='replace')
        match = re.search(r'Ran (\d+) tests', stderr)
        assert result.returncode == 0 and match and int(match[1]) == count, stderr
        tests.append(dict(command='python ' + ' '.join(command), tests=count, passed=True))
    if args.team_root:
        result = subprocess.run([sys.executable, 'agent/verification/integration-final-20261020/verify_peers.py',
            '--team-root', str(args.team_root.resolve())], cwd=stage, env=environment, capture_output=True, timeout=120)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        peer = json.loads(result.stdout)
        assert peer['tests'] == 9 and peer['passed'] and peer['new_model_calls'] == 0
        tests.append(dict(command='python verify_peers.py --team-root <peer-checkout>', tests=9, passed=True))
    report = dict(verified_at=datetime.now(timezone.utc).isoformat(), archive=str(archive), archive_sha256=sha(archive.read_bytes()),
        entries=len(names), manifest_verified=True, tests=tests, new_model_calls=0,
        supplied_shared_contracts_from_existing_checkout=True, credentials_removed_from_child_environment=True)
    with receipt.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
