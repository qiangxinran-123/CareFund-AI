import copy
import unittest
from agent.agent_service import AgentService, AgentError
from agent.draft_policy import DRAFT_WARNING, sections_for_facts

class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.req = dict(schema_version='1.0', application_id='app_test', application_revision=1,
                        user_input={}, extracted_documents=[], candidate_facts=[])
        self.out = {k:self.req[k] for k in ('schema_version','application_id','application_revision')}
        self.out.update(candidate_facts=[], questions=[], warnings=[])
    def service(self, out):
        return AgentService(lambda op, req: copy.deepcopy(out))
    def fact(self, **kw):
        return dict(fact_id='fact_test', field='patient.medical_summary', value={'kind':'text','value':'测试自述'},
                    source_type='user_input', evidence_ids=[], verification_status='pending',user_confirmed=False) | kw
    def test_empty_valid(self):
        self.assertEqual(self.service(self.out).extract(self.req), self.out)
    def test_revision_mismatch(self):
        self.out['application_revision']=2
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def test_unknown_evidence(self):
        self.out['candidate_facts']=[self.fact(source_type='document', evidence_ids=['ev_fake'])]
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def test_self_confirmation(self):
        self.out['candidate_facts']=[self.fact(user_confirmed=True)]
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def test_self_verification(self):
        self.out['candidate_facts']=[self.fact(verification_status='supported')]
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def test_mutated_existing_fact(self):
        self.req['candidate_facts']=[self.fact()]
        self.out['candidate_facts']=[self.fact(value={'kind':'text','value':'另一种疾病'})]
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def test_duplicate_facts(self):
        self.out['candidate_facts']=[self.fact(),self.fact()]
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def test_extra_field(self):
        self.out['status']='exported'
        with self.assertRaises(AgentError): self.service(self.out).extract(self.req)
    def draft_request(self):
        return {k:self.req[k] for k in ('schema_version','application_id','application_revision')} | dict(candidate_facts=[self.fact(user_confirmed=True)],validation_issue_ids=[])
    def draft_output(self):
        return {k:self.req[k] for k in ('schema_version','application_id','application_revision')} | dict(candidate_sections=sections_for_facts(self.draft_request()['candidate_facts']),warnings=[DRAFT_WARNING])
    def test_draft(self):
        out=self.draft_output()
        self.assertEqual(self.service(out).draft(self.draft_request()),out)
    def test_unconfirmed_draft(self):
        req=self.draft_request(); req['candidate_facts'][0]['user_confirmed']=False
        with self.assertRaises(AgentError): self.service(self.draft_output()).draft(req)
    def test_issue_blocks_draft(self):
        req=self.draft_request(); req['validation_issue_ids']=['issue_test']
        with self.assertRaises(AgentError): self.service(self.draft_output()).draft(req)
    def test_invalid_draft_reference(self):
        out=self.draft_output();out['candidate_sections'][0]['fact_ids']=['fact_fake']
        with self.assertRaises(AgentError): self.service(out).draft(self.draft_request())
    def test_runner_failure(self):
        def fail(op, req): raise TimeoutError()
        with self.assertRaises(AgentError): AgentService(fail).extract(self.req)
