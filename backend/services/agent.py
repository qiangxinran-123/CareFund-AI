"""Agent adapter boundary with a safe deterministic mock."""

from __future__ import annotations

from uuid import uuid4

from ..models import AgentQuestion, Application, DraftSection, Evidence, Fact, TextValue


class MockAgentService:
    def extract(
        self, application: Application, evidence: list[Evidence], answers: dict[str, str]
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

    def draft_sections(self, facts: list[Fact]) -> list[DraftSection]:
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


agent_service = MockAgentService()

