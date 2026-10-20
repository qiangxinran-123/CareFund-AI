import type { AgentQuestion, ValidationIssue } from '../../types/contracts'
import { fieldLabel, issueGroup, issueStatus } from './analysisDisplay'

const severityCopy = {
  info: { label: '提醒', style: 'bg-blue-100 text-blue-900' },
  warning: { label: '需要关注', style: 'bg-amber-100 text-amber-900' },
  blocking: { label: '需要先处理', style: 'bg-red-100 text-red-900' },
} as const

interface IssueCardProps {
  issue: ValidationIssue
  onAnswerQuestion?: (questionId: string, trigger: HTMLElement) => void
  question?: AgentQuestion
}

export function ValidationIssueCard({ issue, onAnswerQuestion, question }: IssueCardProps) {
  const severity = severityCopy[issue.severity]
  const status = issueStatus(issue)
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5" data-testid={`validation-issue-${issue.issue_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${status.style}`}>{status.label}</span>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${severity.style}`}>{severity.label}</span>
        <span className="text-xs text-slate-500">涉及：{fieldLabel(issue.field)}</span>
      </div>
      <p className="mt-2 break-words text-sm leading-6 text-slate-700">{issue.message}</p>
      <p className="mt-2 text-xs leading-5 text-slate-600">{status.guidance}</p>
      {question && onAnswerQuestion && (
        <button className="button-secondary mt-3" onClick={(event) => onAnswerQuestion(question.question_id, event.currentTarget)} type="button">
          补充信息
        </button>
      )}
    </li>
  )
}

interface Props {
  issues: ValidationIssue[]
  onAnswerQuestion?: (questionId: string, trigger: HTMLElement) => void
  questionForField?: (field: string) => AgentQuestion | undefined
}

export function ValidationIssueList({ issues, onAnswerQuestion, questionForField }: Props) {
  const groups = ['需要补充', '需要核对', '其他提醒'] as const
  return (
    <section aria-labelledby="issues-title" className="mt-8 border-t border-slate-100 pt-7">
      <p className="text-sm font-medium text-blue-700">信息核对提示</p>
      <h3 className="mt-1 text-xl font-semibold text-slate-900" id="issues-title">需要您核对的信息</h3>
      {issues.length === 0 ? (
        <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">目前没有需要补充或核对的信息。这不代表平台审核通过。</p>
      ) : groups.map((name) => {
        const items = issues.filter((issue) => issueGroup(issue) === name)
        if (items.length === 0) return null
        return (
          <div className="mt-5" key={name}>
            <h4 className="text-sm font-semibold text-slate-800">{name}</h4>
            <ul className="mt-2 space-y-3">
              {items.map((issue) => <ValidationIssueCard issue={issue} key={issue.issue_id} onAnswerQuestion={onAnswerQuestion} question={questionForField?.(issue.field)} />)}
            </ul>
          </div>
        )
      })}
    </section>
  )
}
