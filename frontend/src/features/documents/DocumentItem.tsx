import type { DocumentProcessingStatus, UploadedDocument } from '../../types/contracts'
import { formatFileSize } from './documentValidation'

const statusLabels: Record<DocumentProcessingStatus, string> = {
  uploaded: '已上传，等待处理',
  processing: '处理中',
  processed: '处理完成',
  failed: '处理失败',
}

const statusClasses: Record<DocumentProcessingStatus, string> = {
  uploaded: 'bg-blue-50 text-blue-800',
  processing: 'bg-amber-50 text-amber-800',
  processed: 'bg-emerald-50 text-emerald-800',
  failed: 'bg-red-50 text-red-800',
}

function formatUploadTime(value: string): string {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN')
}

export function DocumentItem({ document }: { document: UploadedDocument }) {
  return (
    <li className="rounded-xl border border-slate-200 p-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="break-all text-sm font-medium text-slate-900">{document.filename}</p>
          <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
            <div><dt className="sr-only">文件类型</dt><dd>{document.media_type}</dd></div>
            <div><dt className="sr-only">文件大小</dt><dd>{formatFileSize(document.size_bytes)}</dd></div>
            <div><dt className="sr-only">上传时间</dt><dd>{formatUploadTime(document.uploaded_at)}</dd></div>
          </dl>
        </div>
        <span className={`w-fit shrink-0 rounded-full px-3 py-1 text-xs font-medium ${statusClasses[document.processing_status]}`}>
          {statusLabels[document.processing_status]}
        </span>
      </div>
      {document.processing_status === 'failed' && (
        <p className="mt-3 text-xs leading-5 text-red-700">文件已上传，但后续处理失败；这不影响上传记录，也不代表材料审核结果。</p>
      )}
    </li>
  )
}
