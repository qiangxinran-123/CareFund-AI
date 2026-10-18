import type { AnalysisResult, Application, Draft, ExportResponse, UploadedDocument } from '../../types/contracts'
import type { WorkflowStepId } from './workflowSteps'

export type WorkflowStepStatus = 'pending' | 'completed' | 'needs_attention'

export interface WorkflowStepState {
  label: string
  status: WorkflowStepStatus
}

export interface ApplicationFormState {
  busy: boolean
  dirty: boolean
  savedRevision: number | null
}

export type DocumentUploadState = 'idle' | 'selected' | 'uploading' | 'error'

export interface DocumentStepState {
  deferred: boolean
  uploadState: DocumentUploadState
}

export type AnalysisPhase = 'idle' | 'loading' | 'submitting' | 'queued' | 'running' | 'succeeded' | 'failed' | 'error' | 'stale'

export interface AnalysisStepState {
  answersSubmitting: boolean
  hasUnsavedAnswers: boolean
  phase: AnalysisPhase
}

export type DraftPhase = 'idle' | 'loading' | 'generating' | 'confirming' | 'exporting'

export interface DraftStepState {
  draft: Draft | null
  exportResult: ExportResponse | null
  hasError: boolean
  phase: DraftPhase
}

interface WorkflowStatusInput {
  analysis: AnalysisResult | null
  analysisState: AnalysisStepState
  application: Application | null
  applicationForm: ApplicationFormState
  documents: UploadedDocument[]
  documentState: DocumentStepState
  draftState: DraftStepState
}

function currentAnalysis(analysis: AnalysisResult | null, application: Application | null): boolean {
  return Boolean(
    analysis
    && application
    && analysis.application_id === application.application_id
    && analysis.application_revision === application.revision
    && analysis.validation.application_id === application.application_id
    && analysis.validation.application_revision === application.revision,
  )
}

function deliverableExport(result: ExportResponse | null, draft: Draft | null, application: Application | null): boolean {
  if (!result?.download_url || !draft || !application) return false
  if (result.application_id !== application.application_id || result.draft_id !== draft.draft_id) return false
  try {
    const url = new URL(result.download_url, 'https://carefund.local')
    return url.protocol === 'https:' || url.protocol === 'http:'
  } catch {
    return false
  }
}

export function deriveWorkflowStepStates(input: WorkflowStatusInput): Record<WorkflowStepId, WorkflowStepState> {
  const { analysis, analysisState, application, applicationForm, documents, documentState, draftState } = input

  const applicationStep: WorkflowStepState = !application
    ? { status: 'pending', label: applicationForm.busy ? '保存处理中' : '尚未保存' }
    : applicationForm.busy
      ? { status: 'needs_attention', label: '保存处理中' }
      : applicationForm.dirty || applicationForm.savedRevision !== application.revision
        ? { status: 'needs_attention', label: '有未保存修改' }
        : { status: 'completed', label: '已保存' }

  const hasFailedDocument = documents.some((document) => document.processing_status === 'failed')
  const documentStep: WorkflowStepState = documentState.uploadState === 'uploading'
    ? { status: 'pending', label: '上传处理中' }
    : documentState.uploadState === 'error' || hasFailedDocument
      ? { status: 'needs_attention', label: '材料需要处理' }
      : documents.length > 0
        ? { status: 'completed', label: '已上传材料' }
        : documentState.deferred
          ? { status: 'completed', label: '已选择稍后补充' }
          : documentState.uploadState === 'selected'
            ? { status: 'needs_attention', label: '文件尚未上传' }
            : { status: 'pending', label: '尚未处理' }

  const analysisIsCurrent = currentAnalysis(analysis, application)
  const analysisBusy = ['loading', 'submitting', 'queued', 'running'].includes(analysisState.phase)
  const analysisStep: WorkflowStepState = analysisBusy
    ? { status: 'pending', label: analysisState.phase === 'loading' ? '正在读取分析结果' : '分析处理中' }
    : analysisState.phase === 'failed' || analysisState.phase === 'error' || analysisState.phase === 'stale'
      ? { status: 'needs_attention', label: analysisState.phase === 'stale' ? '分析已过期' : '分析需要处理' }
      : analysisState.hasUnsavedAnswers
        ? { status: 'needs_attention', label: '追问回答尚未提交' }
        : analysisIsCurrent
        ? !analysis!.validation.can_finalize || analysis!.validation.issues.length > 0 || analysis!.questions.length > 0
          ? { status: 'needs_attention', label: '存在待核对事项' }
          : { status: 'completed', label: '当前版本分析完成' }
        : { status: 'pending', label: '尚未分析' }

  const draft = draftState.draft
  const draftCurrent = Boolean(draft && application
    && draft.application_id === application.application_id
    && draft.application_revision === application.revision
    && draft.status !== 'stale')
  const draftBusy = draftState.phase !== 'idle'
  const draftStep: WorkflowStepState = draftBusy
    ? { status: 'pending', label: draftState.phase === 'loading' ? '正在读取草稿' : '草稿操作处理中' }
    : draftState.hasError
      ? { status: 'needs_attention', label: '草稿操作需要处理' }
      : draft && !draftCurrent
        ? { status: 'needs_attention', label: '草稿已过期' }
        : draftCurrent && draft!.status === 'confirmed' && deliverableExport(draftState.exportResult, draft, application)
          ? { status: 'completed', label: '导出文件已就绪' }
          : draftCurrent && draft!.status === 'confirmed'
            ? { status: 'needs_attention', label: '等待有效导出' }
            : draftCurrent
              ? { status: 'needs_attention', label: '草稿待确认' }
              : { status: 'pending', label: '尚未生成草稿' }

  return {
    application: applicationStep,
    documents: documentStep,
    analysis: analysisStep,
    draft: draftStep,
  }
}
