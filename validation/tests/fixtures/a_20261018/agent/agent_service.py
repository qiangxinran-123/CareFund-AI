"""Schema and local policy boundary. Runner required; no implicit mock fallback."""
import copy
import json
from pathlib import Path
from .draft_policy import DRAFT_WARNING, sections_for_facts
from .extract_policy import EXTRACT_FACT_FIELDS, EXTRACT_QUESTION_FIELDS
from .extract_presentation import present
from .draft_input_policy import contains_generation_instruction
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

class AgentError(ValueError):
    pass

class AgentService:
    def __init__(self, runner, schema_dir=None):
        self.runner = runner
        self.last_extract_raw_response = None
        self.last_extract_presentation_report = None
        directory = Path(schema_dir) if schema_dir else Path(__file__).resolve().parents[1] / 'contracts' / 'schemas'
        schemas = [json.loads(p.read_text(encoding='utf-8')) for p in directory.glob('*.json')]
        self.registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas)
        self.schema = next(s for s in schemas if s['title'] == 'CareFund Agent Contract V1')

    def validate(self, value, name):
        schema = dict(self.schema, **{'$ref': '#/$defs/' + name})
        errors = list(Draft202012Validator(schema, registry=self.registry, format_checker=FormatChecker()).iter_errors(value))
        if errors:
            error = errors[0]
            # Use contract paths, never instance values or jsonschema's raw message.
            path = '/'.join(str(part) for part in error.absolute_schema_path)
            detail = str(error.validator) + ' at schema ' + path
            if error.validator == 'required' and isinstance(error.instance, dict):
                missing = sorted(set(error.validator_value) - error.instance.keys())
                detail += '; missing ' + ', '.join(missing)
            raise AgentError('Schema validation failed: ' + name + ' (' + detail + ')')

    @staticmethod
    def unique(items, key):
        ids = [x[key] for x in items]
        if len(ids) != len(set(ids)):
            raise AgentError('Duplicate ' + key)
        return set(ids)

    def run(self, operation, request, request_type, response_type):
        self.validate(request, request_type)
        try:
            result = self.runner(operation, copy.deepcopy(request))
        except AgentError:
            raise
        except Exception as exc:
            raise AgentError('Agent runner failed') from exc
        self.validate(result, response_type)
        for key in ('schema_version', 'application_id', 'application_revision'):
            if result[key] != request[key]:
                raise AgentError('Response identity/revision mismatch')
        return copy.deepcopy(result)

    def extract(self, request):
        self.last_extract_raw_response = None
        self.last_extract_presentation_report = None
        self.validate(request, 'AgentExtractRequest')
        self.unique(request['candidate_facts'], 'fact_id')
        docs = request['extracted_documents']
        self.unique([x['document'] for x in docs], 'document_id')
        evidence = []
        for entry in docs:
            doc = entry['document']
            if doc['application_id'] != request['application_id']:
                raise AgentError('Document belongs to another application')
            for ev in entry['evidence']:
                if ev['document_id'] != doc['document_id']:
                    raise AgentError('Evidence document mismatch')
                evidence.append(ev)
        allowed = self.unique(evidence, 'evidence_id')
        for fact in request['candidate_facts']:
            if not set(fact['evidence_ids']) <= allowed:
                raise AgentError('Input fact references missing evidence')
        result = self.run('extract', request, 'AgentExtractRequest', 'AgentExtractResponse')
        self.unique(result['candidate_facts'], 'fact_id')
        self.unique(result['questions'], 'question_id')
        previous = {f['fact_id']: f for f in request['candidate_facts']}
        returned_ids = {f['fact_id'] for f in result['candidate_facts']}
        if not previous.keys() <= returned_ids:
            raise AgentError('Existing facts omitted from response')
        for fact in result['candidate_facts']:
            if not set(fact['evidence_ids']) <= allowed:
                raise AgentError('Unknown evidence reference')
            if fact['fact_id'] in previous:
                if fact != previous[fact['fact_id']]:
                    raise AgentError('Existing fact changed; create a new candidate instead')
            elif fact['field'] not in EXTRACT_FACT_FIELDS:
                raise AgentError('New candidate field is outside the extraction scope')
            elif fact['user_confirmed'] or fact['verification_status'] != 'pending':
                raise AgentError('New candidate cannot confirm or verify itself')
        for question in result['questions']:
            if question['field'] not in EXTRACT_QUESTION_FIELDS:
                raise AgentError('Question field is outside the extraction scope')
        # Validate the entire raw model response before rendering reviewed prose.
        # Preserve facts and raw output; never use presentation to bypass a rejection.
        rendered, report = present(request, result)
        self.validate(rendered, 'AgentExtractResponse')
        self.unique(rendered['questions'], 'question_id')
        self.last_extract_raw_response = copy.deepcopy(result)
        self.last_extract_presentation_report = report
        return rendered

    def validate_draft_request(self, request):
        """Validate local draft prerequisites before credentials or network access."""
        self.validate(request, 'AgentDraftRequest')
        self.unique(request['candidate_facts'], 'fact_id')
        # Conservative local policy pending team confirmation of issue severity handling.
        if request['validation_issue_ids']:
            raise AgentError('Resolve validation issues before drafting')
        eligible = {f['fact_id'] for f in request['candidate_facts'] if f['user_confirmed'] and f['verification_status'] not in ('conflicting', 'unsupported')}
        if not eligible or len(eligible) != len(request['candidate_facts']):
            raise AgentError('Provide only confirmed, non-conflicting facts')
        if contains_generation_instruction(request['candidate_facts']):
            raise AgentError('Draft fact contains generation instructions; review the source fact before drafting')
        values_by_field = {}
        for fact in request['candidate_facts']:
            value = fact['value']
            previous = values_by_field.setdefault(fact['field'], value)
            if previous != value:
                raise AgentError('Resolve multiple values for the same field before drafting')
        preview = {key: request[key] for key in ('schema_version', 'application_id', 'application_revision')}
        preview.update(candidate_sections=sections_for_facts(request['candidate_facts']), warnings=[DRAFT_WARNING])
        self.validate(preview, 'AgentDraftResponse')
        return eligible

    def draft(self, request):
        eligible = self.validate_draft_request(request)
        result = self.run('draft', request, 'AgentDraftRequest', 'AgentDraftResponse')
        if not result['candidate_sections']:
            raise AgentError('Empty candidate draft')
        for section in result['candidate_sections']:
            if not section['fact_ids'] or not set(section['fact_ids']) <= eligible:
                raise AgentError('Invalid draft fact references')
        if result['candidate_sections'] != sections_for_facts(request['candidate_facts']):
            raise AgentError('Draft content must preserve each input fact in the literal draft format')
        if result['warnings'] != [DRAFT_WARNING]:
            raise AgentError('Draft warnings must use the local policy notice')
        return result
