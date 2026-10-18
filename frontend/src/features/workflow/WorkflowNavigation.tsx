import { workflowSteps, workflowStepIndex, type WorkflowStepId } from './workflowSteps'

interface Props {
  blockedReason?: string | null
  currentStep: WorkflowStepId
  onNext: () => void
  onPrevious: () => void
}

export function WorkflowNavigation({ blockedReason, currentStep, onNext, onPrevious }: Props) {
  const index = workflowStepIndex(currentStep)
  const previous = workflowSteps[index - 1]
  const next = workflowSteps[index + 1]

  return (
    <div className="mt-6 rounded-xl border border-slate-200 bg-white p-4 sm:p-5">
      {blockedReason && <p className="mb-4 rounded-lg bg-amber-50 p-3 text-sm leading-6 text-amber-900" role="alert">{blockedReason}</p>}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
        {previous
          ? <button className="button-secondary w-full sm:w-auto" disabled={Boolean(blockedReason)} onClick={onPrevious} type="button">上一步：{previous.label}</button>
          : <span />}
        {next && (
          <button
            aria-disabled={Boolean(blockedReason)}
            className={`button-primary w-full sm:w-auto ${blockedReason ? 'cursor-not-allowed bg-slate-300 hover:bg-slate-300' : ''}`}
            disabled={Boolean(blockedReason)}
            onClick={onNext}
            type="button"
          >
            下一步：{next.label}
          </button>
        )}
      </div>
    </div>
  )
}
