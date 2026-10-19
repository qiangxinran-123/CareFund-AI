"""Build an A-only review package from Git-visible files; no network or Git mutation.

This packaging audit is for the original workstation with private evidence.
Recipients use replay.py and unit tests; real patient evidence is never bundled.
"""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DELIVERIES = ROOT.parent / 'deliveries'
ARCHIVE = DELIVERIES / 'CareFund-A-code-and-results-20261017-reviewed.zip'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()


def public_paths():
    raw = subprocess.check_output(['git', 'ls-files', '--cached', '--others',
                                   '--exclude-standard', '-z', '--', 'agent'], cwd=ROOT)
    return sorted(set(p for p in raw.decode().split('\0') if p))


def objects(value):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from objects(item)
    elif isinstance(value, list):
        for item in value:
            yield from objects(item)


def main(receive_readme=None):
    if ARCHIVE.exists():
        raise SystemExit('Append-only delivery: archive already exists')
    private = ROOT / 'agent/.local/full-csv-20261017'
    db = sqlite3.connect((private / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    rows = db.execute('SELECT status,record FROM attempts').fetchall()
    meta = {k: json.loads(v) for k, v in db.execute('SELECT key,value FROM meta')}
    db.close()
    assert len(rows) == 1350 and meta['last_progress']['status'] != 'running'
    real_payloads = set()
    checked_responses = 0
    for state, raw in rows:
        record = json.loads(raw)
        if record.get('response_file'):
            saved = (ROOT / record['response_file']).read_bytes()
            assert sha(saved) == record['response_sha256']
            real_payloads.add(sha(canon(json.loads(saved))))
            checked_responses += 1
    for line in (private / 'prepared-inputs.jsonl').open(encoding='utf-8'):
        item = json.loads(line)
        if item.get('request'):
            real_payloads.add(sha(canon(item['request'])))
    # Include the earlier minimized real-data suites in the exclusion comparison.
    for batch in ('expanded-20261017', 'currency-wording-20261017'):
        profile = json.loads((ROOT / f'agent/verification/{batch}/preparation.json').read_bytes())
        suite = json.loads((ROOT / profile['suite_file']).read_bytes())
        summary = json.loads((ROOT / f'agent/verification/{batch}/summary.json').read_bytes())
        index = {c['case_id']: c for c in summary['cases']}
        for case in suite['cases']:
            if case.get('data_class') == 'synthetic':
                continue
            real_payloads.add(sha(canon(case['request'])))
            record = index[case['case_id']]
            if record.get('response_file'):
                data = (ROOT / record['response_file']).read_bytes()
                assert sha(data) == record['response_sha256']
                real_payloads.add(sha(canon(json.loads(data))))
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    assert not any('/.local/' in p for p in tracked)
    private_files = subprocess.check_output(['git', 'ls-files', '--others', '--ignored',
        '--exclude-standard', '-z', '--', 'agent/.local/full-csv-20261017',
        'agent/.local/content-review-20261017'], cwd=ROOT).decode().split('\0')
    private_files = [p for p in private_files if p]
    assert private_files
    # Batch check-ignore instead of spawning one process for every response.
    probe = subprocess.run(['git', 'check-ignore', '-z', '--stdin'], cwd=ROOT,
        input=('\0'.join(private_files) + '\0').encode(), capture_output=True, check=True)
    assert set(probe.stdout.decode().split('\0')) - {''} == set(private_files)
    patterns = [re.compile(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}'),
                re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
    payloads = {}
    for rel in public_paths():
        path = ROOT / rel
        assert path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(ROOT)
        assert not set(path.parts).intersection({'.local', '.git', '.venv', '__pycache__'})
        assert path.suffix.lower() in ('.py', '.md', '.json', '.txt', '.yml', '.yaml', '.gitignore', '')
        raw = path.read_bytes()
        assert all(not p.search(raw) for p in patterns), 'Credential pattern in ' + rel
        if path.suffix == '.json':
            value = json.loads(raw)
            for obj in objects(value):
                if obj.get('schema_version') and ('candidate_facts' in obj or 'user_input' in obj):
                    assert sha(canon(obj)) not in real_payloads, 'Real medical payload in ' + rel
                if str(obj.get('data_class', '')).startswith(('minimal_', 'real_')):
                    assert 'request' not in obj and 'response' not in obj, 'Nonfiction payload in ' + rel
        payloads[rel] = raw
    subprocess.run(['git', '-c', 'core.safecrlf=false', 'diff', '--check'], cwd=ROOT, check=True)
    checks = dict(audited_at=datetime.now(timezone.utc).isoformat(),
        new_model_calls=0, batch_attempts=1350, ledger_counts=dict(Counter(s for s, r in rows)),
        saved_bulk_responses_hash_verified=checked_responses,
        private_ignored_untracked_files=len(private_files),
        public_agent_files_scanned=len(payloads), credential_pattern_hits=0,
        known_real_request_or_response_objects_in_public_files=0,
        raw_csv_files_in_package=0, non_agent_team_modules_in_package=0,
        privacy_limits='Credential patterns and known payload fingerprints supplement the explicit A-only file selection; not a universal deidentification proof.',
        committed_or_pushed=False)
    audit_raw = (json.dumps(checks, ensure_ascii=False, indent=2) + '\n').encode()
    with (HERE / 'package-audit.json').open('xb') as stream:
        stream.write(audit_raw)
    payloads[(HERE.relative_to(ROOT) / 'package-audit.json').as_posix()] = audit_raw
    readme = '''# CareFund A 模块：代码及测试结果（2026-10-17）

先阅读 agent/CURRENT_HANDOFF.md，再看 agent/verification/content-review-20261017/README.md。

本包只有 agent/，供小组仓库比较合入；不要覆盖其他成员模块。小组仓库的 contracts/schemas/ 是运行前提，包内清单仅记录其指纹，没有携带或改写它。

在已有小组仓库根目录：
1. 安装 agent/requirements.txt。
2. python -m unittest discover -s agent/tests（89 项离线测试）。
3. python agent/verification/content-review-20261017/replay.py（27 个虚构保存响应，0 次 API 调用）。

真实来源 60 条逐条对照的脱敏结论已附，原医疗输入、响应、CSV 和密钥均未附。结果不是医疗准确率，仍有警告/追问及草稿引述问题；v5 仅为未发布、未真实回归的候选。

新部署仅使用 workflow.deepseek-extract.yml 和 workflow.deepseek-draft.yml。历史文件和 candidate 文件不是当前线上导出。现有 Dify 应用的密钥不会随 DSL 迁移，接收方自行配置服务端密钥。已完成的是模块检查与 A/D 离线接口回放，完整 B/D 集成和最终导出仍待验证。

此包没有上传 GitHub。校验清单 PACKAGE_MANIFEST.json 覆盖包中其余文件的 SHA-256；它不包含任何密钥。先解压到独立目录审阅，再合入小组仓库。
'''.encode()
    payloads['RECEIVE_README.md'] = readme if receive_readme is None else receive_readme
    manifest = dict(created_at=datetime.now(timezone.utc).isoformat(),
        scope='A-only source and deidentified results; no private real medical payloads',
        entrypoint='agent/CURRENT_HANDOFF.md',
        current_contract_schema_fingerprints={p.relative_to(ROOT).as_posix(): sha(p.read_bytes())
            for p in sorted((ROOT / 'contracts/schemas').glob('*.json'))},
        files=[dict(path=rel, size_bytes=len(raw), sha256=sha(raw)) for rel, raw in sorted(payloads.items())])
    payloads['PACKAGE_MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    DELIVERIES.mkdir(exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for rel, raw in sorted(payloads.items()):
            archive.writestr(rel, raw)
    with zipfile.ZipFile(ARCHIVE) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(payloads)
        for item in manifest['files']:
            assert sha(archive.read(item['path'])) == item['sha256']
    receipt = dict(archive=str(ARCHIVE.resolve()), size_bytes=ARCHIVE.stat().st_size,
                   sha256=sha(ARCHIVE.read_bytes()), entries=len(payloads), checks=checks)
    with (DELIVERIES / (ARCHIVE.stem + '.receipt.json')).open('x', encoding='utf-8') as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
    print(json.dumps(receipt, ensure_ascii=True))


if __name__ == '__main__':
    main()
