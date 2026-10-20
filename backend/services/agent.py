"""Adapter between Backend models and A's AgentService interface."""

from __future__ import annotations

import os
from uuid import uuid4

from ..models import (
    AgentQuestion,
    Application,
    DraftSection,
    Evidence,
    Fact,
    TextValue,
    UploadedDocument,
    ValidationIssue,
)


class AgentIntegrationError(RuntimeError):
    """Safe backend-facing error for unavailable or rejected Agent calls."""


class MockAgentService:
    def extract(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        candidate_facts: list[Fact],
        answers: dict[str, str],
    ) -> tuple[list[Fact], list[AgentQuestion]]:
        facts: list[Fact] = []
        if application.patient_info.medical_summary:
            facts.append(
                Fact(
                    fact_id=f"fact_{uuid4().hex}",
                    field="patient.medical_summary",
                    value=TextValue(value=application.patient_info.medical_summary),
                    source_type="user_input",
                    evidence_ids=[],
                    verification_status="pending",
                    user_confirmed=True,
                )
            )

        for item in evidence:
            facts.append(
                Fact(
                    fact_id=f"fact_{uuid4().hex}",
                    field="document.ocr_excerpt",
                    value=TextValue(value=item.text_excerpt),
                    source_type="document",
                    evidence_ids=[item.evidence_id],
                    verification_status="supported",
                    user_confirmed=False,
                )
            )

        questions: list[AgentQuestion] = []
        if not application.patient_info.medical_summary and "patient.medical_summary" not in answers:
            questions.append(
                AgentQuestion(
                    question_id="question_medical_summary",
                    field="patient.medical_summary",
                    question="请补充由申请人提供的病情情况说明。",
                    reason="当前申请缺少用户自述，系统不会自行推断医疗事实。",
                    required=True,
                )
            )
        return facts, questions

    def draft_sections(
        self, application: Application, facts: list[Fact], issues: list[ValidationIssue]
    ) -> list[DraftSection]:
        summary_facts = [fact for fact in facts if fact.field == "patient.medical_summary"]
        content = (
            summary_facts[0].value.value
            if summary_facts
            else "申请人尚未提供可用于生成情况说明的医疗信息。"
        )
        return [
            DraftSection(
                section_id=f"section_{uuid4().hex}",
                title="情况说明",
                content=f"以下内容来自用户提供的信息：{content}",
                fact_ids=[fact.fact_id for fact in summary_facts],
            )
        ]


class RealAgentService:
    """Calls A's checked AgentService and converts its contract dictionaries."""

    @staticmethod
    def _service(application_id: str):
        try:
            from agent.agent_service import AgentError, AgentService
            from agent.dify_runner import DifyRunner

            return AgentService(DifyRunner.from_env(user=application_id)), AgentError
        except (ImportError, ValueError) as exc:
            raise AgentIntegrationError("Agent 模块或 Dify 配置不可用") from exc

    def extract(
        self,
        application: Application,
        documents: list[UploadedDocument],
        evidence: list[Evidence],
        candidate_facts: list[Fact],
        answers: dict[str, str],
    ) -> tuple[list[Fact], list[AgentQuestion]]:
        evidence_by_document: dict[str, list[dict]] = {
            document.document_id: [] for document in documents
        }
        for item in evidence:
            evidence_by_document.setdefault(item.document_id, []).append(
                item.model_dump(mode="json")
            )
        user_input: dict[str, str | int | bool | None] = {
            "display_name": application.patient_info.display_name,
            "age_group": application.patient_info.age_group,
            "description": application.patient_info.medical_summary,
        }
        user_input.update({f"answer.{key}": value for key, value in answers.items()})
        request = {
            "schema_version": "1.0",
            "application_id": application.application_id,
            "application_revision": application.revision,
            "user_input": user_input,
            "extracted_documents": [
                {
                    "document": document.model_dump(mode="json"),
                    "evidence": evidence_by_document.get(document.document_id, []),
                }
                for document in documents
            ],
            "candidate_facts": [fact.model_dump(mode="json") for fact in candidate_facts],
        }
        service, agent_error = self._service(application.application_id)
        try:
            result = service.extract(request)
        except agent_error as exc:
            raise AgentIntegrationError(str(exc)) from exc
        return (
            [Fact.model_validate(item) for item in result["candidate_facts"]],
            [AgentQuestion.model_validate(item) for item in result["questions"]],
        )

    def draft_sections(
        self, application: Application, facts: list[Fact], issues: list[ValidationIssue]
    ) -> list[DraftSection]:
        request = {
            "schema_version": "1.0",
            "application_id": application.application_id,
            "application_revision": application.revision,
            "candidate_facts": [fact.model_dump(mode="json") for fact in facts],
            "validation_issue_ids": [issue.issue_id for issue in issues],
        }
        service, agent_error = self._service(application.application_id)
        try:
            result = service.draft(request)
        except agent_error as exc:
            raise AgentIntegrationError(str(exc)) from exc
        return [
            DraftSection(section_id=f"section_{uuid4().hex}", **item)
            for item in result["candidate_sections"]
        ]


def build_agent_service():
    mode = os.getenv("CAREFUND_AGENT_MODE", "real").lower()
    if mode == "mock":
        return MockAgentService()
    if mode != "real":
        raise RuntimeError("CAREFUND_AGENT_MODE must be 'real' or 'mock'")
    return RealAgentService()


agent_service = build_agent_service()

