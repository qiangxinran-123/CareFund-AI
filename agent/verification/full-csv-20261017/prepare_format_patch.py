"""Prepare an unpublished output-format prompt candidate; no network or retries."""
import json
from pathlib import Path
import sys

from prepare import HERE, ROOT, sha

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'agent/.local/yaml-validation-deps'))
import yaml
from agent.agent_service import AgentService


def main():
    source = ROOT / 'agent/workflow.deepseek-extract.yml'
    actual = yaml.safe_load(source.read_bytes())
    nodes = actual['workflow']['graph']['nodes']
    llms = [n for n in nodes if n['data']['type'] == 'llm']
    assert len(llms) == 1
    node = llms[0]
    systems = [p for p in node['data']['prompt_template'] if p['role'] == 'system']
    assert len(systems) == 1
    previous = systems[0]['text']
    request = dict(schema_version='1.0', application_id='app_format_example', application_revision=1,
                   user_input={'description': '这是虚构结构示例。用户自述疑似肺部肿瘤，尚未确诊。'},
                   extracted_documents=[], candidate_facts=[])
    example = dict(schema_version='1.0', application_id='app_format_example', application_revision=1,
                   candidate_facts=[dict(fact_id='fact_001', field='patient.medical_summary',
                     value={'kind': 'text', 'value': '用户自述疑似肺部肿瘤，尚未确诊。'},
                     source_type='user_input', evidence_ids=[], verification_status='pending', user_confirmed=False)],
                   questions=[dict(question_id='question_001', field='patient.relationship_to_applicant',
                     question='请问患者与您是什么关系？', reason='本次输入未说明患者与申请人的关系。', required=False)],
                   warnings=['本次输入未附材料，以上仅为待确认的用户陈述。'])
    AgentService(lambda operation, req: example).extract(request)
    append = ('9. JSON 结构完整性规则（适用于短文本、长病情和多项诊断）：\n'
        '只能输出一个完整的合法 JSON 对象。value 本身是嵌套对象：先完整结束 value，再填写该事实的来源和状态字段，最后结束该事实对象。'
        '不得在 value 结束后直接结束 candidate_facts 数组，也不得把 source_type 等字段移到数组外。\n'
        '每条新事实必须包含 fact_id、field、value、source_type、evidence_ids、verification_status、user_confirmed 七个字段。'
        '用户自述的新事实固定使用 source_type="user_input"、evidence_ids=[]、verification_status="pending"、user_confirmed=false；'
        '材料来源仍按既有规则引用真实证据，已有候选事实仍原样保留。\n'
        '即使病情原文包含多项疾病、编号、问号、引号或换行，也必须保证 JSON 字符串正确转义、所有对象和数组正确闭合，不能省略事实元数据。'
        '输出前检查括号配对、逗号位置、字符串转义、必需字段以及每个字段所属对象。\n'
        '下面是虚构输入对应的完整 JSON 结构示例，仅展示对象嵌套和必需字段。不要复制示例身份、病情或问题作为当前输入的事实；'
        'schema_version、application_id、application_revision 必须取当前输入值，当前输入未提供的信息不能由示例补齐。\n\n'
        + json.dumps(example, ensure_ascii=False, indent=2) + '\n')
    systems[0]['text'] = previous.rstrip() + '\n\n' + append
    full = systems[0]['text']
    append_path = ROOT / 'agent/prompts/extract-json-v4-append.md'
    full_path = ROOT / 'agent/prompts/extract-json-v4-candidate.md'
    candidate_path = ROOT / 'agent/workflow.deepseek-extract.json-v4-candidate.yml'
    for p in (append_path, full_path, candidate_path):
        if p.exists():
            raise SystemExit('Candidate already exists; will not overwrite.')
    append_path.write_bytes(append.encode())
    full_path.write_bytes(full.encode())
    candidate = yaml.safe_dump(actual, allow_unicode=True, sort_keys=False).encode()
    candidate_path.write_bytes(candidate)
    compare = yaml.safe_load(candidate)
    for n in compare['workflow']['graph']['nodes']:
        if n['data']['type'] == 'llm':
            for p in n['data']['prompt_template']:
                if p['role'] == 'system':
                    p['text'] = previous
    assert compare == yaml.safe_load(source.read_bytes())
    report = dict(status='prepared_unpublished_untested_candidate', original_dsl_sha256=sha(source.read_bytes()),
                  candidate_dsl=candidate_path.relative_to(ROOT).as_posix(), candidate_dsl_sha256=sha(candidate),
                  append_prompt=append_path.relative_to(ROOT).as_posix(),
                  complete_candidate_prompt=full_path.relative_to(ROOT).as_posix(),
                  example_validated_against_current_agent_contract=True,
                  only_SYSTEM_prompt_semantics_changed=True, published=False, live_regression_calls=0,
                  model_issue_fixed=False,
                  reference='https://api-docs.deepseek.com/guides/json_mode/',
                  limits='Prompt example may reduce format errors but cannot guarantee valid output; fresh live testing after publication is required.')
    (HERE / 'format-candidate.json').write_bytes((json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
