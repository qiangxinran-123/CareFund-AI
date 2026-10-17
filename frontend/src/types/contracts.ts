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

export interface Evidence {
  evidence_id: string
  document_id: string
  source_type: 'document'
  page: number | null
  text_excerpt: string
  extraction_method: 'ocr' | 'manual' | 'structured_import'
}

export type FactSourceType = 'user_input' | 'document' | 'user_correction'
export type FactVerificationStatus = 'pending' | 'supported' | 'unsupported' | 'conflicting'

export type FactValue =
  | { kind: 'text'; value: string }
  | { kind: 'date'; value: string }
  | { kind: 'boolean'; value: boolean }
  | { kind: 'integer'; value: number }
  | { kind: 'money'; value: { currency: string; amount_minor: number } }

export interface Fact {
  fact_id: string
  field: string
  value: FactValue
  source_type: FactSourceType
  evidence_ids: string[]
  verification_status: FactVerificationStatus
  user_confirmed: boolean
}

export interface AgentQuestion {
  question_id: string
  field: string
  question: string
  reason: string
  required: boolean
}

export type ValidationIssueType =
  | 'missing'
  | 'conflict'
  | 'unsupported'
  | 'invalid_format'
  | 'inconsistent_amount'
  | 'inconsistent_date'

export type ValidationSeverity = 'info' | 'warning' | 'blocking'

export interface ValidationIssue {
  issue_id: string
  type: ValidationIssueType
  severity: ValidationSeverity
  field: string
  message: string
  related_fact_ids: string[]
}

export interface ValidationResult {
  schema_version: '1.0'
  validation_id: string
  application_id: string
  application_revision: number
  issues: ValidationIssue[]
  can_finalize: boolean
  evaluated_at: string
}

export type AnalysisJobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface AnalysisJob {
  job_id: string
  application_id: string
  application_revision: number
  status: AnalysisJobStatus
  created_at: string
  updated_at: string
  error?: ErrorResponse['error'] | null
}

export interface AnalyzeRequest {
  expected_revision: number
  idempotency_key: string
}

export interface AnalysisResult {
  schema_version: '1.0'
  application_id: string
  application_revision: number
  facts: Fact[]
  evidence: Evidence[]
  questions: AgentQuestion[]
  validation: ValidationResult
}

export interface Answer {
  question_id: string
  answer: string
}

export interface AnswerSubmissionRequest {
  expected_revision: number
  answers: Answer[]
}

export interface ApplicationResponse {
  application: Application
  documents: UploadedDocument[]
  evidence: Evidence[]
}

