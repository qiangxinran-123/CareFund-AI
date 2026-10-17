"""OCR adapter boundary.

The default implementation is deliberately a deterministic mock. Replace only
this class when a real OCR provider is selected; routes should remain unchanged.
"""

from __future__ import annotations

from uuid import uuid4

from ..models import Evidence, UploadedDocument


class MockOcrService:
    def extract(self, document: UploadedDocument, _content: bytes) -> list[Evidence]:
        return [
            Evidence(
                evidence_id=f"ev_{uuid4().hex}",
                document_id=document.document_id,
                page=1,
                text_excerpt=f"Mock OCR 已接收文件 {document.filename}；尚未接入真实 OCR。",
                extraction_method="ocr",
            )
        ]


ocr_service = MockOcrService()

