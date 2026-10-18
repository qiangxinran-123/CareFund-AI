"""Explicit mock: validates plumbing, does not perform AI extraction."""
import json
from agent.agent_service import AgentService

def mock_runner(operation, request):
    return {k: request[k] for k in ('schema_version', 'application_id', 'application_revision')} | {
        'candidate_facts': [],
        'questions': [{'question_id': 'question_demo', 'field': 'patient.medical_summary',
                       'question': '请补充需要整理的病情自述。', 'reason': '这是模拟追问，用于检查接口。', 'required': True}],
        'warnings': ['MOCK：没有调用模型，不具备真实抽取能力。']}

if __name__ == '__main__':
    request = {'schema_version': '1.0', 'application_id': 'app_demo', 'application_revision': 1,
               'user_input': {}, 'extracted_documents': [], 'candidate_facts': []}
    print(json.dumps(AgentService(mock_runner).extract(request), ensure_ascii=False, indent=2))
