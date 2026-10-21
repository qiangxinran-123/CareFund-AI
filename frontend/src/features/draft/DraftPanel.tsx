import { useEffect, useRef, useState } from 'react'
import { draftApi as defaultApi, isMockMode as defaultMockMode } from '../../api'
import type { DraftApi } from '../../api/draft'
import { ApiError } from '../../api/client'
import type { AnalysisResult, Application, Draft, ExportResponse, UploadedDocument } from '../../types/contracts'
import type { DraftPhase, DraftStepState } from '../workflow/workflowStatus'
import { DraftConfirmation } from './DraftConfirmation'
import { DraftExport, safeDownloadUrl } from './DraftExport'
import { DraftCompletion } from './DraftCompletion'
import { DraftSectionList, missingDraftFactIds } from './DraftSectionList'

interface Props {
  analysis: AnalysisResult | null
  api?: DraftApi
  application: Application | null
  documents?: UploadedDocument[]
  mockMode?: boolean
  onStateChange?: (state: DraftStepState) => void
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function describeError(error: unknown, action: '读取' | '生成' | '确认' | '导出'): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return '申请信息或草稿已经更新，请刷新后重新生成申请初稿。'
    if (error.status === 422) return `${action}被服务端阻止：${error.message}`
    return error.message
  }
  return error instanceof Error ? error.message : `${action}失败，请稍后重试。`
}

export function DraftPanel({ analysis, api = defaultApi, application, documents = [], mockMode = defaultMockMode, onStateChange }: Props) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [exportResult, setExportResult] = useState<ExportResponse | null>(null)
  const [checked, setChecked] = useState(false)
  const [phase, setPhase] = useState<DraftPhase>('idle')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [showCompletion, setShowCompletion] = useState(false)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef(0)
  const titleRef = useRef<HTMLHeadingElement | null>(null)
  const applicationId = application?.application_id
  const applicationRevision = application?.revision
  const analysisCurrent = Boolean(analysis && application && analysis.application_id === application.application_id && analysis.application_revision === application.revision)

  useEffect(() => {
    onStateChange?.({ draft, exportResult, hasError: Boolean(error), phase })
  }, [draft, error, exportResult, onStateChange, phase])

  useEffect(() => {
    controllerRef.current?.abort()
    const request = ++requestRef.current
    setDraft(null)
    setExportResult(null)
    setChecked(false)
    setError(null)
    setNotice(null)
    setShowCompletion(false)
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
        if (latest.application_id !== applicationId) {
          setError('服务端返回了其他申请的草稿，已停止展示。')
          return
        }
        setDraft(latest)
      })
      .catch((caught: unknown) => {
        if (request !== requestRef.current || isAbort(caught)) return
        if (!(caught instanceof ApiError && caught.status === 404)) setError(describeError(caught, '读取'))
      })
      .finally(() => {
        if (request === requestRef.current) setPhase('idle')
      })
    return () => controller.abort()
  }, [api, applicationId, applicationRevision])

  const stale = Boolean(draft && application && (draft.status === 'stale' || draft.application_revision !== application.revision))
  const blockingIssues = analysisCurrent ? analysis!.validation.issues.filter((issue) => issue.severity === 'blocking') : []
  const missingFacts = draft && analysisCurrent ? missingDraftFactIds(draft.sections, analysis!.facts) : []
  const canFinalize = analysisCurrent && analysis!.validation.can_finalize && blockingIssues.length === 0
  const generateBlocked = !analysisCurrent ? '请先完成当前版本的信息整理和核对；旧版本结果不能用于生成新草稿。'
    : !analysis!.validation.can_finalize ? blockingIssues.length > 0
      ? `当前有 ${blockingIssues.length} 项需要先处理的信息，暂时不能生成草稿。`
      : '当前校验尚未允许生成草稿，请先完成需要处理的信息。'
    : null
  const downloadUrl = safeDownloadUrl(exportResult?.download_url ?? null)
  const completionVisible = Boolean(
    showCompletion
    && !mockMode
    && downloadUrl
    && draft
    && application
    && !stale
    && draft.status === 'confirmed'
    && draft.application_id === application.application_id
    && draft.application_revision === application.revision
    && exportResult?.application_id === application.application_id
    && exportResult.draft_id === draft.draft_id,
  )

  useEffect(() => {
    if (!completionVisible) return
    titleRef.current?.focus({ preventScroll: true })
    titleRef.current?.closest('section')?.scrollIntoView?.({ block: 'start' })
  }, [completionVisible])

  async function runAction(action: 'generate' | 'confirm' | 'export') {
    if (!application || phase !== 'idle') return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const request = ++requestRef.current
    setPhase(action === 'generate' ? 'generating' : action === 'confirm' ? 'confirming' : 'exporting')
    setError(null)
    setNotice(null)
    if (action !== 'export') {
      setExportResult(null)
      setShowCompletion(false)
    }
    try {
      if (action === 'generate') {
        const generated = await api.generate(application.application_id, { expected_revision: application.revision }, controller.signal)
        if (generated.application_id !== application.application_id || generated.application_revision !== application.revision) {
          throw new ApiError('新草稿与当前申请版本不一致。', 'invalid_response')
        }
        if (request !== requestRef.current) return
        setDraft(generated)
        setChecked(false)
        setNotice('申请初稿已生成，请逐节核对内容和来源。')
      } else if (action === 'confirm' && draft) {
        const confirmed = await api.confirm(application.application_id, {
          draft_id: draft.draft_id,
          draft_revision: draft.draft_revision,
          expected_application_revision: application.revision,
        }, controller.signal)
        if (confirmed.application_id !== application.application_id || confirmed.application_revision !== application.revision || confirmed.draft_id !== draft.draft_id) {
          throw new ApiError('确认结果与当前草稿不一致。', 'invalid_response')
        }
        if (request !== requestRef.current) return
        setDraft(confirmed)
        setNotice('草稿已确认。此确认不代表医疗真实性认证或平台审核通过。')
      } else if (action === 'export' && draft) {
        const result = await api.exportApplication(application.application_id, {
          draft_id: draft.draft_id,
          draft_revision: draft.draft_revision,
          expected_application_revision: application.revision,
          format: 'json',
        }, controller.signal)
        if (result.application_id !== application.application_id || result.draft_id !== draft.draft_id) {
          throw new ApiError('导出结果与当前草稿不一致。', 'invalid_response')
        }
        if (request !== requestRef.current) return
        setExportResult(result)
        if (!mockMode && safeDownloadUrl(result.download_url)) {
          setShowCompletion(true)
          setNotice(null)
        } else {
          setNotice('已收到导出结果，请按下方提示获取申请资料包。')
        }
      }
    } catch (caught) {
      if (request === requestRef.current && !isAbort(caught)) {
        setError(describeError(caught, action === 'generate' ? '生成' : action === 'confirm' ? '确认' : '导出'))
      }
    } finally {
      if (request === requestRef.current) setPhase('idle')
    }
  }

  const confirmBlocked = !draft ? '请先生成申请初稿。'
    : stale ? '申请信息已更新，之前的草稿需要重新生成。'
      : !analysisCurrent ? '当前申请没有可用于核对的有效整理结果，请先完成资料整理。'
        : missingFacts.length > 0 ? `有 ${missingFacts.length} 项关联信息暂不可用，暂不能确认草稿。`
          : !canFinalize ? `还有 ${blockingIssues.length || '未解决的'} 项需要先处理的信息，暂时不能确认草稿。`
            : null
  const exportBlocked = !draft ? '请先生成并确认申请初稿。'
    : stale ? '申请信息已更新，之前的草稿需要重新生成。'
      : draft.status !== 'confirmed' ? '草稿尚未确认，暂不能导出。'
        : !canFinalize ? '当前仍有需要先处理的信息，暂不能导出。'
          : missingFacts.length > 0 ? '草稿有暂时不可用的关联信息，暂不能导出。'
            : null

  return (
    <section aria-labelledby="draft-title" className="mt-8 rounded-2xl border border-blue-100 bg-white p-5 shadow-sm sm:p-8">
      <div className="flex flex-col gap-4 border-b border-slate-100 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-700">申请流程 · 确认与导出</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900" id="draft-title" ref={titleRef} tabIndex={-1}>{completionVisible ? '申请资料已整理完成' : '确认并导出申请'}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">{completionVisible ? '资料包已准备完成，请下载保存后按目标众筹平台的要求自行提交。' : '请仔细核对申请初稿中的病情、费用和其他重要信息。确认无误后再导出。'}</p>
        </div>
        {mockMode && <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">Mock 演示模式 · 草稿和导出结果为虚构示例</span>}
      </div>

      {!application ? (
        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">请先填写并保存求助信息，再生成申请初稿。</div>
      ) : completionVisible && downloadUrl ? (
        <DraftCompletion downloadUrl={downloadUrl} onViewDraft={() => setShowCompletion(false)} />
      ) : (
        <>
          <div className="mt-6 flex flex-col gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0">
              <p className="text-xs text-slate-500">当前申请版本：{application.revision}</p>
              <p className="mt-1 text-sm font-medium text-slate-800">
                {phase === 'loading' ? '正在查看已有草稿…' : draft ? `草稿版本 ${draft.draft_revision} · ${draft.status === 'confirmed' ? '已由您确认' : stale ? '需要重新生成' : '已生成，等待您核对'}` : '尚未生成申请初稿'}
              </p>
            </div>
            <button className="button-primary w-full shrink-0 sm:w-auto" disabled={phase !== 'idle' || Boolean(generateBlocked)} onClick={() => void runAction('generate')} type="button">
              {phase === 'generating' ? '正在生成申请初稿…' : draft ? '重新生成申请初稿' : '生成申请初稿'}
            </button>
          </div>
          {generateBlocked && <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">{generateBlocked}</p>}
          {stale && <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">申请信息已更新（当前版本 {application.revision}），之前的草稿需要重新生成。</p>}
          <div aria-live="polite" className="mt-3 min-h-6">
            {notice && <p className="text-sm text-emerald-800" role="status">{notice}</p>}
            {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
          </div>

          {draft && (
            <>
              <DraftSectionList documents={documents} evidence={analysisCurrent ? analysis!.evidence : []} facts={analysisCurrent ? analysis!.facts : []} sections={draft.sections} />
              <DraftConfirmation
                blockedReason={confirmBlocked}
                checked={checked}
                confirmed={draft.status === 'confirmed' && !stale}
                confirming={phase === 'confirming'}
                onCheckedChange={setChecked}
                onConfirm={() => void runAction('confirm')}
              />
              <DraftExport blockedReason={exportBlocked} exporting={phase === 'exporting'} mockMode={mockMode} onExport={() => void runAction('export')} result={exportResult} />
            </>
          )}
        </>
      )}
    </section>
  )
}
