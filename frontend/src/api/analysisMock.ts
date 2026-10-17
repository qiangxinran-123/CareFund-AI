import type { AnalysisApi } from './analysis'
import { ApiError } from './client'
import { advanceMockApplicationRevision, mockApplicationApi } from './applicationMock'
import type { AnalysisJob, AnalysisResult, ErrorCode } from '../types/contracts'

interface MockJobState {
  job: AnalysisJob
  polls: number
  result: AnalysisResult
}

const jobs = new Map<string, MockJobState>()
const jobsByIntent = new Map<string, string>()
const latestByApplication = new Map<string, AnalysisResult>()
let sequence = 0

function mockError(status: number, code: ErrorCode, message: string): ApiError {
  return new ApiError(message, 'http', status, {
    error: { code, message, details: [] },
    request_id: 'req_mock_analysis',
  })
}

function now(): string {
  return new Date().toISOString()
}

function ensureActive(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')
}

function resultFor(applicationId: string, revision: number): AnalysisResult {
  return {
    schema_version: '1.0',
    application_id: applicationId,
    application_revision: revision,
    facts: [
      {
        fact_id: 'fact_mock_summary',
        field: 'patient.medical_summary',
        value: { kind: 'text', value: '用户自述正在接受示例性治疗。' },
        source_type: 'user_input', evidence_ids: [], verification_status: 'pending', user_confirmed: true,
      },
      {
        fact_id: 'fact_mock_cost',
        field: 'treatment.estimated_cost',
        value: { kind: 'money', value: { currency: 'CNY', amount_minor: 1250000 } },
        source_type: 'document', evidence_ids: ['ev_mock_cost'], verification_status: 'supported', user_confirmed: false,
      },
      {
        fact_id: 'fact_mock_date',
        field: 'treatment.recorded_date',
        value: { kind: 'date', value: '2026-10-18' },
        source_type: 'document', evidence_ids: ['ev_mock_date'], verification_status: 'conflicting', user_confirmed: false,
      },
    ],
    evidence: [
      {
        evidence_id: 'ev_mock_cost', document_id: 'doc_mock_001', source_type: 'document', page: 1,
        text_excerpt: '虚构示例费用预估合计人民币 12,500.00 元。', extraction_method: 'ocr',
      },
      {
        evidence_id: 'ev_mock_date', document_id: 'doc_mock_001', source_type: 'document', page: 2,
        text_excerpt: '虚构示例材料记录日期为 2026-10-18。', extraction_method: 'ocr',
      },
    ],
    questions: [
      {
        question_id: 'question_mock_date', field: 'treatment.recorded_date', required: true,
        question: '请确认材料中的日期是否为本次治疗记录日期。',
        reason: '该日期与用户填写的时间描述不一致，需要您澄清。',
      },
      {
        question_id: 'question_mock_city', field: 'contact.city', required: false,
        question: '如方便，请补充当前所在城市。', reason: '现有申请资料中没有城市信息。',
      },
    ],
    validation: {
      schema_version: '1.0', validation_id: `validation_mock_${revision}`, application_id: applicationId,
      application_revision: revision, can_finalize: false, evaluated_at: now(),
      issues: [
        {
          issue_id: 'issue_mock_date', type: 'inconsistent_date', severity: 'blocking',
          field: 'treatment.recorded_date', message: '材料日期与用户填写的时间描述不一致，需要核对。',
          related_fact_ids: ['fact_mock_date'],
        },
        {
          issue_id: 'issue_mock_city', type: 'missing', severity: 'warning', field: 'contact.city',
          message: '当前缺少城市信息。', related_fact_ids: [],
        },
        {
          issue_id: 'issue_mock_summary', type: 'unsupported', severity: 'info',
          field: 'patient.medical_summary', message: '该信息目前仅来自用户自述。',
          related_fact_ids: ['fact_mock_summary'],
        },
      ],
    },
  }
}

function createJob(applicationId: string, revision: number, result: AnalysisResult): AnalysisJob {
  sequence += 1
  const timestamp = now()
  const job: AnalysisJob = {
    job_id: `job_mock_${sequence}`, application_id: applicationId, application_revision: revision,
    status: 'queued', created_at: timestamp, updated_at: timestamp, error: null,
  }
  jobs.set(job.job_id, { job, polls: 0, result })
  return job
}

export const mockAnalysisApi: AnalysisApi = {
  async start(applicationId, input, signal) {
    ensureActive(signal)
    const response = await mockApplicationApi.get(applicationId)
    if (response.application.revision !== input.expected_revision) {
      throw mockError(409, 'STATE_CONFLICT', '申请版本已变化，请刷新后重新分析。')
    }
    const intent = `${applicationId}:${input.expected_revision}:${input.idempotency_key}`
    const existingId = jobsByIntent.get(intent)
    if (existingId) return structuredClone(jobs.get(existingId)!.job)
    const job = createJob(applicationId, input.expected_revision, resultFor(applicationId, input.expected_revision))
    jobsByIntent.set(intent, job.job_id)
    return structuredClone(job)
  },
  async getJob(applicationId, jobId, signal) {
    ensureActive(signal)
    const state = jobs.get(jobId)
    if (!state || state.job.application_id !== applicationId) {
      throw mockError(404, 'RESOURCE_NOT_FOUND', 'Mock 分析任务不存在。')
    }
    state.polls += 1
    state.job = {
      ...state.job,
      status: state.polls === 1 ? 'running' : 'succeeded',
      updated_at: now(),
    }
    if (state.job.status === 'succeeded') latestByApplication.set(applicationId, state.result)
    return structuredClone(state.job)
  },
  async getLatest(applicationId, signal) {
    ensureActive(signal)
    const result = latestByApplication.get(applicationId)
    if (!result) throw mockError(404, 'RESOURCE_NOT_FOUND', '当前申请尚无分析结果。')
    return structuredClone(result)
  },
  async submitAnswers(applicationId, input, signal) {
    ensureActive(signal)
    const current = latestByApplication.get(applicationId)
    if (!current) throw mockError(404, 'RESOURCE_NOT_FOUND', '当前申请尚无可回答的问题。')
    if (input.answers.length < 1 || input.answers.some((answer) => !answer.answer.trim())) {
      throw mockError(422, 'VALIDATION_FAILED', '回答内容不能为空。')
    }
    const revision = advanceMockApplicationRevision(applicationId, input.expected_revision)
    const next = resultFor(applicationId, revision)
    next.questions = []
    next.validation.issues = []
    next.validation.can_finalize = true
    const job = createJob(applicationId, revision, next)
    return structuredClone(job)
  },
}

export function resetMockAnalysis(): void {
  jobs.clear()
  jobsByIntent.clear()
  latestByApplication.clear()
  sequence = 0
}
