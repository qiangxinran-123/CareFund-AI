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
    <section aria-labelledby="draft-export-title" className="mt-6 rounded-xl border border-slate-200 bg-slate-50 p-5">
      <h3 className="text-base font-semibold text-slate-900" id="draft-export-title">导出申请材料</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">正式契约仅支持 JSON 申请包。这里不会自行生成 PDF 或 DOCX。</p>
      {blockedReason && <p className="mt-3 text-sm text-amber-900" role="status">{blockedReason}</p>}
      <button className="button-primary mt-4 w-full sm:w-auto" disabled={exporting || Boolean(blockedReason)} onClick={onExport} type="button">
        {exporting ? '正在准备导出…' : result ? '再次导出 JSON 申请包' : '导出 JSON 申请包'}
      </button>
      {result && (
        <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm leading-6 text-emerald-900" role="status">
          <p>{mockMode ? 'Mock 导出请求已模拟成功，不代表真实文件已经生成。' : '导出请求已成功完成。'}</p>
          {downloadUrl
            ? <a className="mt-2 inline-flex font-medium text-blue-700 underline underline-offset-4" href={downloadUrl} rel="noopener noreferrer">下载 JSON 申请包</a>
            : <p className="mt-1">服务端本次未提供下载地址；请按服务端约定的其他通道获取申请包。</p>}
        </div>
      )}
    </section>
  )
}
