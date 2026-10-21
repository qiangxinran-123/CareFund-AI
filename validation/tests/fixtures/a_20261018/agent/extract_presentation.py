"""Source-neutral presentation policy after the model fact boundary.

Candidate facts are never rewritten. Model-authored questions/warnings are kept
in AgentService's in-memory raw response; public prose uses reviewed templates.
This does not establish medical truth or replace fact/evidence validation.
"""
import copy
import hashlib
import json
import re

VERSION = 'source-neutral-presentation-v1'
FIELDS = ('patient.medical_summary', 'patient.relationship_to_applicant',
          'treatment.paid_cost', 'treatment.estimated_cost')
UNKNOWN = r'未知|不知道|不清楚|不记得|暂无|暂时没有|没有精确|不愿|无法确定'
TEMPLATES = {
    'medical_ambiguity': ('patient.medical_summary',
        '请核对病情原文的写法和不确定表述；仍在检查或暂不清楚时，可以保留原文，不需要猜测诊断。',
        '核对原文可以避免误解；本问题不要求补出确定诊断。'),
    'currency': ('treatment.paid_cost',
        '这笔已支付费用的币种尚需核对。请按原始凭证说明实际币种；暂不清楚可以保留原文。',
        '币种未明确时不能自行认定或换算。'),
    'estimated_currency': ('treatment.estimated_cost',
        '这笔预估费用的币种尚需核对。请按原始说明核对币种；暂不清楚可以保留原文。',
        '币种未明确时不能自行认定或换算。'),
    'medical': ('patient.medical_summary',
        '是否愿意补充患者的病情原文或检查进展？尚未确诊或暂不清楚时可以如实说明。',
        '可选补充有助于整理病情陈述，不代表平台必填要求。'),
    'relationship': ('patient.relationship_to_applicant',
        '是否愿意说明患者与申请人的关系？不愿补充时可以跳过。',
        '当前未记录该信息，补充属于可选项。'),
    'paid': ('treatment.paid_cost',
        '是否愿意补充已支付的医疗费用及币种？暂不清楚可以保留未知。',
        '当前未记录已支付费用，不能据此补出金额。'),
    'estimate': ('treatment.estimated_cost',
        '是否已有后续治疗费用的说明可以补充？暂不清楚或没有说明时可以保留未知。',
        '当前未记录后续费用，不应据此猜测金额。'),
    'documents': ('documents.diagnosis_proof',
        '如已有诊断或检查材料，是否愿意补充以便核对病情原文？暂时没有时可以跳过。',
        '本次未附可用证据，不代表用户没有材料。'),
}
WARNING_USER = '候选事实包含用户陈述，仍待核对和确认，不代表材料已证实。'
WARNING_DOCUMENT = '候选事实包含提交材料中的陈述；本模块未据此证明材料真实。'
WARNING_NO_EVIDENCE = '本次输入未附可引用的材料证据；这不代表用户没有材料。'
WARNING_CONFLICT = '同一字段存在不同数值或表述，已保留各自来源；本次未裁定应采用哪一项。'
WARNING_AMBIGUITY = '请按原文核对病情写法和不确定表述；本模块不提供替代病名或推测病情关联。'


def _sha(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def _sources(request):
    values = [v for v in request['user_input'].values() if isinstance(v, str)]
    values.extend(e['text_excerpt'] for d in request['extracted_documents'] for e in d['evidence'])
    return '\n'.join(values)


def _unknown(field, source, inputs):
    if field in inputs and inputs[field] is None:
        return True
    if field == 'patient.relationship_to_applicant':
        return bool(re.search(r'(?:关系|亲属).{0,8}(?:' + UNKNOWN + r')', source))
    if field == 'patient.medical_summary':
        return bool(re.search(r'(?:病情|诊断|病因).{0,8}(?:不知道|不清楚|未知|不愿)', source))
    role = r'已付|已支付|已花|已经支付' if field == 'treatment.paid_cost' else r'后续|预估|预计'
    if re.search(r'(?:' + role + r').{0,16}(?:' + UNKNOWN + r')', source):
        return True
    # Do not broaden a role-specific unknown cost to the other cost role.
    for segment in re.split(r'[，,。；;\n]', source):
        if re.search(r'费用.{0,3}(?:未知|不知道|不清楚)', segment) and not re.search(r'已付|已支付|已花|后续|预估|预计', segment):
            return True
    return field == 'treatment.estimated_cost' and bool(re.search(
        r'(?:没有|暂无|暂时没有).{0,8}(?:费用预估单|费用说明|预估材料)', source))


def present(request, response):
    """Return contract-shaped prose and a PHI-free provenance report; no I/O."""
    result = copy.deepcopy(response)
    facts = response['candidate_facts']
    source = _sources(request)
    fields = {f['field'] for f in facts}
    context = bool(source.strip() or facts or request['extracted_documents'])
    values = {}
    for fact in facts:
        values.setdefault(fact['field'], set()).add(_sha(fact['value']))
    conflicts = sorted(f for f, choices in values.items() if len(choices) > 1)
    warning_hint = '\n'.join(response['warnings'])
    ambiguity = 'patient.medical_summary' in fields and bool(
        re.search(r'可能|待查|待排|疑似|[?？]|笔误|错别字|写法', source)
        or re.search(r'笔误|不明确|不完整|含糊|可能相关|带问号', warning_hint))
    warnings = []
    if any(f['source_type'] in ('user_input', 'user_correction') for f in facts):
        warnings.append(WARNING_USER)
    if any(f['source_type'] == 'document' for f in facts):
        warnings.append(WARNING_DOCUMENT)
    has_evidence = any(d['evidence'] for d in request['extracted_documents'])
    if context and not has_evidence:
        warnings.append(WARNING_NO_EVIDENCE)
    if conflicts:
        warnings.append(WARNING_CONFLICT)
    if ambiguity:
        warnings.append(WARNING_AMBIGUITY)
    questions, used_fields, rules = [], set(), []

    def add(rule, template):
        field, question, reason = template
        if len(questions) >= 3 or field in used_fields:
            return
        used_fields.add(field)
        identifier = 'question_a_' + _sha([request['application_id'], request['application_revision'], field, rule])[:16]
        questions.append(dict(question_id=identifier, field=field, question=question, reason=reason, required=False))
        rules.append(rule)

    declined = bool(re.search(r'不愿继续|不愿补充|不要追问|不再补充|拒绝补充|不想补充|stop asking|do not ask', source, re.I))
    if context and not declined:
        allowed = set(FIELDS) | {'treatment.recorded_date', 'contact.city', 'documents.diagnosis_proof'}
        for field in conflicts:
            if field in allowed:
                add('different_values', (field,
                    '同一字段存在不同数值或表述。请核对各项的范围、时间和来源，说明本次应采用哪些记录；暂无法确定可以保留待核对。',
                    '不同内容可能对应不同记录或更正，不能由本模块裁定，也不预设哪一方记错。'))
        if ambiguity:
            add('medical_ambiguity', TEMPLATES['medical_ambiguity'])
        for fact in facts:
            if fact['field'] in ('treatment.paid_cost', 'treatment.estimated_cost') and fact['value']['kind'] == 'text':
                value = fact['value']['value']
                if '$' in value and not re.search(r'\b(?:USD|AUD|CAD|HKD|NZD|SGD)\b|美元|澳元|加元|港元|新西兰元|新加坡元', value, re.I):
                    rule = 'currency' if fact['field'] == 'treatment.paid_cost' else 'estimated_currency'
                    add(rule, TEMPLATES[rule])
        for field, rule in zip(FIELDS, ('medical', 'relationship', 'paid', 'estimate')):
            if field not in fields and not _unknown(field, source, request['user_input']):
                add(rule, TEMPLATES[rule])
        lacks_documents = bool(re.search(r'(?:没有|暂无|暂时没有)(?:任何)?(?:诊断|检查)?材料', source))
        if 'patient.medical_summary' in fields and not has_evidence and not lacks_documents:
            add('documents', TEMPLATES['documents'])
    result['questions'], result['warnings'] = questions, warnings
    assert result['candidate_facts'] == response['candidate_facts']
    report = dict(version=VERSION, raw_response_sha256=_sha(response), result_sha256=_sha(result),
        candidate_facts_unchanged=True, raw_response_retained_in_service_memory=True,
        model_questions_count=len(response['questions']), model_warnings_count=len(response['warnings']),
        question_rules=rules, prose_source='reviewed_constant_templates', followup_declined=declined)
    return result, report
