import type { AnalysisJob, AnalysisResult, Application, UploadedDocument } from '../../types/contracts'

export const application: Application = {
  application_id: 'app_test_001', schema_version: '1.0', revision: 3, status: 'reviewing',
  patient_info: { display_name: '测试用户', age_group: 'adult', medical_summary: '测试自述' },
  created_at: '2026-10-17T01:00:00Z', updated_at: '2026-10-17T02:00:00Z',
}

export const document: UploadedDocument = {
  document_id: 'doc_test_001', application_id: application.application_id, filename: '费用清单.pdf',
  media_type: 'application/pdf', size_bytes: 1024, uploaded_at: '2026-10-17T02:00:00Z', processing_status: 'processed',
}

export function job(status: AnalysisJob['status'], revision = application.revision): AnalysisJob {
  return {
    job_id: 'job_test_001', application_id: application.application_id, application_revision: revision,
    status, created_at: '2026-10-17T02:00:00Z', updated_at: '2026-10-17T02:01:00Z', error: null,
  }
}

export function result(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    schema_version: '1.0', application_id: application.application_id, application_revision: application.revision,
    facts: [
      {
        fact_id: 'fact_user', field: 'patient.medical_summary', value: { kind: 'text', value: '用户自述内容' },
        source_type: 'user_input', evidence_ids: [], verification_status: 'pending', user_confirmed: true,
      },
      {
        fact_id: 'fact_cost', field: 'treatment.estimated_cost', value: { kind: 'money', value: { currency: 'CNY', amount_minor: 1250000 } },
        source_type: 'document', evidence_ids: ['ev_cost'], verification_status: 'supported', user_confirmed: false,
      },
      {
        fact_id: 'fact_conflict', field: 'treatment.recorded_date', value: { kind: 'date', value: '2026-10-17' },
        source_type: 'document', evidence_ids: ['ev_missing'], verification_status: 'conflicting', user_confirmed: false,
      },
    ],
    evidence: [
      { evidence_id: 'ev_cost', document_id: document.document_id, source_type: 'document', page: 2, text_excerpt: '费用合计 12,500 元', extraction_method: 'ocr' },
    ],
    questions: [
      { question_id: 'q_required', field: 'contact.city', question: '请补充所在城市', reason: '当前缺少城市信息', required: true },
      { question_id: 'q_optional', field: 'patient.medical_summary', question: '是否还有其他说明', reason: '帮助完整整理', required: false },
    ],
    validation: {
      schema_version: '1.0', validation_id: 'validation_test', application_id: application.application_id,
      application_revision: application.revision, can_finalize: false, evaluated_at: '2026-10-17T02:02:00Z',
      issues: [
        { issue_id: 'issue_missing', type: 'missing', severity: 'warning', field: 'contact.city', message: '缺少城市信息', related_fact_ids: [] },
        { issue_id: 'issue_conflict', type: 'conflict', severity: 'blocking', field: 'treatment.recorded_date', message: '日期信息不一致', related_fact_ids: ['fact_conflict'] },
        { issue_id: 'issue_unsupported', type: 'unsupported', severity: 'info', field: 'patient.medical_summary', message: '目前仅来自用户自述', related_fact_ids: ['fact_user'] },
      ],
    },
    ...overrides,
  }
}
