import type {
  AnalysisJob,
  AnalysisResult,
  AnalyzeRequest,
  AnswerSubmissionRequest,
  Fact,
} from '../types/contracts'
import { ApiError, apiRequest } from './client'

export interface AnalysisApi {
  start(applicationId: string, input: AnalyzeRequest, signal?: AbortSignal): Promise<AnalysisJob>
  getJob(applicationId: string, jobId: string, signal?: AbortSignal): Promise<AnalysisJob>
  getLatest(applicationId: string, signal?: AbortSignal): Promise<AnalysisResult>
  submitAnswers(applicationId: string, input: AnswerSubmissionRequest, signal?: AbortSignal): Promise<AnalysisJob>
}

const jobStatuses = new Set(['queued', 'running', 'succeeded', 'failed'])
const verificationStatuses = new Set(['pending', 'supported', 'unsupported', 'conflicting'])
const sourceTypes = new Set(['user_input', 'document', 'user_correction'])
const issueTypes = new Set(['missing', 'conflict', 'unsupported', 'invalid_format', 'inconsistent_amount', 'inconsistent_date'])
const severities = new Set(['info', 'warning', 'blocking'])

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : null
}

function isUtc(value: unknown): value is string {
  return typeof value === 'string' && value.endsWith('Z')
}

function isFact(value: unknown): value is Fact {
  const item = record(value)
  const factValue = record(item?.value)
  if (!item || !factValue) return false
  const validValue = factValue.kind === 'boolean'
    ? typeof factValue.value === 'boolean'
    : factValue.kind === 'integer'
      ? Number.isInteger(factValue.value)
      : factValue.kind === 'money'
        ? Boolean(record(factValue.value)
          && typeof record(factValue.value)?.currency === 'string'
          && Number.isInteger(record(factValue.value)?.amount_minor))
        : (factValue.kind === 'text' || factValue.kind === 'date') && typeof factValue.value === 'string'
  return typeof item.fact_id === 'string'
    && typeof item.field === 'string'
    && validValue
    && sourceTypes.has(item.source_type as string)
    && Array.isArray(item.evidence_ids) && item.evidence_ids.every((id) => typeof id === 'string')
    && verificationStatuses.has(item.verification_status as string)
    && typeof item.user_confirmed === 'boolean'
}

export function assertAnalysisJob(value: unknown): AnalysisJob {
  const item = record(value)
  if (!item
    || typeof item.job_id !== 'string'
    || typeof item.application_id !== 'string'
    || !Number.isInteger(item.application_revision)
    || !jobStatuses.has(item.status as string)
    || !isUtc(item.created_at)
    || !isUtc(item.updated_at)
    || (item.error !== undefined && item.error !== null && !record(item.error))) {
    throw new ApiError('服务器返回的分析任务格式异常。', 'invalid_response')
  }
  return value as AnalysisJob
}

export function assertAnalysisResult(value: unknown): AnalysisResult {
  const item = record(value)
  const validation = record(item?.validation)
  const evidenceValid = Array.isArray(item?.evidence) && item.evidence.every((entry) => {
    const evidence = record(entry)
    return evidence
      && typeof evidence.evidence_id === 'string'
      && typeof evidence.document_id === 'string'
      && evidence.source_type === 'document'
      && (evidence.page === null || (Number.isInteger(evidence.page) && Number(evidence.page) >= 1))
      && typeof evidence.text_excerpt === 'string'
      && ['ocr', 'manual', 'structured_import'].includes(String(evidence.extraction_method))
  })
  const questionsValid = Array.isArray(item?.questions) && item.questions.every((entry) => {
    const question = record(entry)
    return question && typeof question.question_id === 'string' && typeof question.field === 'string'
      && typeof question.question === 'string' && typeof question.reason === 'string'
      && typeof question.required === 'boolean'
  })
  const issuesValid = Array.isArray(validation?.issues) && validation.issues.every((entry) => {
    const issue = record(entry)
    return issue && typeof issue.issue_id === 'string' && issueTypes.has(issue.type as string)
      && severities.has(issue.severity as string) && typeof issue.field === 'string'
      && typeof issue.message === 'string' && Array.isArray(issue.related_fact_ids)
      && issue.related_fact_ids.every((id) => typeof id === 'string')
  })
  if (!item || item.schema_version !== '1.0' || typeof item.application_id !== 'string'
    || !Number.isInteger(item.application_revision) || !Array.isArray(item.facts) || !item.facts.every(isFact)
    || !evidenceValid || !questionsValid || !validation || validation.schema_version !== '1.0'
    || typeof validation.validation_id !== 'string' || validation.application_id !== item.application_id
    || validation.application_revision !== item.application_revision || !issuesValid
    || typeof validation.can_finalize !== 'boolean' || !isUtc(validation.evaluated_at)) {
    throw new ApiError('服务器返回的分析结果格式异常。', 'invalid_response')
  }
  return value as AnalysisResult
}

export const httpAnalysisApi: AnalysisApi = {
  async start(applicationId, input, signal) {
    return assertAnalysisJob(await apiRequest(`applications/${encodeURIComponent(applicationId)}/analyze`, {
      method: 'POST', body: input, signal,
    }))
  },
  async getJob(applicationId, jobId, signal) {
    return assertAnalysisJob(await apiRequest(
      `applications/${encodeURIComponent(applicationId)}/analysis/jobs/${encodeURIComponent(jobId)}`,
      { signal },
    ))
  },
  async getLatest(applicationId, signal) {
    return assertAnalysisResult(await apiRequest(
      `applications/${encodeURIComponent(applicationId)}/analysis`, { signal },
    ))
  },
  async submitAnswers(applicationId, input, signal) {
    return assertAnalysisJob(await apiRequest(`applications/${encodeURIComponent(applicationId)}/answers`, {
      method: 'POST', body: input, signal,
    }))
  },
}
