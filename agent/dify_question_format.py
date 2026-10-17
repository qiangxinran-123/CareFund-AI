"""Dify Code-node source; standard library only, no network or model calls.

CareFund's current explicit policy: absent team mandatory-field rules, questions
are optional. Only an omitted question.required may receive False. This is a
workflow policy value, not a medical inference or a substitute for AgentService.
Keep raw_result and normalization_report when evaluating the workflow.
"""
import json
import re


VERSION = 'optional-question-required-v1'
TOP_KEYS = {'schema_version', 'application_id', 'application_revision',
            'candidate_facts', 'questions', 'warnings'}
FACT_KEYS = {'fact_id', 'field', 'value', 'source_type', 'evidence_ids',
             'verification_status', 'user_confirmed'}
QUESTION_KEYS = {'question_id', 'field', 'question', 'reason', 'required'}


def _reject():
    # Never include model output, request values or medical text in errors.
    raise ValueError('CareFund response format rejected; no automatic retry')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject()
        result[key] = value
    return result


def _constant(value):
    _reject()


def main(llm_text: str) -> dict:
    if not isinstance(llm_text, str) or len(llm_text) > 262144:
        _reject()
    try:
        response = json.loads(llm_text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, TypeError, RecursionError):
        _reject()
    if not isinstance(response, dict) or set(response) != TOP_KEYS:
        _reject()
    if not isinstance(response['candidate_facts'], list) or not isinstance(response['questions'], list):
        _reject()
    # Missing fact metadata, values or evidence are never supplied by this node.
    if any(not isinstance(fact, dict) or set(fact) != FACT_KEYS for fact in response['candidate_facts']):
        _reject()
    paths = []
    for index, question in enumerate(response['questions']):
        if not isinstance(question, dict) or set(question) not in (QUESTION_KEYS, QUESTION_KEYS - {'required'}):
            _reject()
        if any(not isinstance(question[key], str) or not question[key]
               for key in ('question_id', 'field', 'question', 'reason')):
            _reject()
        if (not re.fullmatch(r'[a-z][a-z0-9_]{2,63}', question['question_id'])
                or not re.fullmatch(r'[a-z][a-z0-9_.]{1,127}', question['field'])
                or len(question['question']) > 500 or len(question['reason']) > 500):
            _reject()
        if 'required' in question:
            if type(question['required']) is not bool:
                _reject()
        else:
            question['required'] = False
            paths.append('/questions/' + str(index) + '/required')
    report = {'version': VERSION, 'policy': 'no_team_mandatory_rules_questions_optional',
              'inserted_false_paths': paths, 'raw_model_output_preserved': True}
    return {'result': json.dumps(response, ensure_ascii=False, allow_nan=False) if paths else llm_text,
            'raw_result': llm_text,
            'normalization_report': json.dumps(report, ensure_ascii=False)}
