import { useEffect, useRef, useState } from 'react'
import { analysisApi as defaultApi, isMockMode as defaultMockMode } from '../../api'
import type { AnalysisApi } from '../../api/analysis'
import { ApiError } from '../../api/client'
import type { AnalysisJob, AnalysisResult, Answer, Application, UploadedDocument } from '../../types/contracts'
import { FactList } from './FactList'
import { FollowUpQuestions } from './FollowUpQuestions'
import { ValidationIssueList } from './ValidationIssueList'

type Phase = 'idle' | 'loading' | 'submitting' | 'queued' | 'running' | 'succeeded' | 'failed' | 'error' | 'stale'

interface Props {
  api?: AnalysisApi
  application: Application | null
  documents?: UploadedDocument[]
  maxPollAttempts?: number
  mockMode?: boolean
  onRefreshApplication?: () => Promise<void>
  onAnalysisChange?: (result: AnalysisResult | null) => void
  pollIntervalMs?: number
}

const phaseCopy: Record<Phase, string> = {
  idle: '尚未分析',
  loading: '正在读取分析结果…',
  submitting: '正在提交分析请求…',
  queued: '分析任务已进入等待队列。',
  running: '正在整理您提交的信息，请稍候。',
  succeeded: '分析已完成，请核对以下结果。',
  failed: '本次分析未能完成。',
  error: '分析请求遇到问题。',
  stale: '现有分析结果与当前申请版本不一致，已停止展示。',
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
    if (error.status === 409) return '申请内容或版本已经变化，请刷新申请后重新操作。'
    if (error.status === 422) return `当前信息暂不满足分析条件：${error.message}`
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
  pollIntervalMs = 2000,
}: Props) {
  const [phase, setPhase] = useState<Phase>('idle')
  const [job, setJob] = useState<AnalysisJob | null>(null)
  const [result, setResult] = useState<AnalysisResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
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
          setError('任务返回的申请或版本与当前操作不一致，已停止展示。')
          setPhase('stale')
          return
        }
        setPhase(current.status === 'queued' ? 'queued' : current.status === 'running' ? 'running' : current.status === 'failed' ? 'failed' : 'loading')
        if (current.status === 'failed') {
          setError(current.error?.message || '分析任务失败，请安全重试。')
          return
        }
        if (current.status === 'succeeded') {
          const latest = await api.getLatest(applicationId!, controller.signal)
          if (latest.application_id !== applicationId || latest.application_revision !== expectedRevision) {
            setResult(null)
            setError('分析结果与本次申请版本不一致，已停止展示。')
            setPhase('stale')
            return
          }
          if (refreshAfter && onRefreshApplication) {
            try {
              await onRefreshApplication()
            } catch {
              setResult(null)
              setError('补充信息已提交，但申请版本刷新失败。请重新加载页面后查看最新结果。')
              setPhase('stale')
              return
            }
          }
          setResult(latest)
          setJob(current)
          setPhase('succeeded')
          setNotice(refreshAfter ? '补充信息已提交，分析结果已更新。' : null)
          intentRef.current = null
          return
        }
        if (attempt === maxPollAttempts) {
          setError('分析等待时间较长，已暂停自动查询。您可以继续查询同一任务。')
          setPhase('error')
          return
        }
        await delay(pollIntervalMs, controller.signal)
        current = await api.getJob(applicationId!, current.job_id, controller.signal)
        setJob(current)
      }
    } catch (caught) {
      if (request !== requestRef.current || isAbort(caught)) return
      setError(`查询分析任务失败：${describeError(caught)}`)
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
    setNotice('补充信息正在提交，提交成功后将自动重新分析。')
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
          <p className="text-sm font-medium text-blue-700">申请流程 · AI 分析与补充</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900" id="analysis-title" tabIndex={-1}>核对申请信息</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">系统将根据您填写的信息和已上传的材料，协助整理申请信息并提示需要核对的内容。</p>
        </div>
        {mockMode && <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">Mock 模式 · 结果为虚构演示数据</span>}
      </div>

      {!application ? (
        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">请先完成并保存申请，获得有效的 application_id 后才能开始分析。</p>
          <a className="mt-3 inline-flex text-sm font-medium text-blue-700 underline underline-offset-4" href="#application-form-title">返回填写申请信息</a>
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">当前申请</p><p className="mt-1 break-all text-sm font-medium text-slate-800">{application.application_id}</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">申请版本</p><p className="mt-1 text-sm font-medium text-slate-800">版本 {application.revision}</p></div>
            <div className="rounded-xl bg-slate-50 p-4"><p className="text-xs text-slate-500">已上传材料</p><p className="mt-1 text-sm font-medium text-slate-800">{documents.length} 份</p></div>
          </div>
          {documents.length === 0 && <p className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-900">当前尚未上传材料。您仍可尝试分析用户自述，但材料核查能力会受限；是否满足分析条件以服务端响应为准。</p>}

          <div className="mt-5 flex flex-col gap-3 rounded-xl border border-blue-100 bg-blue-50/60 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div aria-live="polite">
              <p className="text-xs font-medium text-blue-700">分析状态</p>
              <p className="mt-1 text-sm text-slate-700">{phaseCopy[phase]}</p>
              {notice && <p className="mt-1 text-xs text-emerald-800" role="status">{notice}</p>}
              {error && <p className="mt-2 text-sm text-red-700" role="alert">{error}</p>}
            </div>
            <div className="flex shrink-0 flex-col gap-2 sm:flex-row">
              {phase === 'error' && job && <button className="button-secondary" onClick={resumePolling} type="button">继续查询任务</button>}
              <button className="button-primary" disabled={busy} onClick={() => void startAnalysis()} type="button">
                {busy ? '分析处理中…' : result ? '重新分析' : phase === 'error' && !job ? '安全重试' : '开始分析'}
              </button>
            </div>
          </div>

          {result && (phase === 'succeeded' || phase === 'submitting') && (
            <div>
              <div className="mt-7 rounded-xl border border-slate-200 p-4">
                <p className="text-sm font-semibold text-slate-900">分析结果摘要</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">共整理 {result.facts.length} 项事实，发现 {result.validation.issues.length} 项需要关注的内容，并提出 {result.questions.length} 个补充问题。</p>
              </div>
              <FactList documents={documents} evidence={result.evidence} facts={result.facts} />
              <ValidationIssueList issues={result.validation.issues} />
              <FollowUpQuestions onSubmit={submitAnswers} questions={result.questions} />
            </div>
          )}
        </>
      )}
    </section>
  )
}
