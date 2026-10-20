"""Small in-memory repository for the runnable V1 prototype.

The repository boundary is intentional: replacing it with a database later does
not require changing route or adapter interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import AnalysisJob, AnalysisResult, Application, Draft, Evidence, Fact, UploadedDocument


@dataclass
class ApplicationRecord:
    application: Application
    documents: list[UploadedDocument] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    facts: list[Fact] = field(default_factory=list)
    jobs: dict[str, AnalysisJob] = field(default_factory=dict)
    idempotency_jobs: dict[tuple[int, str], str] = field(default_factory=dict)
    analysis: AnalysisResult | None = None
    draft: Draft | None = None
    answers: dict[str, str] = field(default_factory=dict)


class InMemoryStore:
    def __init__(self) -> None:
        self.applications: dict[str, ApplicationRecord] = {}

    def clear(self) -> None:
        self.applications.clear()


store = InMemoryStore()

