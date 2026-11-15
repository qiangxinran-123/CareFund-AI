export type AiProcessStatus = 'pending' | 'active' | 'complete' | 'waiting_user' | 'blocked'

export interface AiProcessStep {
  id: string
  title: string
  detail: string
  status: AiProcessStatus
}

const statusCopy: Record<AiProcessStatus, { label: string; marker: string; markerStyle: string; cardStyle: string }> = {
  pending: {
    label: '等待处理', marker: '·', markerStyle: 'bg-slate-200 text-slate-700', cardStyle: 'border-slate-200 bg-slate-50/70',
  },
  active: {
    label: '正在处理', marker: '…', markerStyle: 'bg-blue-600 text-white', cardStyle: 'border-blue-300 bg-blue-50',
  },
  complete: {
    label: '已完成', marker: '✓', markerStyle: 'bg-emerald-600 text-white', cardStyle: 'border-emerald-200 bg-emerald-50/70',
  },
  waiting_user: {
    label: '等待用户', marker: '!', markerStyle: 'bg-amber-500 text-white', cardStyle: 'border-amber-300 bg-amber-50',
  },
  blocked: {
    label: '暂时阻断', marker: '×', markerStyle: 'bg-red-600 text-white', cardStyle: 'border-red-300 bg-red-50',
  },
}

interface Props {
  caption?: string
  steps: AiProcessStep[]
  title?: string
}

export function AiProcessTimeline({ caption, steps, title = 'AI 工作进度' }: Props) {
  const titleId = useId()
  return (
    <section aria-labelledby={titleId} className="mt-5 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      <div>
        <p className="text-xs font-medium uppercase tracking-wide text-blue-700">AI processing</p>
        <h3 className="mt-1 text-base font-semibold text-slate-900" id={titleId}>{title}</h3>
        {caption && <p className="mt-2 text-xs leading-5 text-slate-600">{caption}</p>}
      </div>
      <ol aria-label={title} className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {steps.map((step) => {
          const appearance = statusCopy[step.status]
          return (
            <li aria-current={step.status === 'active' ? 'step' : undefined} className={`min-w-0 rounded-lg border p-3 ${appearance.cardStyle}`} data-process-status={step.status} data-testid={`ai-process-${step.id}`} key={step.id}>
              <div className="flex items-start gap-3">
                <span aria-hidden="true" className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${appearance.markerStyle}`}>{appearance.marker}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <p className="text-sm font-semibold text-slate-900">{step.title}</p>
                    <span className="text-xs text-slate-500">{appearance.label}</span>
                  </div>
                  <p className="mt-1 text-xs leading-5 text-slate-600">{step.detail}</p>
                </div>
              </div>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
import { useId } from 'react'

