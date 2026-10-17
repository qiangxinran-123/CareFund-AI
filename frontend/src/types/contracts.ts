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

export type AgeGroup = 'child' | 'adult' | 'older_adult' | 'unknown'

export interface PatientInfo {
  display_name: string
  age_group?: AgeGroup | null
  medical_summary: string | null
}

export interface PatientInfoPatch {
  display_name?: string
  age_group?: AgeGroup | null
  medical_summary?: string | null
}

export interface Application {
  application_id: string
  schema_version: '1.0'
  revision: number
  status: ApplicationStatus
  patient_info: PatientInfo
  created_at: string
  updated_at: string
}

export interface CreateApplicationRequest {
  patient_info: PatientInfo
}

export interface UpdateApplicationRequest {
  expected_revision: number
  patient_info: PatientInfoPatch
}

export type DocumentMediaType = 'image/jpeg' | 'image/png' | 'application/pdf'

export type DocumentProcessingStatus = 'uploaded' | 'processing' | 'processed' | 'failed'

export interface UploadedDocument {
  document_id: string
  application_id: string
  filename: string
  media_type: DocumentMediaType
  size_bytes: number
  uploaded_at: string
  processing_status: DocumentProcessingStatus
}

export interface ApplicationResponse {
  application: Application
  documents: UploadedDocument[]
  evidence: Array<{
    evidence_id: string
    document_id: string
    source_type: 'document'
    page: number | null
    text_excerpt: string
    extraction_method: 'ocr' | 'manual' | 'structured_import'
  }>
}

