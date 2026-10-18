import type { Evidence, Fact, UploadedDocument } from '../../types/contracts'
import { factValueText, fieldLabel } from './analysisDisplay'

const statusCopy = {
  pending: { label: '还需要确认', detail: '这项信息还需要您确认。', style: 'bg-amber-100 text-amber-900' },
  supported: { label: '材料内容支持', detail: '当前材料中有相关内容支持这项信息，不代表材料真实性已认证。', style: 'bg-emerald-100 text-emerald-900' },
  unsupported: { label: '暂无材料支持', detail: '暂未找到支持这项信息的材料，不代表信息有误。', style: 'bg-slate-200 text-slate-800' },
  conflicting: { label: '信息有出入', detail: '不同来源的信息有出入，请核对。', style: 'bg-red-100 text-red-900' },
} as const

const sourceLabels = {
  user_input: '用户填写/自述',
  document: '材料内容',
  user_correction: '用户补充说明',
} as const

interface Props {
  documents: UploadedDocument[]
  evidence: Evidence[]
  facts: Fact[]
}

export function FactList({ documents, evidence, facts }: Props) {
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]))
  const documentById = new Map(documents.map((item) => [item.document_id, item]))

  return (
    <section aria-labelledby="facts-title" className="mt-8">
      <div>
        <p className="text-sm font-medium text-blue-700">信息与材料依据</p>
        <h3 className="mt-1 text-xl font-semibold text-slate-900" id="facts-title">请核对以下信息</h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">以下内容用于帮助您核对申请，不构成医疗诊断、材料真实性认证或平台审核结论。</p>
      </div>

      {facts.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600">暂时还没有可展示的信息。您可以补充材料或信息后重新整理。</p>
      ) : (
        <ul className="mt-5 grid gap-4 lg:grid-cols-2">
          {facts.map((fact) => {
            const status = statusCopy[fact.verification_status]
            return (
              <li className="min-w-0 rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5" key={fact.fact_id}>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="break-words text-xs leading-5 text-slate-500">{fieldLabel(fact.field)} · 来源：{sourceLabels[fact.source_type]}</p>
                    <p className="mt-2 break-words whitespace-pre-wrap text-base font-medium leading-7 text-slate-900">{factValueText(fact.value)}</p>
                  </div>
                  <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium leading-5 ${status.style}`}>{status.label}</span>
                </div>
                <p className="mt-3 text-xs leading-5 text-slate-600">{status.detail}</p>
                {fact.evidence_ids.length > 0 && (
                  <div className="mt-4 border-t border-slate-200 pt-4">
                    <p className="text-xs font-semibold text-slate-700">相关材料内容</p>
                    <ul className="mt-2 space-y-2">
                      {fact.evidence_ids.map((evidenceId) => {
                        const item = evidenceById.get(evidenceId)
                        if (!item) return <li className="text-xs text-amber-800" key={evidenceId}>证据来源暂不可用</li>
                        const filename = documentById.get(item.document_id)?.filename ?? '材料来源暂不可用'
                        return (
                          <li className="rounded-lg bg-white p-3 text-xs leading-5 text-slate-600" key={evidenceId}>
                            <p className="break-words font-medium text-slate-800">{filename}{item.page === null ? '' : ` · 第 ${item.page} 页`}</p>
                            <p className="mt-1 break-words">相关内容：{item.text_excerpt}</p>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
