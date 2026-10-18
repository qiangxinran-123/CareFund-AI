import { describe, expect, it } from 'vitest'
import { application, document, result } from '../analysis/testFixtures'
import { draft, exportResponse } from '../draft/testFixtures'
import { deriveWorkflowStepStates } from './workflowStatus'

function states(overrides: Partial<Parameters<typeof deriveWorkflowStepStates>[0]> = {}) {
  return deriveWorkflowStepStates({
    analysis: null,
    analysisState: { answersSubmitting: false, hasUnsavedAnswers: false, phase: 'idle' },
    application: null,
    applicationForm: { busy: false, dirty: false, savedRevision: null },
    documents: [],
    documentState: { deferred: false, uploadState: 'idle' },
    draftState: { draft: null, exportResult: null, hasError: false, phase: 'idle' },
    ...overrides,
  })
}

describe('workflow business status derivation', () => {
  it('marks a saved application complete only at the matching revision', () => {
    expect(states({ application, applicationForm: { busy: false, dirty: false, savedRevision: application.revision } }).application)
      .toEqual({ status: 'completed', label: '已保存' })
    expect(states({ application, applicationForm: { busy: false, dirty: false, savedRevision: application.revision - 1 } }).application.status)
      .toBe('needs_attention')
  })

  it('invalidates application completion after a local edit or during save', () => {
    expect(states({ application, applicationForm: { busy: false, dirty: true, savedRevision: application.revision } }).application.status)
      .toBe('needs_attention')
    expect(states({ application, applicationForm: { busy: true, dirty: false, savedRevision: application.revision } }).application.status)
      .toBe('needs_attention')
  })

  it('treats deferring optional documents as handled without claiming materials are complete', () => {
    const step = states({ application, documentState: { deferred: true, uploadState: 'idle' } }).documents
    expect(step).toEqual({ status: 'completed', label: '已选择稍后补充' })
    expect(step.label).not.toContain('齐全')
  })

  it('does not complete documents while a file is selected, uploading, or failed', () => {
    expect(states({ documentState: { deferred: false, uploadState: 'selected' } }).documents.status).toBe('needs_attention')
    expect(states({ documentState: { deferred: false, uploadState: 'uploading' } }).documents.status).toBe('pending')
    expect(states({ documents: [{ ...document, processing_status: 'failed' }] }).documents.status).toBe('needs_attention')
  })

  it('marks current analysis with questions or validation issues as needing attention', () => {
    const step = states({ analysis: result(), analysisState: { answersSubmitting: false, hasUnsavedAnswers: false, phase: 'succeeded' }, application }).analysis
    expect(step).toEqual({ status: 'needs_attention', label: '存在待核对事项' })
  })

  it('does not complete an analysis from an old application revision', () => {
    const old = result({ application_revision: application.revision - 1 })
    expect(states({ analysis: old, analysisState: { answersSubmitting: false, hasUnsavedAnswers: false, phase: 'stale' }, application }).analysis.status)
      .toBe('needs_attention')
  })

  it('completes a current analysis only when no follow-up issues remain', () => {
    const clean = result({ questions: [], validation: { ...result().validation, issues: [], can_finalize: true } })
    expect(states({ analysis: clean, analysisState: { answersSubmitting: false, hasUnsavedAnswers: false, phase: 'succeeded' }, application }).analysis.status)
      .toBe('completed')
  })

  it('does not treat draft generation or confirmation alone as final completion', () => {
    expect(states({ application, draftState: { draft: draft(), exportResult: null, hasError: false, phase: 'idle' } }).draft.status)
      .toBe('needs_attention')
    expect(states({ application, draftState: { draft: draft({ status: 'confirmed' }), exportResult: null, hasError: false, phase: 'idle' } }).draft.label)
      .toBe('等待有效导出')
  })

  it('requires a current confirmed draft and usable download URL for final completion', () => {
    const confirmed = draft({ status: 'confirmed' })
    expect(states({ application, draftState: { draft: confirmed, exportResult: exportResponse({ download_url: null }), hasError: false, phase: 'idle' } }).draft.status)
      .toBe('needs_attention')
    expect(states({ application, draftState: { draft: confirmed, exportResult: exportResponse(), hasError: false, phase: 'idle' } }).draft)
      .toEqual({ status: 'completed', label: '导出文件已就绪' })
    expect(states({ application, draftState: { draft: confirmed, exportResult: null, hasError: true, phase: 'idle' } }).draft.status)
      .toBe('needs_attention')
  })
})
