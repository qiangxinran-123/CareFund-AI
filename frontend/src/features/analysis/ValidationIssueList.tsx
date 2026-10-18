import type { ValidationIssue } from '../../types/contracts'
import { fieldLabel } from './analysisDisplay'

const severityCopy = {
  info: { label: '提醒', style: 'bg-blue-100 text-blue-900' },
  warning: { label: '需要关注', style: 'bg-amber-100 text-amber-900' },
  blocking: { label: '影响后续确认或导出', style: 'bg-red-100 text-red-900' },
} as const

function group(issue: ValidationIssue): '需要补充' | '需要核对' | '其他提醒' {
  if (issue.type === 'missing' || issue.type === 'unsupported') return '需要补充'
  if (issue.type === 'conflict' || issue.type === 'inconsistent_amount' || issue.type === 'inconsistent_date') return '需要核对'
  return '其他提醒'
}

export function ValidationIssueList({ issues }: { issues: ValidationIssue[] }) {
  const groups = ['需要补充', '需要核对', '其他提醒'] as const
  return (
    <section aria-labelledby="issues-title" className="mt-8 border-t border-slate-100 pt-7">
      <p className="text-sm font-medium text-blue-700">缺失与冲突提示</p>
      <h3 className="mt-1 text-xl font-semibold text-slate-900" id="issues-title">需要您关注的内容</h3>
      {issues.length === 0 ? (
        <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">当前分析没有返回需要补充或核对的问题。这不代表平台审核通过。</p>
      ) : groups.map((name) => {
        const items = issues.filter((issue) => group(issue) === name)
        if (items.length === 0) return null
        return (
          <div className="mt-5" key={name}>
            <h4 className="text-sm font-semibold text-slate-800">{name}</h4>
            <ul className="mt-2 space-y-3">
              {items.map((issue) => {
                const severity = severityCopy[issue.severity]
                return (
                  <li className="rounded-xl border border-slate-200 p-4" key={issue.issue_id}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${severity.style}`}>{severity.label}</span>
                      <span className="text-xs text-slate-500">涉及：{fieldLabel(issue.field)}</span>
                    </div>
                    <p className="mt-2 text-sm leading-6 text-slate-700">{issue.message}</p>
                  </li>
                )
              })}
            </ul>
          </div>
        )
      })}
    </section>
  )
}
