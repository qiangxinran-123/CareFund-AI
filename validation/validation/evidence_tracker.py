"""Trace Fact -> Evidence -> UploadedDocument without mutating source objects."""

from .issues import issue


class EvidenceTracker:
    def __init__(self, request: dict):
        self.request = request
        self.documents: dict[str, dict] = {}
        self.evidence: dict[str, dict] = {}
        self.facts: dict[str, dict] = {}
        self.issues: list[dict] = []
        for collection, key, target in (
            ("documents", "document_id", self.documents),
            ("evidence", "evidence_id", self.evidence),
            ("facts", "fact_id", self.facts),
        ):
            for item in request[collection]:
                if item[key] in target:
                    related = [item[key]] if collection == "facts" else []
                    self.issues.append(issue("invalid_format", collection, "存在重复标识，无法唯一追溯来源。", related))
                else:
                    target[item[key]] = item

    def check(self) -> list[dict]:
        issues = list(self.issues)
        for document in self.documents.values():
            if document["application_id"] != self.request["application_id"]:
                issues.append(issue("unsupported", "documents", "附件不属于当前申请。"))
            if document["processing_status"] != "processed":
                issues.append(issue("missing", "documents", "附件解析尚未完成或已失败，需处理后重新校验。"))
        for evidence in self.evidence.values():
            if evidence["document_id"] not in self.documents:
                issues.append(issue("unsupported", "evidence", "证据引用的附件不存在。"))
        for fact in self.facts.values():
            if any(ref not in self.evidence for ref in fact["evidence_ids"]):
                issues.append(issue("unsupported", fact["field"], "事实引用了不存在的证据。", [fact["fact_id"]]))
        return issues

    def sources_for(self, fact: dict) -> list[dict]:
        return [self.evidence[ref] for ref in fact["evidence_ids"] if ref in self.evidence]

    def trace(self, fact_id: str) -> list[dict]:
        """Internal diagnostic view; retains unknown pages as null."""
        fact = self.facts[fact_id]
        return [
            {"evidence": evidence, "document": self.documents.get(evidence["document_id"])}
            for evidence in self.sources_for(fact)
        ]
