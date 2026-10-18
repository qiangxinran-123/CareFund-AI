import { workflowSteps, type WorkflowStepId } from './workflowSteps'
import type { WorkflowStepState } from './workflowStatus'

interface Props {
  currentStep: WorkflowStepId
  onStepSelect: (step: WorkflowStepId) => void
  stepStates: Record<WorkflowStepId, WorkflowStepState>
  visitedSteps: ReadonlySet<WorkflowStepId>
}

const statusCopy = {
  completed: '已完成',
  needs_attention: '需要补充',
  pending: '尚未开始',
} as const

export function WorkflowStepper({ currentStep, onStepSelect, stepStates, visitedSteps }: Props) {
  return (
    <nav aria-label="申请向导进度" className="mb-8 sm:mb-10">
      <ol className="grid grid-cols-2 gap-2 sm:grid-cols-4 sm:gap-3">
        {workflowSteps.map((step, index) => {
          const current = step.id === currentStep
          const available = current || visitedSteps.has(step.id)
          const state = stepStates[step.id]
          const statusLabel = state.status === 'pending' && (state.label.includes('处理中') || state.label.startsWith('正在'))
            ? '进行中'
            : statusCopy[state.status]
          return (
            <li key={step.id}>
              <button
                aria-current={current ? 'step' : undefined}
                className={`h-full w-full min-w-0 rounded-xl border px-3 py-3 text-left shadow-sm transition focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-blue-600 sm:px-4 sm:py-4 ${
                  current
                    ? 'border-blue-600 bg-blue-50'
                    : available
                      ? 'border-slate-200 bg-white hover:border-blue-300'
                      : 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-400'
                }`}
                disabled={!available}
                onClick={() => onStepSelect(step.id)}
                type="button"
              >
                <span className={`text-xs font-semibold ${current ? 'text-blue-700' : state.status === 'completed' ? 'text-emerald-700' : state.status === 'needs_attention' ? 'text-amber-800' : available ? 'text-slate-600' : 'text-slate-400'}`}>
                  {state.status === 'completed' ? '✓' : state.status === 'needs_attention' ? '!' : index + 1} · 步骤 {index + 1}
                </span>
                <span className={`mt-1 block break-words text-sm font-medium leading-5 ${current ? 'text-blue-950' : available ? 'text-slate-800' : 'text-slate-400'}`}>{step.label}</span>
                <span className={`mt-2 block break-words text-xs leading-5 ${current ? 'text-blue-700' : state.status === 'completed' ? 'text-emerald-700' : state.status === 'needs_attention' ? 'text-amber-800' : 'text-slate-500'}`}>
                  {current ? `当前步骤 · ${state.label}` : `${statusLabel} · ${state.label}`}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
