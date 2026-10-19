"""Local OCR service for images and PDFs.

PDFs with a usable text layer are read directly. Scanned PDF pages and image
uploads are recognized locally with RapidOCR (PaddleOCR-compatible ONNX models),
so patient material is not sent to a third-party API.
"""

from __future__ import annotations

from threading import Lock
from uuid import uuid4

from ..models import Evidence, UploadedDocument


MAX_PDF_PAGES = 20
MAX_EVIDENCE_TEXT_LENGTH = 2000
MIN_NATIVE_TEXT_LENGTH = 8
MIN_OCR_SCORE = 0.50


class OcrProcessingError(RuntimeError):
    """Raised when an uploaded document cannot produce usable text."""


class LocalOcrService:
    def __init__(self) -> None:
        self._engine = None
        self._engine_lock = Lock()

    def extract(self, document: UploadedDocument, content: bytes) -> list[Evidence]:
        try:
            if document.media_type == "application/pdf":
                pages = self._extract_pdf(content)
            else:
                pages = [(1, self._run_rapidocr(content), "ocr")]
        except OcrProcessingError:
            raise
        except Exception as exc:
            raise OcrProcessingError(f"无法识别文件：{exc}") from exc

        evidence: list[Evidence] = []
        for page_number, text, method in pages:
            for excerpt in self._split_text(text):
                evidence.append(
                    Evidence(
                        evidence_id=f"ev_{uuid4().hex}",
                        document_id=document.document_id,
                        page=page_number,
                        text_excerpt=excerpt,
                        extraction_method=method,
                    )
                )
        if not evidence:
            raise OcrProcessingError("文件中没有识别到可用文字")
        return evidence

    def _extract_pdf(self, content: bytes) -> list[tuple[int, str, str]]:
        try:
            import pymupdf
        except ImportError as exc:
            raise OcrProcessingError("缺少 PyMuPDF，无法处理 PDF") from exc

        try:
            pdf = pymupdf.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise OcrProcessingError("PDF 文件已损坏或格式无效") from exc

        with pdf:
            if pdf.page_count == 0:
                raise OcrProcessingError("PDF 不包含页面")
            if pdf.page_count > MAX_PDF_PAGES:
                raise OcrProcessingError(f"PDF 超过 {MAX_PDF_PAGES} 页处理上限")

            pages: list[tuple[int, str, str]] = []
            for index, page in enumerate(pdf, start=1):
                native_text = self._normalize_text(page.get_text("text"))
                if len(native_text) >= MIN_NATIVE_TEXT_LENGTH:
                    pages.append((index, native_text, "structured_import"))
                    continue

                pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                recognized = self._run_rapidocr(pixmap.tobytes("png"))
                if recognized:
                    pages.append((index, recognized, "ocr"))
            return pages

    def _get_engine(self):
        if self._engine is None:
            with self._engine_lock:
                if self._engine is None:
                    try:
                        from rapidocr import RapidOCR
                    except ImportError as exc:
                        raise OcrProcessingError(
                            "缺少 RapidOCR/ONNX Runtime，无法识别扫描件"
                        ) from exc
                    self._engine = RapidOCR()
        return self._engine

    def _run_rapidocr(self, image: bytes) -> str:
        try:
            result = self._get_engine()(image)
        except Exception as exc:
            raise OcrProcessingError(f"图片 OCR 失败：{exc}") from exc

        texts = list(result.txts or [])
        scores = list(result.scores or [])
        accepted = [
            str(text).strip()
            for text, score in zip(texts, scores, strict=False)
            if text and float(score) >= MIN_OCR_SCORE
        ]
        return self._normalize_text("\n".join(accepted))

    @staticmethod
    def _normalize_text(text: str) -> str:
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())

    @staticmethod
    def _split_text(text: str) -> list[str]:
        normalized = LocalOcrService._normalize_text(text)
        return [
            normalized[start : start + MAX_EVIDENCE_TEXT_LENGTH]
            for start in range(0, len(normalized), MAX_EVIDENCE_TEXT_LENGTH)
        ]


ocr_service = LocalOcrService()

