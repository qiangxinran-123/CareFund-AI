import { useEffect, useRef, useState } from 'react'
import { applicationApi } from './api'
import { AppLayout } from './components/layout/AppLayout'
import { ApplicationForm } from './features/application/ApplicationForm'
import { DocumentManager } from './features/documents/DocumentManager'
import { AnalysisPanel } from './features/analysis/AnalysisPanel'
import { DraftPanel } from './features/draft/DraftPanel'
import { WorkflowNavigation } from './features/workflow/WorkflowNavigation'
import { WorkflowStepper } from './features/workflow/WorkflowStepper'
import { workflowSteps, workflowStepIndex, type WorkflowStepId } from './features/workflow/workflowSteps'
import type { AnalysisResult, Application, UploadedDocument } from './types/contracts'

export default function App() {
  const [application, setApplication] = useState<Application | null>(null)
  const [documents, setDocuments] = useState<UploadedDocument[]>([])
  const [analysis, setAnalysis] = useState<AnalysisResult | null>(null)
  const [currentStep, setCurrentStep] = useState<WorkflowStepId>('application')
  const [visitedSteps, setVisitedSteps] = useState<ReadonlySet<WorkflowStepId>>(() => new Set(['application']))
  const [navigationMessage, setNavigationMessage] = useState<string | null>(null)
  const hasNavigated = useRef(false)

  function handleApplicationChange(next: Application | null) {
    if (next?.application_id !== application?.application_id) {
      setDocuments([])
      setCurrentStep('application')
      setVisitedSteps(new Set(['application']))
    }
    if (next?.application_id !== application?.application_id || next?.revision !== application?.revision) setAnalysis(null)
    setApplication(next)
  }

  function showStep(step: WorkflowStepId) {
    setNavigationMessage(null)
    setVisitedSteps((current) => new Set(current).add(step))
    hasNavigated.current = true
    setCurrentStep(step)
  }

  function goPrevious() {
    const previous = workflowSteps[workflowStepIndex(currentStep) - 1]
    if (previous) showStep(previous.id)
  }

  function goNext() {
    if (currentStep === 'application' && !application) {
      setNavigationMessage('请先完成申请信息的三步填写并成功保存，再进入材料上传。')
      return
    }
    const next = workflowSteps[workflowStepIndex(currentStep) + 1]
    if (next) showStep(next.id)
  }

  function revisitStep(step: WorkflowStepId) {
    if (visitedSteps.has(step)) showStep(step)
  }

  useEffect(() => {
    if (!hasNavigated.current) return
    const panel = document.querySelector<HTMLElement>(`[data-workflow-panel="${currentStep}"]`)
    const heading = panel?.querySelector<HTMLElement>('h2')
    heading?.focus({ preventScroll: true })
    if (typeof panel?.scrollIntoView === 'function') panel.scrollIntoView({ block: 'start' })
  }, [currentStep])

  async function refreshApplication() {
    if (!application) return
    const response = await applicationApi.get(application.application_id)
    setApplication(response.application)
  }

  return (
    <AppLayout>
      <WorkflowStepper currentStep={currentStep} onStepSelect={revisitStep} visitedSteps={visitedSteps} />
      <div data-workflow-panel="application" hidden={currentStep !== 'application'}>
        <ApplicationForm applicationSnapshot={application} onApplicationChange={handleApplicationChange} />
      </div>
      <div data-workflow-panel="documents" hidden={currentStep !== 'documents'}>
        <DocumentManager application={application} onDocumentsChange={setDocuments} onRefreshApplication={refreshApplication} />
      </div>
      <div data-workflow-panel="analysis" hidden={currentStep !== 'analysis'}>
        <AnalysisPanel application={application} documents={documents} onAnalysisChange={setAnalysis} onRefreshApplication={refreshApplication} />
      </div>
      <div data-workflow-panel="draft" hidden={currentStep !== 'draft'}>
        <DraftPanel analysis={analysis} application={application} documents={documents} />
      </div>
      <WorkflowNavigation
        currentStep={currentStep}
        nextBlockedReason={currentStep === 'application' && !application ? navigationMessage : null}
        onNext={goNext}
        onPrevious={goPrevious}
      />
    </AppLayout>
  )
}

