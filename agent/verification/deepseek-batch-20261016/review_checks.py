"""Evaluation-only checks for this tested prompt's declared development field scope.

This is not a shared contract or an AgentService runtime policy change.
"""

FACT_FIELDS = frozenset({
    'patient.relationship_to_applicant', 'patient.medical_summary',
    'treatment.paid_cost', 'treatment.estimated_cost',
    'treatment.recorded_date', 'contact.city',
})
QUESTION_FIELDS = FACT_FIELDS | {'documents.diagnosis_proof'}


def prompt_scope_findings(case, response):
    if case['operation'] != 'extract':
        return []
    existing_ids = {fact['fact_id'] for fact in case['request']['candidate_facts']}
    findings = []
    for fact in response['candidate_facts']:
        if fact['fact_id'] not in existing_ids and fact['field'] not in FACT_FIELDS:
            findings.append({'type': 'new_fact_field_outside_tested_prompt_scope',
                             'fact_id': fact['fact_id'], 'field': fact['field']})
    for question in response['questions']:
        if question['field'] not in QUESTION_FIELDS:
            findings.append({'type': 'question_field_outside_tested_prompt_scope',
                             'question_id': question['question_id'], 'field': question['field']})
    return findings
