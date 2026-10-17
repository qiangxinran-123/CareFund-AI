import { workflowSteps, workflowStepIndex, type WorkflowStepId } from './workflowSteps'

interface Props {
  currentStep: WorkflowStepId
  nextBlockedReason?: string | null
  onNext: () => void
  onPrevious: () => void
}

export function WorkflowNavigation({ currentStep, nextBlockedReason, onNext, onPrevious }: Props) {
  const index = workflowStepIndex(currentStep)
  const previous = workflowSteps[index - 1]
  const next = workflowSteps[index + 1]

  return (
    <div className="mt-6 border-t border-slate-200 pt-6">
      {nextBlockedReason && <p className="mb-3 text-sm text-amber-900" role="alert">{nextBlockedReason}</p>}
      <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
        {previous
          ? <button className="button-secondary" onClick={onPrevious} type="button">上一步：{previous.label}</button>
          : <span />}
        {next && (
          <button
            aria-disabled={Boolean(nextBlockedReason)}
            className={`button-primary ${nextBlockedReason ? 'cursor-not-allowed bg-slate-300 hover:bg-slate-300' : ''}`}
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
