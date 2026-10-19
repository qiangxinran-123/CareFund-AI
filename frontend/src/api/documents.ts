import { ApiError, apiRequest } from './client'
import type { DocumentMediaType, DocumentProcessingStatus, UploadedDocument } from '../types/contracts'

export interface UploadDocumentInput {
  applicationId: string
  expectedRevision: number
  file: File
  idempotencyKey: string
  signal?: AbortSignal
}

export interface DocumentApi {
  upload(input: UploadDocumentInput): Promise<UploadedDocument>
  list(applicationId: string, signal?: AbortSignal): Promise<UploadedDocument[]>
}

const mediaTypes = new Set<DocumentMediaType>(['image/jpeg', 'image/png', 'application/pdf'])
const processingStatuses = new Set<DocumentProcessingStatus>(['uploaded', 'processing', 'processed', 'failed'])

export function isUploadedDocument(value: unknown): value is UploadedDocument {
  if (typeof value !== 'object' || value === null) return false
  const item = value as Record<string, unknown>
  return typeof item.document_id === 'string'
    && typeof item.application_id === 'string'
    && typeof item.filename === 'string'
    && item.filename.length > 0
    && mediaTypes.has(item.media_type as DocumentMediaType)
    && Number.isInteger(item.size_bytes)
    && (item.size_bytes as number) >= 1
    && typeof item.uploaded_at === 'string'
    && item.uploaded_at.endsWith('Z')
    && processingStatuses.has(item.processing_status as DocumentProcessingStatus)
}

function assertDocument(value: unknown): UploadedDocument {
  if (!isUploadedDocument(value)) {
    throw new ApiError('服务器返回的文件数据格式异常。', 'invalid_response')
  }
  return value
}

export const httpDocumentApi: DocumentApi = {
  async upload(input) {
    const form = new FormData()
    form.append('file', input.file)
    form.append('expected_revision', String(input.expectedRevision))
    const response = await apiRequest<unknown>(
      `applications/${encodeURIComponent(input.applicationId)}/documents`,
      {
        method: 'POST',
        body: form,
        headers: { 'Idempotency-Key': input.idempotencyKey },
        signal: input.signal,
      },
    )
    return assertDocument(response)
  },

  async list(applicationId, signal) {
    const response = await apiRequest<unknown>(
      `applications/${encodeURIComponent(applicationId)}/documents`,
      { signal },
    )
    if (!Array.isArray(response) || !response.every(isUploadedDocument)) {
      throw new ApiError('服务器返回的文件列表格式异常。', 'invalid_response')
    }
    return response
  },
}
