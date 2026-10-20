"""INT-08: checked severity mapping with the frozen AgentDraftRequest schema.

Only a trusted, current deterministic ValidationResult can explain issue IDs.
The complete result stays with B; only blocking IDs belong in the Dify request.
"""
import copy
import hashlib
import json

from .errors import AgentError


def prepare_draft_gate(request, validation_result, validate_result):
    """Return (model_request, audit_report), leaving both input objects untouched.

Legacy ID-only callers remain fail-closed. With a paired complete D result,
accept either its full ID set or D's explicit blocking-only projection.
Never infer severity from an ID, an LLM response, or can_finalize alone.
"""
    prepared = copy.deepcopy(request)
    if validation_result is None:
        if request['validation_issue_ids']:
            raise AgentError('Resolve validation issues before drafting; a complete current ValidationResult is required to classify issue IDs')
        return prepared, None
    validate_result(validation_result)
    for key in ('schema_version', 'application_id', 'application_revision'):
        if validation_result[key] != request[key]:
            raise AgentError('Draft validation identity/revision mismatch')
    issues = validation_result['issues']
    all_ids = {item['issue_id'] for item in issues}
    if len(all_ids) != len(issues):
        raise AgentError('Duplicate validation issue_id')
    fact_ids = {fact['fact_id'] for fact in request['candidate_facts']}
    if any(not set(item['related_fact_ids']) <= fact_ids for item in issues):
        raise AgentError('Validation issue references unknown draft facts')
    blocking_ids = {item['issue_id'] for item in issues if item['severity'] == 'blocking'}
    supplied = set(request['validation_issue_ids'])
    if supplied != all_ids and supplied != blocking_ids:
        raise AgentError('Draft issue IDs must match the complete validation result or its blocking-only projection')
    if blocking_ids or not validation_result['can_finalize']:
        raise AgentError('Validation blocks drafting')
    # This explicit D mapping does not remove any issue from the paired result.
    prepared['validation_issue_ids'] = [item['issue_id'] for item in issues if item['severity'] == 'blocking']
    digest = hashlib.sha256(json.dumps(validation_result, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    report = dict(policy='checked-severity-v1', validation_result_sha256=digest,
        complete_issues_count=len(issues), blocking_issues_count=len(blocking_ids),
        input_issue_scope='all' if supplied == all_ids else 'blocking',
        model_issue_scope='blocking', complete_validation_preserved=True)
    return prepared, report
