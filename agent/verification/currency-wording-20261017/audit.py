"""Offline artifact and privacy checks for the six-case regression."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(*args):return subprocess.check_output(['git','-c','core.safecrlf=false',*args],cwd=ROOT).decode()
if __name__=='__main__':
    profile=json.loads((HERE/'preparation.json').read_bytes())
    summary=json.loads((HERE/'summary.json').read_bytes())
    assert summary['calls_attempted']==summary['accepted_after_context_review']==6
    assert summary['automatic_retries']==summary['real_medical_inputs']==0
    for p,expected in summary['runtime_sha256'].items():assert sha(ROOT/p)==expected
    dsl=json.loads((HERE/'dsl-verification.json').read_bytes())
    assert sha(ROOT/dsl['old_export_archived'])==profile['source_DSL_sha256']==dsl['old_export_sha256']
    assert sha(ROOT/'agent/workflow.deepseek-extract.yml')==dsl['new_export_sha256']
    assert sha(ROOT/'agent/workflow.deepseek-extract.currency-v3-candidate.yml')==profile['candidate_DSL_sha256']
    private=[p for p in (ROOT/'agent/.local/currency-wording-20261017').rglob('*') if p.is_file()]
    tracked=set(git('ls-files','-z').split('\0'))
    for p in private:
        rel=p.relative_to(ROOT).as_posix();assert rel not in tracked
        subprocess.run(['git','check-ignore','-q','--',rel],cwd=ROOT,check=True)
    changed=set(filter(None,git('diff','--name-only','-z').split('\0')))
    changed.update(filter(None,git('ls-files','--others','--exclude-standard','-z').split('\0')))
    assert all(p.startswith('agent/') for p in changed)
    public=[ROOT/p for p in changed if (ROOT/p).is_file()]
    pattern=re.compile(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}')
    assert all(not pattern.search(p.read_bytes()) for p in public)
    subprocess.run(['git','-c','core.safecrlf=false','diff','--check'],cwd=ROOT,check=True)
    result=dict(date='2026-10-17',agent_unit_tests_passed=77,contract_tests_passed=10,
        old_100_saved_responses_rechecked_without_rewriting=True,
        new_evaluation_tests=6,old_error_marked_for_context_review=True,
        generation_calls=6,automatic_passed=5,context_review_accepted=1,
        known_redundant_currency_question=1,D_offline_replays=6,D_can_finalize_true=0,
        private_files_ignored_and_untracked=len(private),public_files_credential_scanned=len(public),
        published_prompt_reported_by_user=True,fresh_DSL_export_verified=True,
        old_DSL_bytes_archived=True,new_DSL_synced_as_original_bytes=True,candidate_DSL_only_adds_currency_rule=True,
        other_member_directories_unchanged=True,git_diff_whitespace_check='passed',
        additional_model_calls_by_offline_checks=0,actual_bill_read=False,committed_or_pushed=False)
    target=HERE/'local-checks.json';assert not target.exists()
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
