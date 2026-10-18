import type { UploadedDocument } from '../../types/contracts'
import { DocumentItem } from './DocumentItem'

interface Props {
  documents: UploadedDocument[]
  error: string | null
  loading: boolean
  onRefresh: () => void
}

export function DocumentList({ documents, error, loading, onRefresh }: Props) {
  return (
    <section aria-labelledby="document-list-title" className="mt-8 border-t border-slate-100 pt-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-base font-semibold text-slate-900" id="document-list-title">已上传材料</h3>
          <p className="mt-1 text-xs leading-5 text-slate-500">处理状态来自后端，不表示真实性核验或审核通过。</p>
        </div>
        <button className="button-secondary shrink-0" disabled={loading} onClick={onRefresh} type="button">
          {loading ? '刷新中…' : '刷新状态'}
        </button>
      </div>

      <div aria-live="polite" className="mt-4">
        {loading && documents.length === 0 && <p className="text-sm text-blue-700">正在读取文件列表…</p>}
        {error && <p className="text-sm text-red-700" role="alert">{error}</p>}
        {!loading && !error && documents.length === 0 && (
          <p className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">暂未上传医疗材料。</p>
        )}
        {documents.length > 0 && (
          <ul className="space-y-3">
            {documents.map((document) => <DocumentItem document={document} key={document.document_id} />)}
          </ul>
        )}
      </div>
    </section>
  )
}
