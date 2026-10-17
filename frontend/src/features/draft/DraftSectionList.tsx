import type { DraftSection, Evidence, Fact, UploadedDocument } from '../../types/contracts'
import { factValueText, fieldLabel } from '../analysis/analysisDisplay'

interface Props {
  documents: UploadedDocument[]
  evidence: Evidence[]
  facts: Fact[]
  sections: DraftSection[]
}

const sourceLabel = {
  user_input: '用户填写或自述',
  user_correction: '用户补充确认',
  document: '上传材料提取',
} as const

const verificationLabel = {
  pending: '待进一步核对',
  supported: '有材料内容支持（不代表真实性认证）',
  unsupported: '现有材料尚未支持',
  conflicting: '不同来源存在冲突',
} as const

export function missingDraftFactIds(sections: DraftSection[], facts: Fact[]): string[] {
  const available = new Set(facts.map((fact) => fact.fact_id))
  return [...new Set(sections.flatMap((section) => section.fact_ids).filter((id) => !available.has(id)))]
}

export function DraftSectionList({ documents, evidence, facts, sections }: Props) {
  const factsById = new Map(facts.map((fact) => [fact.fact_id, fact]))
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]))
  const documentsById = new Map(documents.map((item) => [item.document_id, item]))

  if (sections.length === 0) {
    return <p className="mt-5 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600">草稿暂时没有可显示的章节，请安全重试或联系服务端负责人。</p>
  }

  return (
    <div className="mt-6 space-y-5">
      {sections.map((section, index) => (
        <article aria-labelledby={`draft-section-${section.section_id}`} className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6" key={section.section_id}>
          <p className="text-xs font-medium text-blue-700">第 {index + 1} 节</p>
          <h3 className="mt-1 text-lg font-semibold text-slate-900" id={`draft-section-${section.section_id}`}>{section.title}</h3>
          <p className="mt-4 whitespace-pre-wrap text-[15px] leading-8 text-slate-800">{section.content}</p>
          <div className="mt-5 border-t border-slate-100 pt-4">
            <p className="text-xs font-semibold text-slate-700">本节关联的信息来源</p>
            <ul className="mt-3 space-y-3">
              {section.fact_ids.map((factId) => {
                const fact = factsById.get(factId)
                if (!fact) {
                  return <li className="rounded-lg bg-amber-50 p-3 text-xs leading-5 text-amber-900" key={factId}>关联事实暂不可用（{factId}）。请勿据此认定内容已经证实。</li>
                }
                const relatedEvidence = fact.evidence_ids.map((id) => evidenceById.get(id)).filter((item): item is Evidence => Boolean(item))
                return (
                  <li className="rounded-lg bg-slate-50 p-3 text-xs leading-5 text-slate-700" key={fact.fact_id}>
                    <p><span className="font-medium text-slate-900">{fieldLabel(fact.field)}：</span>{factValueText(fact.value)}</p>
                    <p className="mt-1">来源：{sourceLabel[fact.source_type]} · {verificationLabel[fact.verification_status]}</p>
                    {fact.source_type === 'document' && fact.evidence_ids.length > 0 && relatedEvidence.length === 0 && (
                      <p className="mt-1 text-amber-800">关联证据暂不可用，不能据此认定材料已核实。</p>
                    )}
                    {relatedEvidence.map((item) => (
                      <p className="mt-1 text-slate-600" key={item.evidence_id}>
                        材料：{documentsById.get(item.document_id)?.filename ?? '材料名称暂不可用'}{item.page === null ? '' : ` · 第 ${item.page} 页`} · 摘要：{item.text_excerpt}
                      </p>
                    ))}
                  </li>
                )
              })}
            </ul>
          </div>
        </article>
      ))}
    </div>
  )
}
