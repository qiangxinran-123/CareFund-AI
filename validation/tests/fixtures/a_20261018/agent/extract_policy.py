"""Local development scope from the tested extraction prompt, not business requirements.

Only newly generated facts and questions use this scope. Existing facts keep
their original fields and must still be returned completely unchanged.
"""

EXTRACT_FACT_FIELDS = frozenset({
    'patient.relationship_to_applicant',
    'patient.medical_summary',
    'treatment.paid_cost',
    'treatment.estimated_cost',
    'treatment.recorded_date',
    'contact.city',
})
EXTRACT_QUESTION_FIELDS = EXTRACT_FACT_FIELDS | {'documents.diagnosis_proof'}
