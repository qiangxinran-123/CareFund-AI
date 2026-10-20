import { useEffect, useMemo, useRef, useState } from 'react'
import { applicationApi } from './api'
import { AppLayout } from './components/layout/AppLayout'
import { ApplicationForm } from './features/application/ApplicationForm'
import { DocumentManager } from './features/documents/DocumentManager'
import { AnalysisPanel } from './features/analysis/AnalysisPanel'
import { DraftPanel } from './features/draft/DraftPanel'
import { WorkflowNavigation } from './features/workflow/WorkflowNavigation'
import { WorkflowStepper } from './features/workflow/WorkflowStepper'
import { workflowSteps, workflowStepIndex, type WorkflowStepId } from './features/workflow/workflowSteps'
import {
  deriveWorkflowStepStates,
  type AnalysisStepState,
  type ApplicationFormState,
  type DocumentStepState,
  type DraftStepState,
} from './features/workflow/workflowStatus'
import type { AnalysisResult, Application, UploadedDocument } from './types/contracts'

export default function App() {
  const [application, setApplication] = useState<Application | null>(null)
  const [documents, setDocuments] = useState<UploadedDocument[]>([])
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [currentStep, setCurrentStep] = useState<WorkflowStepId>('application')
  const [visitedSteps, setVisitedSteps] = useState<ReadonlySet<WorkflowStepId>>(() => new Set(['application']))
  const [navigationMessage, setNavigationMessage] = useState<string | null>(null)
  const [applicationFormState, setApplicationFormState] = useState<ApplicationFormState>({ busy: false, dirty: false, savedRevision: null })
  const [documentStepState, setDocumentStepState] = useState<DocumentStepState>({ deferred: false, uploadState: 'idle' })
  const [analysisStepState, setAnalysisStepState] = useState<AnalysisStepState>({ answersSubmitting: false, hasUnsavedAnswers: false, phase: 'idle' })
  const [draftStepState, setDraftStepState] = useState<DraftStepState>({ draft: null, exportResult: null, hasError: false, phase: 'idle' })
  const hasNavigated = useRef(false)

  const stepStates = useMemo(() => deriveWorkflowStepStates({
    analysis,
    analysisState: analysisStepState,
    application,
    applicationForm: applicationFormState,
    documents,
    documentState: documentStepState,
    draftState: draftStepState,
  }), [analysis, analysisStepState, application, applicationFormState, documents, documentStepState, draftStepState])
  const shouldWarnBeforeUnload = applicationFormState.dirty
    || analysisStepState.hasUnsavedAnswers
    || ['submitting', 'queued', 'running'].includes(analysisStepState.phase)
    || documentStepState.uploadState === 'selected'
    || documentStepState.uploadState === 'uploading'
    || ['generating', 'confirming', 'exporting'].includes(draftStepState.phase)

  function handleApplicationChange(next: Application | null) {
    if (next?.application_id !== application?.application_id) {
      setDocuments([])
      setDocumentStepState({ deferred: false, uploadState: 'idle' })
      setAnalysisStepState({ answersSubmitting: false, hasUnsavedAnswers: false, phase: 'idle' })
      setDraftStepState({ draft: null, exportResult: null, hasError: false, phase: 'idle' })
      setCurrentStep('application')
      setVisitedSteps(new Set(['application']))
    }
    if (next?.application_id !== application?.application_id || next?.revision !== application?.revision) setAnalysis(null)
    setApplication(next)
  }

  function leaveBlockedReason(): string | null {
    if (currentStep === 'application') {
      if (applicationFormState.busy) return '申请信息正在保存或恢复，请等待操作完成后再离开。'
      if (applicationFormState.dirty) return '申请信息存在未保存修改，请先保存后再离开此步骤。'
    }
    if (currentStep === 'analysis') {
      if (analysisStepState.answersSubmitting) return '补充信息正在提交，请等待操作完成后再离开。'
      if (analysisStepState.hasUnsavedAnswers) return '补充问题存在尚未提交的回答，请先提交后再离开此步骤。'
    }
    return null
  }

  function showStep(step: WorkflowStepId) {
    setNavigationMessage(null)
    setVisitedSteps((current) => new Set(current).add(step))
    hasNavigated.current = true
    setCurrentStep(step)
  }

  function goPrevious() {
    const previous = workflowSteps[workflowStepIndex(currentStep) - 1]
    if (previous) attemptShowStep(previous.id)
  }

  function goNext() {
    const blocked = leaveBlockedReason()
    if (blocked) {
      setNavigationMessage(blocked)
      return
    }
    if (currentStep === 'application' && !application) {
      setNavigationMessage('请先完成申请信息的三步填写并成功保存，再进入材料上传。')
      return
    }
    const next = workflowSteps[workflowStepIndex(currentStep) + 1]
    if (next) showStep(next.id)
  }

  function revisitStep(step: WorkflowStepId) {
    if (visitedSteps.has(step)) attemptShowStep(step)
  }

  function attemptShowStep(step: WorkflowStepId) {
    if (step === currentStep) return
    const blocked = leaveBlockedReason()
    if (blocked) {
      setNavigationMessage(blocked)
      return
    }
    showStep(step)
  }

  useEffect(() => {
    if (!hasNavigated.current) return
    const panel = document.querySelector<HTMLElement>(`[data-workflow-panel="${currentStep}"]`)
    const heading = panel?.querySelector<HTMLElement>('h2')
    heading?.focus({ preventScroll: true })
    if (typeof panel?.scrollIntoView === 'function') panel.scrollIntoView({ block: 'start' })
  }, [currentStep])

  useEffect(() => {
    if (!shouldWarnBeforeUnload) return
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', warnBeforeUnload)
    return () => window.removeEventListener('beforeunload', warnBeforeUnload)
  }, [shouldWarnBeforeUnload])

  useEffect(() => {
    if (!navigationMessage) return
    if (currentStep === 'application' && application && !applicationFormState.busy && !applicationFormState.dirty) {
      setNavigationMessage(null)
    }
    if (currentStep === 'analysis' && !analysisStepState.answersSubmitting && !analysisStepState.hasUnsavedAnswers) {
      setNavigationMessage(null)
    }
  }, [analysisStepState.answersSubmitting, analysisStepState.hasUnsavedAnswers, application, applicationFormState.busy, applicationFormState.dirty, currentStep, navigationMessage])

  async function refreshApplication() {
    if (!application) return
    const response = await applicationApi.get(application.application_id)
    setApplication(response.application)
  }

  return (
    <AppLayout>
      <WorkflowStepper currentStep={currentStep} onStepSelect={revisitStep} stepStates={stepStates} visitedSteps={visitedSteps} />
      <div data-workflow-panel="application" hidden={currentStep !== 'application'}>
        <ApplicationForm applicationSnapshot={application} onApplicationChange={handleApplicationChange} onStateChange={setApplicationFormState} />
      </div>
      <div data-workflow-panel="documents" hidden={currentStep !== 'documents'}>
        <DocumentManager application={application} onDocumentsChange={setDocuments} onRefreshApplication={refreshApplication} onStateChange={setDocumentStepState} />
      </div>
      <div data-workflow-panel="analysis" hidden={currentStep !== 'analysis'}>
        <AnalysisPanel application={application} documents={documents} onAnalysisChange={setAnalysis} onRefreshApplication={refreshApplication} onStateChange={setAnalysisStepState} />
      </div>
      <div data-workflow-panel="draft" hidden={currentStep !== 'draft'}>
        <DraftPanel analysis={analysis} application={application} documents={documents} onStateChange={setDraftStepState} />
      </div>
      <WorkflowNavigation
        blockedReason={navigationMessage ?? leaveBlockedReason()}
        currentStep={currentStep}
        onNext={goNext}
        onPrevious={goPrevious}
      />
    </AppLayout>
  )
}

