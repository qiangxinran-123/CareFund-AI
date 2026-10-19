import { useEffect, useRef, useState } from 'react'
import { analysisApi as defaultApi, isMockMode as defaultMockMode } from '../../api'
import type { AnalysisApi } from '../../api/analysis'
import { ApiError } from '../../api/client'
import type { AnalysisJob, AnalysisResult, Answer, Application, UploadedDocument } from '../../types/contracts'
import type { AnalysisPhase, AnalysisStepState } from '../workflow/workflowStatus'
import { FactList } from './FactList'
import { FollowUpQuestions } from './FollowUpQuestions'
import { ValidationIssueList } from './ValidationIssueList'

interface Props {
  api?: AnalysisApi
  application: Application | null
  documents?: UploadedDocument[]
  maxPollAttempts?: number
  mockMode?: boolean
  onRefreshApplication?: () => Promise<void>
  onAnalysisChange?: (result: AnalysisResult | null) => void
  onStateChange?: (state: AnalysisStepState) => void
  pollIntervalMs?: number
}

const phaseCopy: Record<AnalysisPhase, string> = {
  idle: '尚未开始整理资料。',
  loading: '正在查看已有整理结果…',
  submitting: '正在提交整理请求…',
  queued: '已收到请求，正在等待处理。',
  running: '正在整理您的资料，请稍候。',
  succeeded: '资料整理完成，请查看需要核对的信息。',
  failed: '资料整理没有完成，请重试。',
  error: '资料整理遇到问题，请重试。',
  stale: '申请信息已更新，之前的整理结果不能继续使用。请重新整理。',
}

function createKey(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID().replaceAll('-', '_')
    : `analysis_${Date.now()}_${Math.random().toString(36).slice(2)}`
}

function delay(milliseconds: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, milliseconds)
    signal.addEventListener('abort', () => {
      window.clearTimeout(timer)
      reject(new DOMException('The operation was aborted.', 'AbortError'))
    }, { once: true })
  })
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return '申请信息已更新，请刷新后重新操作。'
    if (error.status === 422) return `当前信息暂时不能整理：${error.message}`
    return error.message
  }
  return error instanceof Error ? error.message : '操作失败，请稍后重试。'
}

export function AnalysisPanel({
  api = defaultApi,
  application,
  documents = [],
  maxPollAttempts = 60,
  mockMode = defaultMockMode,
  onRefreshApplication,
  onAnalysisChange,
  onStateChange,
  pollIntervalMs = 2000,
}: Props) {
  const [phase, setPhase] = useState<AnalysisPhase>('idle')
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [followUpState, setFollowUpState] = useState({ answersSubmitting: false, hasUnsavedAnswers: false })
  const [questionToAnswer, setQuestionToAnswer] = useState<string | null>(null)
  const questionTriggerRef = useRef<HTMLElement | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef(0)
  const intentRef = useRef<{ applicationId: string; revision: number; key: string } | null>(null)

  const applicationId = application?.application_id
  const applicationRevision = application?.revision
  const busy = phase === 'loading' || phase === 'submitting' || phase === 'queued' || phase === 'running'

  useEffect(() => {
    onAnalysisChange?.(result)
  }, [onAnalysisChange, result])

  useEffect(() => {
    onStateChange?.({ phase, ...followUpState })
  }, [followUpState, onStateChange, phase])

  useEffect(() => {
    if (!result) setFollowUpState({ answersSubmitting: false, hasUnsavedAnswers: false })
  }, [result])

  useEffect(() => {
    controllerRef.current?.abort()
    const request = ++requestRef.current
    setJob(null)
    setResult(null)
    setError(null)
    setNotice(null)
    intentRef.current = null
    if (!applicationId || !applicationRevision) {
      setPhase('idle')
      return
    }

    const controller = new AbortController()
    controllerRef.current = controller
    setPhase('loading')
    api.getLatest(applicationId, controller.signal)
      .then((latest) => {
        if (request !== requestRef.current || controller.signal.aborted) return
        if (latest.application_id !== applicationId || latest.application_revision !== applicationRevision) {
          setPhase('stale')
          return
        }
        setResult(latest)
        setPhase('succeeded')
      })
      .catch((caught: unknown) => {
        if (request !== requestRef.current || isAbort(caught)) return
        if (caught instanceof ApiError && caught.status === 404) {
          setPhase('idle')
          return
        }
        setError(describeError(caught))
        setPhase('error')
      })
    return () => controller.abort()
  }, [api, applicationId, applicationRevision])

  async function pollJob(initialJob: AnalysisJob, expectedRevision: number, refreshAfter: boolean) {
    const controller = controllerRef.current
    const request = requestRef.current
    if (!controller) return
    let current = initialJob
    setJob(current)

    try {
      for (let attempt = 0; attempt <= maxPollAttempts; attempt += 1) {
        if (request !== requestRef.current || controller.signal.aborted) return
        if (current.application_id !== applicationId || current.application_revision !== expectedRevision) {
          setResult(null)
          setError('任务结果与当前申请不一致，已停止显示。请重新整理资料。')
          setPhase('stale')
          return
        }
        setPhase(current.status === 'queued' ? 'queued' : current.status === 'running' ? 'running' : current.status === 'failed' ? 'failed' : 'loading')
        if (current.status === 'failed') {
          setError(current.error?.message || '资料整理没有完成，请重试。')
          return
        }
        if (current.status === 'succeeded') {
          const latest = await api.getLatest(applicationId!, controller.signal)
          if (latest.application_id !== applicationId || latest.application_revision !== expectedRevision) {
            setResult(null)
            setError('整理结果与当前申请不一致，已停止显示。请重新整理资料。')
            setPhase('stale')
            return
          }
          if (refreshAfter && onRefreshApplication) {
            try {
              await onRefreshApplication()
            } catch {
              setResult(null)
              setError('补充信息已提交，但暂时无法更新申请信息。请刷新页面后查看最新结果。')
              setPhase('stale')
              return
            }
          }
          setResult(latest)
          setJob(current)
          setPhase('succeeded')
          setNotice(refreshAfter ? (latest.validation.issues.length > 0 ? '信息已更新，还有内容需要核对。' : '信息已更新，核对完成。') : null)
          intentRef.current = null
          return
        }
        if (attempt === maxPollAttempts) {
          setError('资料整理时间较长，已暂停自动查询。您可以继续查看进度。')
          setPhase('error')
          return
        }
        await delay(pollIntervalMs, controller.signal)
        current = await api.getJob(applicationId!, current.job_id, controller.signal)
        setJob(current)
      }
    } catch (caught) {
      if (request !== requestRef.current || isAbort(caught)) return
      setError(`查看整理进度没有完成：${describeError(caught)}`)
      setPhase('error')
    }
  }

  async function startAnalysis() {
    if (!application || busy) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    requestRef.current += 1
    const intent = intentRef.current?.applicationId === application.application_id
      && intentRef.current.revision === application.revision
      ? intentRef.current
      : { applicationId: application.application_id, revision: application.revision, key: createKey() }
    intentRef.current = intent
    setPhase('submitting')
    setError(null)
    setNotice(null)
    setResult(null)
    try {
      const nextJob = await api.start(application.application_id, {
        expected_revision: application.revision,
        idempotency_key: intent.key,
      }, controller.signal)
      await pollJob(nextJob, application.revision, false)
    } catch (caught) {
      if (isAbort(caught)) return
      setError(describeError(caught))
      setPhase('error')
    }
  }

  async function submitAnswers(answers: Answer[]) {
    if (!application || busy) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    requestRef.current += 1
    setPhase('submitting')
    setError(null)
    setNotice('补充信息已提交，正在重新核对…')
    try {
      const nextJob = await api.submitAnswers(application.application_id, {
        expected_revision: application.revision,
        answers,
      }, controller.signal)
      setResult(null)
      await pollJob(nextJob, nextJob.application_revision, true)
    } catch (caught) {
      if (isAbort(caught)) return
      setPhase('succeeded')
      setNotice(null)
      throw new Error(describeError(caught))
    }
  }

  function resumePolling() {
    if (!job || !application) return
    controllerRef.current?.abort()
    controllerRef.current = new AbortController()
    requestRef.current += 1
    setError(null)
    void pollJob(job, job.application_revision, job.application_revision !== application.revision)
  }

  return (
    <section aria-labelledby="analysis-title" className="mt-8 rounded-2xl border border-blue-100 bg-white p-5 shadow-sm sm:p-8">
      <div className="flex flex-col gap-4 border-b border-slate-100 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-700">申请流程 · 信息核对与补充</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900" id="analysis-title" tabIndex={-1}>核对您的申请信息</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">我们已整理您填写和上传的资料。请重点查看需要补充或核对的内容。</p>
        </div>
        {mockMode && <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">Mock 演示模式 · 整理结果为虚构示例</span>}
      </div>

      {!application ? (
        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">请先填写并保存求助信息，再整理和核对资料。</p>
          <a className="mt-3 inline-flex text-sm font-medium text-blue-700 underline underline-offset-4" href="#application-form-title">返回填写申请信息</a>
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">当前申请</p><p className="mt-1 break-words text-sm font-medium leading-6 text-slate-800">{application.application_id}</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">申请版本</p><p className="mt-1 text-sm font-medium text-slate-800">版本 {application.revision}</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">已上传材料</p><p className="mt-1 text-sm font-medium text-slate-800">{documents.length} 份</p></div>
          </div>
          {documents.length === 0 && <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">还没有上传材料。您仍可以整理已填写的内容，但部分信息可能无法通过材料核对；能否继续以服务端结果为准。</p>}

          <div className="mt-5 flex flex-col gap-4 rounded-xl border border-blue-100 bg-blue-50/60 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div aria-live="polite">
              <p className="text-xs font-medium text-blue-700">整理状态</p>
              <p className="mt-1 text-sm text-slate-700">{phaseCopy[phase]}</p>
              {notice && <p className="mt-1 text-xs text-emerald-800" role="status">{notice}</p>}
              {error && <p className="mt-2 text-sm text-red-700" role="alert">{error}</p>}
            </div>
            <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
              {phase === 'error' && job && <button className="button-secondary w-full sm:w-auto" onClick={resumePolling} type="button">继续查看进度</button>}
              <button className="button-primary w-full sm:w-auto" disabled={busy} onClick={() => void startAnalysis()} type="button">
                {busy ? '正在整理资料…' : result ? '重新检查资料' : phase === 'error' && !job ? '重新尝试' : '开始整理和核对'}
              </button>
            </div>
          </div>

          {result && (phase === 'succeeded' || phase === 'submitting') && (
            <div>
              <div className="mt-7 rounded-xl border border-slate-200 p-4">
                <p className="text-sm font-semibold text-slate-900">核对概况</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">需要处理：{result.validation.issues.length} 项 · 其他已整理信息：{result.facts.filter((fact) => !result.validation.issues.some((issue) => issue.related_fact_ids.includes(fact.fact_id)) && fact.verification_status !== 'pending' && fact.verification_status !== 'conflicting').length} 条</p>
              </div>
              <FactList documents={documents} evidence={result.evidence} facts={result.facts} issues={result.validation.issues} onAnswerQuestion={(questionId, trigger) => { questionTriggerRef.current = trigger; setQuestionToAnswer(questionId) }} questionForField={(field) => {
                const matching = result.questions.filter((question) => question.field === field)
                return matching.length === 1 && result.validation.issues.filter((issue) => issue.field === field).length === 1 ? matching[0] : undefined
              }} />
              {result.validation.issues.some((issue) => !issue.related_fact_ids.some((factId) => result.facts.some((fact) => fact.fact_id === factId))) && (
                <ValidationIssueList issues={result.validation.issues.filter((issue) => !issue.related_fact_ids.some((factId) => result.facts.some((fact) => fact.fact_id === factId)))} onAnswerQuestion={(questionId, trigger) => { questionTriggerRef.current = trigger; setQuestionToAnswer(questionId) }} questionForField={(field) => {
                  const matching = result.questions.filter((question) => question.field === field)
                  return matching.length === 1 && result.validation.issues.filter((issue) => issue.field === field).length === 1 ? matching[0] : undefined
                }} />
              )}
              <FollowUpQuestions dialogTrigger={questionTriggerRef.current} onDialogClose={() => { questionTriggerRef.current = null; setQuestionToAnswer(null) }} onStateChange={setFollowUpState} onSubmit={submitAnswers} openQuestionId={questionToAnswer} questions={result.questions} standaloneQuestionIds={result.questions.filter((question) => result.validation.issues.filter((issue) => issue.field === question.field).length !== 1 || result.questions.filter((candidate) => candidate.field === question.field).length !== 1).map((question) => question.question_id)} />
            </div>
          )}
        </>
      )}
    </section>
  )
}
