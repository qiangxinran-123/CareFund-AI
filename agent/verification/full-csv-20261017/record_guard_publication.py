"""Record reported guard publication and offline triage. No external calls."""
import json
import sqlite3
from datetime import datetime, timezone

from prepare import HERE, ROOT, PRIVATE, sha
from run_live import QUESTION_FORMAT_VERSION, question_format
from agent.agent_service import AgentService


def main():
    db = sqlite3.connect(PRIVATE / 'attempts.sqlite3')
    before = db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone()
    assert before == (85, 1488962)
    snapshot = (HERE / 'live-progress.json').read_bytes()
    assert json.loads(snapshot)['calls_attempted'] == 85
    with (HERE / 'phase3-progress.json').open('xb') as stream:
        stream.write(snapshot)
    decisions = json.loads((PRIVATE / 'review-decisions.json').read_bytes())
    for row in (84,85):
        assert str(row) not in decisions
        record = json.loads(db.execute('SELECT record FROM attempts WHERE source_row=?', (row,)).fetchone()[0])
        assert record['error'] == 'Schema validation failed: AgentExtractResponse (required at schema properties/questions/items/required; missing required)'
        path = ROOT / record['response_file']
        assert sha(path.read_bytes()) == record['response_sha256']
        normalized = question_format(path.read_text(encoding='utf-8'))
        paths = json.loads(normalized['normalization_report'])['inserted_false_paths']
        assert paths == ['/questions/0/required','/questions/1/required','/questions/2/required']
        AgentService(None).validate(json.loads(normalized['result']), 'AgentExtractResponse')
        decisions[str(row)] = dict(
            disposition='confirmed_missing_question_required_kept_failed_continue_new_rows',
            request_sha256=record['request_sha256'], evidence_file=record['response_file'],
            evidence_sha256=record['response_sha256'], retry_failed_row=False,
            raw_model_issue_fixed=False, previous_failure_status_unchanged=True,
            reason='Only omitted optional-question policy flag. Continue new rows after reported code publication; compare returned raw text and processing report.')
    (PRIVATE / 'review-decisions.json').write_bytes((json.dumps(decisions,ensure_ascii=False,indent=2)+'\n').encode())
    old_publication = db.execute("SELECT value FROM meta WHERE key='active_publication'").fetchone()[0]
    candidate = ROOT / 'agent/workflow.deepseek-extract.question-guard-candidate.yml'
    code = ROOT / 'agent/dify_question_format.py'
    append = ROOT / 'agent/prompts/extract-json-v4-append.md'
    publication = dict(epoch='question-format-guard-v1-user-reported',
        recorded_at=datetime.now(timezone.utc).isoformat(),
        user_statement='所有步骤都弄好了，发布过了，接下来干什么',
        publication_verified_by_export=False, original_attempts=85, starts_after_source_row=85,
        question_format_version=QUESTION_FORMAT_VERSION,
        candidate_dsl_file=candidate.relative_to(ROOT).as_posix(), candidate_dsl_sha256=sha(candidate.read_bytes()),
        code_file=code.relative_to(ROOT).as_posix(), code_sha256=sha(code.read_bytes()),
        append_file=append.relative_to(ROOT).as_posix(), append_sha256=sha(append.read_bytes()),
        original_budget_and_call_cap_preserved=True, cumulative_budget_cny=20,
        cumulative_call_cap=84712, retry_failed_rows=False,
        verification_plan='One unattempted row first. Require raw_result and normalization_report, compare with exact local guard; then review before dispatching more.',
        note='Publication based on user statement, no fresh DSL yet. Runtime verification is per response; it does not prove all editor settings.')
    with (HERE / 'publication-question-guard.json').open('xb') as stream:
        stream.write((json.dumps(publication,ensure_ascii=False,indent=2)+'\n').encode())
    with db:
        db.execute("INSERT INTO meta VALUES ('previous_publication_before_guard',?)", (old_publication,))
        db.execute("UPDATE meta SET value=? WHERE key='active_publication'", (json.dumps(publication,ensure_ascii=False),))
    assert db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone() == before
    db.close()
    print(json.dumps({'recorded_publication':True,'preserved_attempts':85,'cost_upper_bound_cny':1.488962,'generation_calls':0}))


if __name__ == '__main__':
    main()
