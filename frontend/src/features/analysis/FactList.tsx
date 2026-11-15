import type { AgentQuestion, Evidence, Fact, UploadedDocument, ValidationIssue } from '../../types/contracts'
import { factValueText, fieldLabel } from './analysisDisplay'
import { ValidationIssueCard } from './ValidationIssueList'

const statusCopy = {
  pending: { label: 'pending · 待核对', detail: '这项信息还需要您确认。', style: 'bg-amber-100 text-amber-900' },
  supported: { label: 'supported · 有材料支持', detail: '当前材料中有相关内容支持这项信息，不代表材料真实性已认证。', style: 'bg-emerald-100 text-emerald-900' },
  unsupported: { label: 'unsupported · 暂无材料支持', detail: '暂未找到支持这项信息的材料，不代表信息有误。', style: 'bg-slate-200 text-slate-800' },
  conflicting: { label: 'conflicting · 信息有出入', detail: '不同来源的信息有出入，请核对。', style: 'bg-red-100 text-red-900' },
} as const

const sourceLabels = {
  user_input: '用户输入',
  document: '上传材料',
  user_correction: '用户补充说明',
} as const

const extractionLabels = {
  ocr: 'OCR 识别',
  manual: '人工录入',
  structured_import: 'PDF 文本提取',
} as const

interface Props {
  documents: UploadedDocument[]
  evidence: Evidence[]
  facts: Fact[]
  issues?: ValidationIssue[]
  onAnswerQuestion?: (questionId: string, trigger: HTMLElement) => void
  questionForField?: (field: string) => AgentQuestion | undefined
}

export function FactList({ documents, evidence, facts, issues = [], onAnswerQuestion, questionForField }: Props) {
  const evidenceById = new Map(evidence.map((item) => [item.evidence_id, item]))
  const documentById = new Map(documents.map((item) => [item.document_id, item]))
  const issuesByFactId = new Map(facts.map((fact) => [fact.fact_id, issues.filter((issue) => issue.related_fact_ids.includes(fact.fact_id))]))
  const needsAttention = (fact: Fact) => fact.verification_status === 'pending'
    || fact.verification_status === 'conflicting'
    || (issuesByFactId.get(fact.fact_id)?.length ?? 0) > 0
  const attentionFacts = facts.filter(needsAttention)
  const otherFacts = facts.filter((fact) => !needsAttention(fact))

  function FactCard({ fact }: { fact: Fact }) {
    const status = statusCopy[fact.verification_status]
    const relatedIssues = issuesByFactId.get(fact.fact_id) ?? []
    return (
      <li className="min-w-0 rounded-xl border border-slate-200 bg-slate-50/60 p-4 sm:p-5" data-testid={`fact-${fact.fact_id}`} key={fact.fact_id}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <p className="break-words text-xs leading-5 text-slate-500">{fieldLabel(fact.field)}</p>
            <div className="mt-1 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-blue-100 px-2.5 py-1 font-medium text-blue-900">来源：{sourceLabels[fact.source_type]}</span>
              <span className={`rounded-full px-2.5 py-1 font-medium ${fact.user_confirmed ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'}`}>{fact.user_confirmed ? '用户已确认' : '等待用户确认'}</span>
            </div>
            <p className="mt-2 break-words whitespace-pre-wrap text-base font-medium leading-7 text-slate-900">{factValueText(fact.value)}</p>
          </div>
          <span className={`shrink-0 rounded-full px-3 py-1 text-xs font-medium leading-5 ${status.style}`}>{status.label}</span>
        </div>
        <p className="mt-3 text-xs leading-5 text-slate-600">{status.detail}</p>
        {relatedIssues.length > 0 && (
          <div className="mt-4 border-t border-slate-200 pt-4">
            <p className="text-xs font-semibold text-slate-700">需要处理的问题</p>
            <ul className="mt-2 space-y-2">{relatedIssues.map((issue) => <ValidationIssueCard issue={issue} key={issue.issue_id} onAnswerQuestion={onAnswerQuestion} question={questionForField?.(issue.field)} />)}</ul>
          </div>
        )}
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
                    <p className="mt-1 text-slate-500">提取方式：{extractionLabels[item.extraction_method]}</p>
                    <blockquote className="mt-2 break-words border-l-2 border-blue-300 pl-3 text-slate-700"><span className="font-medium">原始 OCR/文本片段：</span>{item.text_excerpt}</blockquote>
                  </li>
                )
              })}
            </ul>
          </div>
        )}
        {fact.evidence_ids.length === 0 && (
          <p className="mt-4 border-t border-slate-200 pt-4 text-xs leading-5 text-slate-600">
            {fact.source_type === 'document' ? '该材料事实没有可展示的 Evidence 引用，系统会将其作为需要处理的问题。' : '该事实来自用户输入，没有关联材料片段；是否允许继续由正式 Policy 决定。'}
          </p>
        )}
      </li>
    )
  }

  return (
    <section aria-labelledby="facts-title" className="mt-8">
      <div>
        <p className="text-sm font-medium text-blue-700">信息核对清单</p>
        <h3 className="mt-1 text-xl font-semibold text-slate-900" id="facts-title">请重点查看需要处理的信息</h3>
        <p className="mt-2 text-sm leading-6 text-slate-600">以下内容用于帮助您核对申请，不构成医疗诊断、材料真实性认证或平台审核结论。</p>
      </div>

      {facts.length === 0 ? (
        <p className="mt-4 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600">暂时还没有可展示的信息。您可以补充材料或信息后重新整理。</p>
      ) : (
        <>
          {attentionFacts.length > 0 && <div className="mt-5"><h4 className="text-sm font-semibold text-slate-800">需要处理的信息</h4><ul className="mt-3 grid gap-4 lg:grid-cols-2">{attentionFacts.map((fact) => <FactCard fact={fact} key={fact.fact_id} />)}</ul></div>}
          {otherFacts.length > 0 && <div className="mt-7"><h4 className="text-sm font-semibold text-slate-800">其他已整理的信息</h4><ul className="mt-3 grid gap-4 lg:grid-cols-2">{otherFacts.map((fact) => <FactCard fact={fact} key={fact.fact_id} />)}</ul></div>}
        </>
      )}
    </section>
  )
}
