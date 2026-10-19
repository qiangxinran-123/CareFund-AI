"""Offline provenance, privacy and artifact checks; no API or credential access."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('expanded_final_audit',HERE/'finalize.py')
FINAL=importlib.util.module_from_spec(spec);spec.loader.exec_module(FINAL)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)


if __name__=='__main__':
    summary=json.loads((HERE/'summary.json').read_bytes())
    accepted,checks=FINAL.verified_records(summary)
    d=json.loads((HERE/'ad-replay-summary.json').read_bytes())
    review=json.loads((HERE/'post-run-review.json').read_bytes())
    conclusion=json.loads((HERE/'evaluation-conclusion.json').read_bytes())
    assert conclusion['status']=='completed_with_content_finding'
    assert conclusion['supplemental_content_findings']==len(review['findings'])==1
    assert review['automatic_results_preserved'] and not conclusion['production_fix_published']
    assert d['mapped_extract_cases']==sum(c['operation']=='extract' for _,c,_ in accepted)
    assert all(r['contracts']=='passed' and r['input_unmodified'] for r in d['cases'])
    assert sha(FINAL.PRIVATE/'live-status.json')==summary['local_status_sha256']
    private=[p for p in FINAL.PRIVATE.rglob('*') if p.is_file()]
    tracked=set(git('ls-files','-z').decode().split('\0'))
    for p in private:
        rel=p.relative_to(ROOT).as_posix()
        assert rel not in tracked
        subprocess.run(['git','check-ignore','-q','--',rel],cwd=ROOT,check=True)
    profile=json.loads((HERE/'preparation.json').read_bytes())
    source_paths={
        'user_csv':Path(r'C:\Users\zxw01\Downloads\data_final(1).csv'),
        'MDCC':ROOT.parent/'CareFund-Codex-Handoff/CareFund-AI-main/agent/.local/mdcc/raw_data.csv'}
    assert all(sha(source_paths[k])==v for k,v in profile['source_sha256'].items())
    expected_production={
        'agent/agent_service.py':'9eed2c94cf38e1fa4ff381217e638d917eb682036d3611f281de8223792fbde0',
        'agent/extract_policy.py':'6e2bed965b56d4c85c8008ea25b1a2269d1f9f9b358571de4b089daf606e328a'}
    assert all(sha(ROOT/k)==v for k,v in expected_production.items())
    assert all(sha(ROOT/k)==v for k,v in summary['runtime_code_sha256'].items())
    workflows={
        'agent/workflow.deepseek-extract.yml':'b6288e27770394827eeeb9e83a6f65b25ad1a5db6ba1ceec58e6d208963d07b7',
        'agent/workflow.deepseek-draft.yml':'6ace13cd39a2980577b36801939b55e138912ff47f7e04ebd07e2e652300d052'}
    assert all(sha(ROOT/k)==v for k,v in workflows.items())
    changed=set(filter(None,git('diff','--name-only','-z').decode().split('\0')))
    changed.update(filter(None,git('ls-files','--others','--exclude-standard','-z').decode().split('\0')))
    assert all(p.startswith('agent/') for p in changed)
    public=[ROOT/p for p in changed if (ROOT/p).is_file()]
    credentials=re.compile(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}')
    assert all(not credentials.search(p.read_bytes()) for p in public)
    report_text=b'\n'.join(p.read_bytes() for p in HERE.iterdir() if p.suffix in ('.md','.json'))
    checked_medical_texts=0
    for _,case,response in accepted:
        if case['data_class']=='synthetic':continue
        for fact in response['candidate_facts']:
            if fact['field']=='patient.medical_summary':
                value=fact['value']['value']
                if len(value)>=10:
                    assert value.encode() not in report_text
                    checked_medical_texts+=1
    subprocess.run(['git','diff','--check'],cwd=ROOT,check=True)
    result=dict(date='2026-10-17',generation_calls=summary['calls_attempted'],
        overall_status=conclusion['status'],open_content_findings=len(review['findings']),
        offline_recheck=checks,D_extract_cases=d['mapped_extract_cases'],D_can_finalize_true=d['can_finalize_true'],
        private_files_ignored_and_untracked=len(private),public_files_credential_scanned=len(public),
        real_medical_texts_checked_absent_from_public_report=checked_medical_texts,
        source_fingerprints_unchanged=True,production_A_hashes_unchanged=True,
        workflow_export_hashes_unchanged=True,other_member_directories_unchanged=True,
        git_diff_whitespace_check='passed',full_unit_suite_rerun_this_turn=False,
        prior_unit_regression_evidence='agent/verification/scope-guard-20261017/local-checks.json',
        additional_model_calls_by_offline_checks=0,committed_or_pushed_this_turn=False,
        limits='Partial semantic checks; source records and saved responses remain local and ignored.')
    target=HERE/'local-checks.json'
    assert not target.exists()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
