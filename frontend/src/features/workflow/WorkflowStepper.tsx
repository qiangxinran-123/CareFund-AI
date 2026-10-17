import { workflowSteps, type WorkflowStepId } from './workflowSteps'

interface Props {
  currentStep: WorkflowStepId
  onStepSelect: (step: WorkflowStepId) => void
  visitedSteps: ReadonlySet<WorkflowStepId>
}

export function WorkflowStepper({ currentStep, onStepSelect, visitedSteps }: Props) {
  return (
    <nav aria-label="申请向导进度" className="mb-10">
      <ol className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {workflowSteps.map((step, index) => {
          const current = step.id === currentStep
          const available = current || visitedSteps.has(step.id)
          return (
            <li key={step.id}>
              <button
                aria-current={current ? 'step' : undefined}
                className={`h-full w-full rounded-xl border px-4 py-4 text-left shadow-sm transition focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-blue-600 ${
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
                <span className={`text-xs font-semibold ${current ? 'text-blue-700' : available ? 'text-slate-600' : 'text-slate-400'}`}>步骤 {index + 1}</span>
                <span className={`mt-1 block text-sm font-medium ${current ? 'text-blue-950' : available ? 'text-slate-800' : 'text-slate-400'}`}>{step.label}</span>
              </button>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
