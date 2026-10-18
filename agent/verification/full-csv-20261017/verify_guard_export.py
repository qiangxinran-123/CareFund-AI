"""Verify the supplied Code-node export before synchronizing local configuration.

Executes only reviewed local code, allowing trailing blank lines. No provider calls.
Historical attempts, usage and publication statements remain untouched.
"""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

from prepare import HERE, ROOT, PRIVATE, sha

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'agent/.local/dsl-verification-deps'))
import yaml
from agent.agent_service import AgentService

SUPPLIED = Path('C:/Users/zxw01/Downloads/CareFund-信息抽取与追问-修订版 (4).yml')
OLD_SHA = 'e98b2c7d631a86ba9de986d5c241cfd6478b327dad03e6057a81e4fc630ed233'


def main():
    raw = SUPPLIED.read_bytes()
    assert not re.search(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}', raw)
    actual = yaml.safe_load(raw)
    prior_raw = (HERE / 'verified-format-v4-export.yml').read_bytes()
    assert sha(prior_raw) == OLD_SHA
    prior = yaml.safe_load(prior_raw)
    assert actual['app'] == prior['app']
    assert actual['dependencies'] == prior['dependencies']
    for key in ('environment_variables', 'conversation_variables', 'features', 'rag_pipeline_variables'):
        assert actual['workflow'].get(key) == prior['workflow'].get(key)
    nodes = actual['workflow']['graph']['nodes']
    assert Counter(n['data']['type'] for n in nodes) == dict(start=1, llm=1, code=1, end=1)
    by_type = {n['data']['type']: n for n in nodes}
    before = {n['data']['type']: n for n in prior['workflow']['graph']['nodes']}
    start, llm, code, end = (by_type[k] for k in ('start', 'llm', 'code', 'end'))
    assert start['data']['variables'] == before['start']['data']['variables']
    for key in ('model', 'prompt_template', 'context', 'vision'):
        assert llm['data'].get(key) == before['llm']['data'].get(key)
    assert not llm['data'].get('structured_output_enabled')
    source = (ROOT / 'agent/dify_question_format.py').read_text(encoding='utf-8')
    embedded = code['data']['code']
    assert embedded.rstrip('\n') == source.rstrip('\n'), 'Only trailing blank lines may differ from reviewed source'
    assert code['data']['code_language'] == 'python3'
    variables = code['data']['variables']
    assert len(variables) == 1 and variables[0]['variable'] == 'llm_text'
    assert variables[0]['value_selector'] == [llm['id'], 'text']
    names = {'result', 'raw_result', 'normalization_report'}
    assert set(code['data']['outputs']) == names
    assert all(v['type'] == 'string' for v in code['data']['outputs'].values())
    assert len(end['data']['outputs']) == 3
    assert {v['variable'] for v in end['data']['outputs']} == names
    for value in end['data']['outputs']:
        assert value['value_selector'] == [code['id'], value['variable']]
        assert value['value_type'] == 'string'
    edges = actual['workflow']['graph']['edges']
    expected_edges = {(start['id'], llm['id']), (llm['id'], code['id']), (code['id'], end['id'])}
    assert len(edges) == 3 and {(e['source'], e['target']) for e in edges} == expected_edges
    for node in (llm, code):
        assert not node['data'].get('retry_config', {}).get('retry_enabled', False)
        assert not node['data'].get('error_strategy')

    namespace = {}
    exec(compile(embedded, '<verified-local-question-code>', 'exec'), namespace)
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri() + '?mode=ro', uri=True)
    records = [json.loads(item[0]) for item in db.execute('SELECT record FROM attempts ORDER BY source_row')]
    attempt_count, charge = db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone()
    db.close()
    requests = {}
    with (PRIVATE / 'prepared-inputs.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            if item['source_row'] > max(r['source_row'] for r in records):
                break
            requests[item['source_row']] = item['request']
    replay = Counter()
    inserted, syntax_rejected, unknown_rows = [], [], []
    for record in records:
        row = record['source_row']
        if record.get('wire_response_file'):
            captured = (ROOT / record['wire_response_file']).read_bytes()
            assert sha(captured) == record['wire_response_sha256']
            outputs = json.loads(captured)['data']['outputs']
            text = outputs.get('raw_result', outputs.get('result'))
        elif record.get('response_file'):
            saved = (ROOT / record['response_file']).read_bytes()
            assert sha(saved) == record['response_sha256']
            text = json.dumps(json.loads(saved), ensure_ascii=False)
            replay['reserialized_parsed_input_original_whitespace_unavailable'] += 1
        elif row == 44:
            recovered = json.loads((PRIVATE / 'failure-000044.dify-detail.json').read_bytes())['outputs']
            if isinstance(recovered, str):
                recovered = json.loads(recovered)
            text = recovered['result']
        else:
            unknown_rows.append(row)
            continue
        try:
            result = namespace['main'](text)
        except ValueError:
            syntax_rejected.append(row)
            continue
        assert result['raw_result'] == text
        processed = json.loads(result['result'])
        AgentService(lambda op, req: processed).extract(requests[row])
        paths = json.loads(result['normalization_report'])['inserted_false_paths']
        if paths:
            original = json.loads(text)
            for i, question in enumerate(processed['questions']):
                if 'required' not in original['questions'][i]:
                    assert question.pop('required') is False
            assert processed == original
            inserted.append(dict(source_row=row, inserted_false_count=len(paths)))
            replay['counterfactual_valid_after_policy'] += 1
        else:
            assert result['result'] == text
            replay['already_valid_preserved'] += 1
    assert sorted(syntax_rejected) == [44, 70]
    assert replay['already_valid_preserved'] == 81
    assert replay['counterfactual_valid_after_policy'] == 2
    assert sorted(unknown_rows) == [78, 87, 88]
    canonical = ROOT / 'agent/workflow.deepseek-extract.yml'
    assert sha(canonical.read_bytes()) in (OLD_SHA, sha(raw))
    archive = HERE / 'verified-question-guard-export.yml'
    if archive.exists():
        assert archive.read_bytes() == raw
    else:
        archive.write_bytes(raw)
    canonical.write_bytes(raw)
    report = dict(verified_at=datetime.now(timezone.utc).isoformat(),
        supplied_export_file=SUPPLIED.name, supplied_export_sha256=sha(raw),
        previous_canonical_export_sha256=OLD_SHA, canonical_synchronized=True,
        node_count=len(nodes), code_source_exactly_matches_reviewed_local=embedded == source,
        code_difference_limited_to_trailing_blank_lines=True,
        code_source_sha256=sha(embedded.encode()), graph_and_three_string_outputs_verified=True,
        model_prompt_start_variables_and_features_unchanged=True,
        retry_settings='disabled_or_absent_default_disabled', error_strategy='absent_default_fail',
        offline_replay_counts=dict(replay), counterfactual_insertions=inserted,
        malformed_historical_rows_still_rejected=syntax_rejected,
        timeout_rows_not_replayed=unknown_rows, historical_attempts_unchanged=attempt_count,
        historical_cost_upper_bound_cny=charge/1e6, generation_calls=0,
        limitation='Export verifies saved configuration, not the exact configuration of each historical run. Offline policy replay does not repair historical outcomes or prove model medical accuracy.')
    (HERE / 'verified-question-guard-export.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode())
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
