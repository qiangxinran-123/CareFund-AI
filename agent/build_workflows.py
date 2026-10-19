"""Build local import candidates without modifying the working extraction export.

The draft .yml uses JSON syntax, which Dify's YAML importer accepts. Actual import
and model-provider availability still need checking in the user's Dify instance.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORDING_RULE = '未提供平台规则时，不得声称“平台建议”“平台要求”或“审核需要”，也不得声称补充材料能“加快审核进度”“提高通过率”或产生其他未经输入支持的审批效果。仅可中性说明“补充材料便于核对已有陈述”，不代表平台发言，不承诺审核速度或结果。'


def build():
    start, llm, end = '1792025822151', '1792026425851', '1792027126071'
    def node(identifier, x, data):
        return {'id': identifier, 'type': 'custom', 'position': {'x': x, 'y': 160},
                'positionAbsolute': {'x': x, 'y': 160}, 'width': 242, 'height': 110,
                'sourcePosition': 'right', 'targetPosition': 'left', 'selected': False,
                'data': dict(data, selected=False)}
    def edge(source, target, source_type, target_type):
        return {'id': source + '--' + target + '-target', 'source': source, 'target': target,
                'sourceHandle': 'source', 'targetHandle': 'target', 'type': 'custom',
                'data': {'sourceType': source_type, 'targetType': target_type,
                         'isInIteration': False, 'isInLoop': False}, 'zIndex': 0}
    plugin = 'langgenius/openai:1.0.7@f36c3761167b3af0bfb4975b728fe3cd126342d076e1ec5359e6d4f92557d3d4'
    workflow = {
        'kind': 'app', 'version': '0.7.0',
        'app': {'name': 'CareFund-已确认事实草稿-首版', 'mode': 'workflow',
                'description': '事实逐条成稿；仅接收已确认事实。仍需 Python、B/D 校验；不是导出许可。',
                'icon': '📝', 'icon_type': 'emoji', 'icon_background': '#E8F2EC',
                'use_icon_as_answer_icon': False},
        'dependencies': [{'type': 'marketplace', 'current_identifier': None,
                          'value': {'marketplace_plugin_unique_identifier': plugin, 'version': None}}],
        'workflow': {'conversation_variables': [], 'environment_variables': [],
                     'rag_pipeline_variables': [],
                     'features': {'file_upload': {'enabled': False}, 'opening_statement': '',
                                  'retriever_resource': {'enabled': False},
                                  'sensitive_word_avoidance': {'enabled': False},
                                  'speech_to_text': {'enabled': False}, 'suggested_questions': [],
                                  'suggested_questions_after_answer': {'enabled': False},
                                  'text_to_speech': {'enabled': False}},
                     'graph': {'nodes': [
                         node(start, 100, {'type': 'start', 'title': '已确认事实输入', 'variables': [
                             {'variable': 'request_json', 'label': '草稿请求 JSON', 'type': 'paragraph',
                              'required': True, 'default': '', 'options': []}]}),
                         node(llm, 400, {'type': 'llm', 'title': '事实逐条成稿',
                             'context': {'enabled': False, 'variable_selector': []},
                             'vision': {'enabled': False},
                             'model': {'provider': 'langgenius/openai/openai', 'name': 'gpt-4.1',
                                       'mode': 'chat', 'completion_params': {'temperature': 0}},
                             'prompt_template': [
                                 {'id': 'draft-system', 'role': 'system',
                                  'text': (ROOT / 'prompts' / 'draft.md').read_text(encoding='utf-8')},
                                 {'id': 'draft-input', 'role': 'user', 'text': '{{#' + start + '.request_json#}}'}]}),
                         node(end, 700, {'type': 'end', 'title': '候选章节输出', 'outputs': [
                             {'variable': 'result', 'value_type': 'string', 'value_selector': [llm, 'text']}]})],
                         'edges': [edge(start, llm, 'start', 'llm'), edge(llm, end, 'llm', 'end')],
                         'viewport': {'x': 0, 'y': 0, 'zoom': 0.8}}},
    }
    (ROOT / 'workflow.draft.yml').write_text(json.dumps(workflow, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    original = (ROOT / 'workflow.yml').read_text(encoding='utf-8')
    anchor = '6. 这类矛盾追问优先于一般信息补充问题。'
    if original.count(anchor) != 1:
        raise ValueError('Extraction workflow prompt anchor must occur exactly once')
    revised = original.replace(anchor, anchor + '\n\n            7. ' + WORDING_RULE)
    revised = revised.replace('name: CareFund-信息抽取与追问-修订版', 'name: CareFund-信息抽取与追问-措辞修订候选')
    (ROOT / 'workflow.extract-v2.yml').write_text(revised, encoding='utf-8')
    extract_prompt = (ROOT / 'prompts' / 'extract.md').read_text(encoding='utf-8').rstrip()
    (ROOT / 'prompts' / 'extract-v2.md').write_text(extract_prompt + '\n\n' + WORDING_RULE + '\n', encoding='utf-8')


if __name__ == '__main__':
    build()
    print('Built local import candidates; this command does not publish to Dify.')
