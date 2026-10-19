"""Conservative, literal draft format; input truth remains B/D's responsibility."""

FIELD_LABELS = {
    'patient.relationship_to_applicant': '患者与申请人的关系',
    'patient.medical_summary': '病情及检查情况',
    'treatment.paid_cost': '已支付医疗费',
    'treatment.estimated_cost': '后续预估治疗费',
    'treatment.recorded_date': '治疗记录日期',
    'contact.city': '当前所在城市',
}
SOURCE_PREFIXES = {
    'user_input': '用户自述，',
    'user_correction': '用户更正陈述，',
    'document': '提交材料记载（真伪未经本模块核验），',
}
DRAFT_WARNING = '候选草稿仅整理已确认事实，仍需独立校验和人工复核；用户确认不等于材料真实或平台审核通过。'


def render_value(value):
    kind, data = value['kind'], value['value']
    if kind == 'money':
        currency, minor = data['currency'], data['amount_minor']
        if currency == 'CNY':
            return f'人民币{minor // 100}.{minor % 100:02d}元'
        return f'{currency} {minor}（最小货币单位）'
    if kind == 'boolean':
        return 'true' if data else 'false'
    if kind == 'text':
        return '“' + data + '”'
    return str(data)


def sections_for_facts(facts):
    sections = []
    for fact in facts:
        label = FIELD_LABELS.get(fact['field'], fact['field'])
        sections.append({
            'title': FIELD_LABELS.get(fact['field'], '补充事实'),
            'content': SOURCE_PREFIXES[fact['source_type']] + label + '：' + render_value(fact['value']),
            'fact_ids': [fact['fact_id']],
        })
    return sections
