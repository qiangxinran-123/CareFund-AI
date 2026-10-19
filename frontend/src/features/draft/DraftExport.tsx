import type { ExportResponse } from '../../types/contracts'

interface Props {
  blockedReason: string | null
  exporting: boolean
  mockMode: boolean
  onExport: () => void
  result: ExportResponse | null
}

function safeDownloadUrl(value: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value, window.location.origin)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}

export function DraftExport({ blockedReason, exporting, mockMode, onExport, result }: Props) {
  const downloadUrl = safeDownloadUrl(result?.download_url ?? null)
  return (
    <section aria-labelledby="draft-export-title" className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-4 sm:p-5">
      <h3 className="text-base font-semibold text-slate-900" id="draft-export-title">导出申请资料包</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">将按正式契约导出 JSON 申请资料包，不会自动生成 PDF 或 DOCX。</p>
      {blockedReason && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900" role="status">{blockedReason}</p>}
      <button className="button-primary mt-4 w-full sm:w-auto" disabled={exporting || Boolean(blockedReason)} onClick={onExport} type="button">
        {exporting ? '正在准备申请资料包…' : result ? '重新导出申请资料包' : '导出申请资料包'}
      </button>
      {result && (
        <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm leading-6 text-emerald-900" role="status">
          <p>{mockMode ? 'Mock 演示已返回导出结果，不代表真实文件已经生成。' : downloadUrl ? '申请资料包已准备好，请下载保存。' : '已收到导出结果，但服务端未提供下载地址。'}</p>
          {downloadUrl
            ? <a className="mt-2 inline-flex font-medium text-blue-700 underline underline-offset-4" href={downloadUrl} rel="noopener noreferrer">下载申请资料包</a>
            : <p className="mt-1">本次导出没有提供下载地址，请按服务端约定的其他通道获取资料包。</p>}
        </div>
      )}
    </section>
  )
}
