import { ApiError } from './client'
import { appendMockDocument, getMockDocuments } from './applicationMock'
import type { DocumentApi, UploadDocumentInput } from './documents'
import type { DocumentMediaType, ErrorCode, UploadedDocument } from '../types/contracts'

interface IdempotentUpload {
  fingerprint: string
  document: UploadedDocument
}

const allowedTypes = new Set<DocumentMediaType>(['image/jpeg', 'image/png', 'application/pdf'])
const uploadsByKey = new Map<string, IdempotentUpload>()
let sequence = 0

function mockError(status: number, code: ErrorCode, message: string): ApiError {
  return new ApiError(message, 'http', status, {
    error: { code, message, details: [] },
    request_id: 'req_mock_upload',
  })
}

function fingerprint(input: UploadDocumentInput): string {
  return `${input.applicationId}:${input.file.name}:${input.file.type}:${input.file.size}`
}

export const mockDocumentApi: DocumentApi = {
  async upload(input) {
    if (input.signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')
    const existing = uploadsByKey.get(input.idempotencyKey)
    const currentFingerprint = fingerprint(input)
    if (existing) {
      if (existing.fingerprint !== currentFingerprint) {
        throw mockError(409, 'STATE_CONFLICT', '同一幂等键不能用于不同文件。')
      }
      return structuredClone(existing.document)
    }
    if (!allowedTypes.has(input.file.type as DocumentMediaType)) {
      throw mockError(415, 'UNSUPPORTED_FILE', '仅支持 JPEG、PNG 或 PDF 文件。')
    }
    if (input.file.size < 1) {
      throw mockError(422, 'VALIDATION_FAILED', '不能上传空文件。')
    }

    sequence += 1
    const document: UploadedDocument = {
      document_id: `doc_mock_${String(sequence).padStart(3, '0')}`,
      application_id: input.applicationId,
      filename: input.file.name,
      media_type: input.file.type as DocumentMediaType,
      size_bytes: input.file.size,
      uploaded_at: new Date().toISOString(),
      processing_status: 'uploaded',
    }
    appendMockDocument(input.applicationId, input.expectedRevision, document)
    uploadsByKey.set(input.idempotencyKey, { fingerprint: currentFingerprint, document })
    return structuredClone(document)
  },

  async list(applicationId, signal) {
    if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')
    return getMockDocuments(applicationId)
  },
}

export function resetMockDocuments(): void {
  uploadsByKey.clear()
  sequence = 0
}
