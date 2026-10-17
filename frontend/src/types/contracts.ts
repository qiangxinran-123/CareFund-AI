// Aligned with contracts/schemas/common.schema.json and application.schema.json.
export type ErrorCode =
  | 'INVALID_REQUEST'
  | 'RESOURCE_NOT_FOUND'
  | 'UNSUPPORTED_FILE'
  | 'FILE_TOO_LARGE'
  | 'OCR_FAILED'
  | 'AGENT_UNAVAILABLE'
  | 'VALIDATION_FAILED'
  | 'STATE_CONFLICT'
  | 'EXPORT_BLOCKED'
  | 'INTERNAL_ERROR'

export interface ErrorDetail {
  field?: string | null
  message: string
  value?: unknown
}

export interface ErrorResponse {
  error: {
    code: ErrorCode
    message: string
    details: ErrorDetail[]
  }
  request_id: string
}

export type ApplicationStatus =
  | 'collecting'
  | 'reviewing'
  | 'ready_for_draft'
  | 'draft_ready'
  | 'confirmed'
  | 'exported'

export interface ApplicationResponse {
  application: {
    application_id: string
    schema_version: '1.0'
    revision: number
    status: ApplicationStatus
    patient_info: {
      display_name: string
      age_group?: 'child' | 'adult' | 'older_adult' | 'unknown' | null
      medical_summary: string | null
    }
    created_at: string
    updated_at: string
  }
  documents: Array<{
    document_id: string
    application_id: string
    filename: string
    media_type: 'image/jpeg' | 'image/png' | 'application/pdf'
    size_bytes: number
    uploaded_at: string
    processing_status: 'uploaded' | 'processing' | 'processed' | 'failed'
  }>
  evidence: Array<{
    evidence_id: string
    document_id: string
    source_type: 'document'
    page: number | null
    text_excerpt: string
    extraction_method: 'ocr' | 'manual' | 'structured_import'
  }>
}

