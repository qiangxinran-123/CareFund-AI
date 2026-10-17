import { useEffect, useRef, useState } from 'react'
import { draftApi as defaultApi, isMockMode as defaultMockMode } from '../../api'
import type { DraftApi } from '../../api/draft'
import { ApiError } from '../../api/client'
import type { AnalysisResult, Application, Draft, ExportResponse, UploadedDocument } from '../../types/contracts'
import { DraftConfirmation } from './DraftConfirmation'
import { DraftExport } from './DraftExport'
import { DraftSectionList, missingDraftFactIds } from './DraftSectionList'

interface Props {
  analysis: AnalysisResult | null
  api?: DraftApi
  application: Application | null
  documents?: UploadedDocument[]
  mockMode?: boolean
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError'
}

function describeError(error: unknown, action: '读取' | '生成' | '确认' | '导出'): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return '申请或草稿版本已经变化，请刷新申请状态并重新生成草稿。'
    if (error.status === 422) return `${action}被服务端阻止：${error.message}`
    return error.message
  }
  return error instanceof Error ? error.message : `${action}失败，请稍后重试。`
}

export function DraftPanel({ analysis, api = defaultApi, application, documents = [], mockMode = defaultMockMode }: Props) {
  const [draft, setDraft] = useState<Draft | null>(null)
  const [exportResult, setExportResult] = useState<ExportResponse | null>(null)
  const [checked, setChecked] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'loading' | 'generating' | 'confirming' | 'exporting'>('idle')
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef(0)
  const applicationId = application?.application_id
  const applicationRevision = application?.revision
  const analysisCurrent = Boolean(analysis && application && analysis.application_id === application.application_id && analysis.application_revision === application.revision)

  useEffect(() => {
    controllerRef.current?.abort()
    const request = ++requestRef.current
    setDraft(null)
    setExportResult(null)
    setChecked(false)
    setError(null)
    setNotice(null)
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

  async function runAction(action: 'generate' | 'confirm' | 'export') {
    if (!application || phase !== 'idle') return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const request = ++requestRef.current
    setPhase(action === 'generate' ? 'generating' : action === 'confirm' ? 'confirming' : 'exporting')
    setError(null)
    setNotice(null)
    if (action !== 'export') setExportResult(null)
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
        setNotice('草稿已由您确认。此状态不代表平台审核通过。')
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
        setNotice('导出请求已完成。')
      }
    } catch (caught) {
      if (request === requestRef.current && !isAbort(caught)) {
        setError(describeError(caught, action === 'generate' ? '生成' : action === 'confirm' ? '确认' : '导出'))
      }
    } finally {
      if (request === requestRef.current) setPhase('idle')
    }
  }

  const confirmBlocked = !draft ? '请先生成草稿。'
    : stale ? '草稿已过期，需要基于当前申请版本重新生成。'
      : !analysisCurrent ? '当前申请没有可用于核对的有效分析结果，请先完成分析。'
        : missingFacts.length > 0 ? `有 ${missingFacts.length} 项关联事实暂不可用，暂不能提供确认操作。`
          : !canFinalize ? `仍有 ${blockingIssues.length || '未解决的'} 项校验问题，服务端当前不允许最终确认。`
            : null
  const exportBlocked = !draft ? '请先生成并确认草稿。'
    : stale ? '草稿已过期，不能导出。'
      : draft.status !== 'confirmed' ? '草稿尚未确认，不能导出。'
        : !canFinalize ? '当前校验结果不允许导出。'
          : missingFacts.length > 0 ? '草稿存在不可用的关联事实，不能导出。'
            : null

  return (
    <section aria-labelledby="draft-title" className="mt-8 rounded-2xl border border-blue-100 bg-white p-5 shadow-sm sm:p-8">
      <div className="flex flex-col gap-4 border-b border-slate-100 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-700">申请流程 · 草稿确认</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900" id="draft-title" tabIndex={-1}>预览并确认申请草稿</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">查看 AI 整理的章节、核对真实信息来源，确认后按正式契约导出 JSON 申请包。</p>
        </div>
        {mockMode && <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">Mock 模式 · 草稿为虚构演示数据</span>}
      </div>

      {!application ? (
        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">请先保存申请并取得有效的 application_id。</div>
      ) : (
        <>
          <div className="mt-6 flex flex-col gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs text-slate-500">当前申请版本：{application.revision}</p>
              <p className="mt-1 text-sm font-medium text-slate-800">
                {phase === 'loading' ? '正在读取草稿…' : draft ? `草稿版本 ${draft.draft_revision} · ${draft.status === 'confirmed' ? '用户已确认' : stale ? '已过期' : '已生成，待确认'}` : '尚未生成草稿'}
              </p>
            </div>
            <button className="button-primary shrink-0" disabled={phase !== 'idle' || !analysisCurrent} onClick={() => void runAction('generate')} type="button">
              {phase === 'generating' ? '正在生成草稿…' : draft ? '重新生成草稿' : '生成申请初稿'}
            </button>
          </div>
          {!analysisCurrent && <p className="mt-3 text-sm text-amber-900">请先完成当前版本的 AI 分析；旧版本分析不会用于生成新草稿。</p>}
          {blockingIssues.length > 0 && <p className="mt-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">当前有 {blockingIssues.length} 项阻断性问题。仍可请求服务端生成草稿，但确认和导出将保持受限。</p>}
          {stale && <p className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">草稿对应申请版本 {draft?.application_revision}，当前为版本 {application.revision}。请重新分析并生成草稿。</p>}
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
