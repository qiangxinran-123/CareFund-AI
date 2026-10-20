"""Verify supplied DSL; prepare a deterministic optional-question policy node.

Offline only. Replay is counterfactual and never changes historical outcomes.
"""
from collections import Counter
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

from prepare import HERE, ROOT, PRIVATE, sha

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'agent/.local/yaml-validation-deps'))
import yaml
from agent.agent_service import AgentService, AgentError
from agent.dify_question_format import main as normalize

EXPORT = Path('C:/Users/zxw01/Downloads/CareFund-信息抽取与追问-修订版 (3).yml')
BEFORE_SHA = 'f4780099f9008ee478bdcc93409745641e7c75389f42232e1630adaee52511b6'
VERIFIED_SHA = 'e98b2c7d631a86ba9de986d5c241cfd6478b327dad03e6057a81e4fc630ed233'


def main():
    supplied = EXPORT.read_bytes()
    assert sha(supplied) == VERIFIED_SHA
    assert supplied == (ROOT / 'agent/workflow.deepseek-extract.json-v4-candidate.yml').read_bytes()
    actual = yaml.safe_load(supplied)
    assert not actual['workflow']['environment_variables']
    assert not re.search(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}', supplied)
    graph = actual['workflow']['graph']
    llm = next(n for n in graph['nodes'] if n['data']['type'] == 'llm')
    end = next(n for n in graph['nodes'] if n['data']['type'] == 'end')
    system = next(p['text'] for p in llm['data']['prompt_template'] if p['role'] == 'system')
    assert 'required' in system and (ROOT / 'agent/prompts/extract-json-v4-append.md').read_text(encoding='utf-8').strip() in system
    assert llm['data']['model']['completion_params']['response_format'] == 'json_object'
    assert not llm['data'].get('structured_output_enabled')
    canonical = ROOT / 'agent/workflow.deepseek-extract.yml'
    assert sha(canonical.read_bytes()) == BEFORE_SHA
    for path, data in ((HERE / 'pre-format-extract-export.yml', canonical.read_bytes()),
                       (HERE / 'verified-format-v4-export.yml', supplied)):
        with path.open('xb') as stream:
            stream.write(data)
    canonical.write_bytes(supplied)

    candidate = copy.deepcopy(actual)
    graph = candidate['workflow']['graph']
    node_id = '1792227420000'
    assert node_id not in {n['id'] for n in graph['nodes']}
    code_source = (ROOT / 'agent/dify_question_format.py').read_text(encoding='utf-8')
    position = {'x': end['position']['x'], 'y': end['position']['y']}
    code_node = dict(id=node_id, type='custom', width=242, height=100,
                     position=position, positionAbsolute=dict(position), selected=False,
                     sourcePosition='right', targetPosition='left', zIndex=0,
                     data=dict(type='code', title='追问可选标记与原文留存', selected=False,
                               desc='仅按当前规则为缺失 required 补 false；保留原文和记录；其他错误不修补。',
                               code_language='python3', code=code_source,
                               variables=[{'variable':'llm_text', 'value_selector':[llm['id'], 'text']}],
                               outputs={name:{'type':'string','children':None}
                                        for name in ('result','raw_result','normalization_report')},
                               retry_config={'retry_enabled':False, 'max_retries':0, 'retry_interval':1000}))
    new_end = next(n for n in graph['nodes'] if n['data']['type'] == 'end')
    new_end['position']['x'] += 310
    new_end['positionAbsolute']['x'] += 310
    new_end['data']['outputs'] = [dict(variable=name, value_type='string', value_selector=[node_id,name])
                                for name in ('result','raw_result','normalization_report')]
    new_llm = next(n for n in graph['nodes'] if n['data']['type'] == 'llm')
    new_llm['data']['retry_config'] = {'retry_enabled':False, 'max_retries':0, 'retry_interval':1000}
    graph['nodes'].insert(-1, code_node)
    direct = next(e for e in graph['edges'] if e['source']==llm['id'] and e['target']==end['id'])
    graph['edges'].remove(direct)
    for src, dst, stype, dtype in ((llm['id'],node_id,'llm','code'), (node_id,end['id'],'code','end')):
        graph['edges'].append(dict(id=src+'--'+dst+'-target', source=src, target=dst,
            sourceHandle='source', targetHandle='target', type='custom', zIndex=0,
            data={'isInIteration':False,'isInLoop':False,'sourceType':stype,'targetType':dtype}))
    candidate_path = ROOT / 'agent/workflow.deepseek-extract.question-guard-candidate.yml'
    encoded = yaml.safe_dump(candidate, allow_unicode=True, sort_keys=False).encode()
    with candidate_path.open('xb') as stream:
        stream.write(encoded)
    parsed = yaml.safe_load(encoded)
    embedded = next(n['data']['code'] for n in parsed['workflow']['graph']['nodes'] if n['data']['type']=='code')
    assert embedded == code_source
    assert new_llm['data']['prompt_template'] == llm['data']['prompt_template']
    assert new_llm['data']['model'] == llm['data']['model']
    # Execute the exact standalone Code-node source, not an alternate mock.
    namespace = {}
    exec(compile(embedded, '<dify-question-format-candidate>', 'exec'), namespace)
    db = sqlite3.connect((PRIVATE / 'attempts.sqlite3').as_uri()+'?mode=ro', uri=True)
    attempts = {row:json.loads(record) for row,record in db.execute('SELECT source_row,record FROM attempts')}
    totals = db.execute('SELECT COUNT(*),SUM(charge) FROM attempts').fetchone()
    db.close()
    requests = {}
    with (PRIVATE / 'prepared-inputs.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            item = json.loads(line)
            if item['source_row'] in attempts:
                requests[item['source_row']] = item['request']
            if item['source_row'] >= max(attempts):
                break
    replay, raw_basis, inserted, rejected_syntax = Counter(), Counter(), [], []
    for row, record in attempts.items():
        if record.get('wire_response_file'):
            wire = (ROOT / record['wire_response_file']).read_bytes()
            assert sha(wire) == record['wire_response_sha256']
            raw = json.loads(wire)['data']['outputs']['result']
            raw_basis['exact_captured_model_text'] += 1
        elif record.get('response_file'):
            saved = (ROOT / record['response_file']).read_bytes()
            assert sha(saved) == record['response_sha256']
            raw = json.dumps(json.loads(saved), ensure_ascii=False)
            raw_basis['reserialized_saved_parsed_response_original_whitespace_unavailable'] += 1
        else:
            continue
        try:
            out = namespace['main'](raw)
        except ValueError:
            assert row == 70
            rejected_syntax.append(row)
            continue
        assert out == normalize(raw) and out['raw_result'] == raw
        after = json.loads(out['result'])
        AgentService(lambda op, req: after).extract(requests[row])
        paths = json.loads(out['normalization_report'])['inserted_false_paths']
        if paths:
            before = json.loads(raw)
            for index, question in enumerate(after['questions']):
                if 'required' not in before['questions'][index]:
                    question.pop('required')
            assert after == before
            assert record['status'] == 'boundary_or_transport_rejected'
            replay['counterfactual_valid_after_optional_policy'] += 1
            inserted.append(dict(source_row=row, inserted_false_count=len(paths), original_status_unchanged=True))
        else:
            assert out['result'] == raw
            replay['already_valid_preserved'] += 1
    recovered = json.loads((PRIVATE / 'failure-000044.dify-detail.json').read_bytes())
    recovered_outputs = recovered['outputs']
    if isinstance(recovered_outputs, str):
        recovered_outputs = json.loads(recovered_outputs)
    try:
        namespace['main'](recovered_outputs['result'])
    except ValueError:
        rejected_syntax.append(44)
    else:
        raise AssertionError('Original malformed row 44 must stay rejected')
    assert dict(replay) == {'already_valid_preserved':80,'counterfactual_valid_after_optional_policy':2}
    assert sorted(rejected_syntax) == [44,70]
    report = dict(recorded_at=datetime.now(timezone.utc).isoformat(),
        supplied_export_sha256=VERIFIED_SHA, supplied_export_matches_v4_candidate_exactly=True,
        actual_SYSTEM_contains_required_rule_and_example=True,
        current_offline_canonical_export_synchronized=True, previous_export_sha256=BEFORE_SHA,
        candidate_dsl=candidate_path.relative_to(ROOT).as_posix(), candidate_dsl_sha256=sha(encoded),
        candidate_code_sha256=sha(code_source.encode()), model_and_prompt_unchanged=True,
        candidate_status='prepared_offline_not_imported_or_published',
        automatic_model_or_code_retries_enabled=False, new_generation_calls=0,
        offline_replay_counts=dict(replay), offline_replay_input_basis=dict(raw_basis), counterfactual_insertions=inserted,
        malformed_historical_responses_still_rejected=sorted(rejected_syntax),
        historical_attempts_unchanged=totals[0], historical_cost_upper_bound_cny=totals[1]/1e6,
        actual_bill_read=False, provider_model_bug_proven_fixed=False,
        full_csv_resume_requires_new_publication_and_separate_failure_triage=True,
        references=['https://docs.dify.ai/en/cloud/use-dify/nodes/code',
                    'https://api-docs.deepseek.com/api/create-chat-completion/'],
        limitations='Offline normalization is not a new model run or correction of historical failures. Program fills only question.required=false under current optional-question policy. A still validates full final response; medical accuracy is not established.')
    with (HERE / 'question-guard-candidate.json').open('xb') as stream:
        stream.write((json.dumps(report,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
