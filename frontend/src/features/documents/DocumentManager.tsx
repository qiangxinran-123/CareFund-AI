import { useCallback, useEffect, useRef, useState } from 'react'
import { documentApi as defaultApi, isMockMode as defaultMockMode } from '../../api'
import type { DocumentApi } from '../../api/documents'
import type { Application, UploadedDocument } from '../../types/contracts'
import { DocumentList } from './DocumentList'
import { DocumentUpload } from './DocumentUpload'

interface Props {
  api?: DocumentApi
  application: Application | null
  mockMode?: boolean
  onDocumentsChange?: (documents: UploadedDocument[]) => void
  onRefreshApplication?: () => Promise<void>
}

function describeListError(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return ''
  return error instanceof Error ? `无法读取文件列表：${error.message}` : '无法读取文件列表，请稍后重试。'
}

export function DocumentManager({
  api = defaultApi,
  application,
  mockMode = defaultMockMode,
  onDocumentsChange,
  onRefreshApplication,
}: Props) {
  const [documents, setDocuments] = useState<UploadedDocument[]>([])
  const [loading, setLoading] = useState(false)
  const [listError, setListError] = useState<string | null>(null)
  const [revisionReady, setRevisionReady] = useState(true)
  const [revisionError, setRevisionError] = useState<string | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const requestRef = useRef(0)
  const applicationId = application?.application_id

  const loadDocuments = useCallback(async () => {
    if (!applicationId) return
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const request = ++requestRef.current
    setLoading(true)
    setListError(null)
    try {
      const result = await api.list(applicationId, controller.signal)
      if (request === requestRef.current) {
        setDocuments(result)
        onDocumentsChange?.(result)
      }
    } catch (error) {
      if (request === requestRef.current && !controller.signal.aborted) {
        setListError(describeListError(error))
      }
    } finally {
      if (request === requestRef.current) setLoading(false)
    }
  }, [api, applicationId, onDocumentsChange])

  useEffect(() => {
    if (!applicationId) {
      setDocuments([])
      onDocumentsChange?.([])
      setListError(null)
      setLoading(false)
      return
    }
    setDocuments([])
    void loadDocuments()
    return () => controllerRef.current?.abort()
  }, [applicationId, loadDocuments, onDocumentsChange])

  async function handleUploaded(document: UploadedDocument) {
    setDocuments((current) => current.some((item) => item.document_id === document.document_id)
      ? current
      : [document, ...current])
    onDocumentsChange?.(documents.some((item) => item.document_id === document.document_id)
      ? documents
      : [document, ...documents])
    if (!onRefreshApplication) return
    setRevisionReady(false)
    setRevisionError(null)
    try {
      await onRefreshApplication()
      setRevisionReady(true)
    } catch {
      setRevisionError('文件已上传，但申请版本刷新失败。请重新加载页面后再上传其他文件。')
    }
  }

  return (
    <section aria-labelledby="documents-title" className="mt-8 rounded-2xl border border-blue-100 bg-white p-5 shadow-sm sm:p-8">
      <div className="flex flex-col gap-3 border-b border-slate-100 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-700">申请流程 · 材料上传</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900" id="documents-title" tabIndex={-1}>上传医疗材料</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">仅上传申请所需材料。上传和处理状态不代表真实性核验、医疗判断或审核通过。</p>
        </div>
        {mockMode && <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">Mock 模式 · 文件仅模拟上传</span>}
      </div>

      {!application ? (
        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <p className="text-sm text-amber-900">请先完成并保存申请，获得有效的 application_id 后才能上传材料。</p>
          <a className="mt-3 inline-flex text-sm font-medium text-blue-700 underline underline-offset-4" href="#application-form-title">返回填写申请信息</a>
        </div>
      ) : (
        <div className="mt-6">
          <p className="mb-5 text-xs text-slate-500">当前申请：{application.application_id} · 版本 {application.revision}</p>
          <DocumentUpload
            api={api}
            applicationId={application.application_id}
            disabled={!revisionReady}
            expectedRevision={application.revision}
            key={application.application_id}
            onUploaded={handleUploaded}
          />
          {revisionError && <p className="mt-3 text-sm text-red-700" role="alert">{revisionError}</p>}
          <DocumentList documents={documents} error={listError} loading={loading} onRefresh={() => void loadDocuments()} />
        </div>
      )}
    </section>
  )
}
