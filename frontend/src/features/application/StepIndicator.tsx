const steps = ['基本信息', '医疗情况', '资金情况'] as const

export function StepIndicator({ currentStep }: { currentStep: number }) {
  return (
    <div className="mb-8">
      <div className="mb-3 flex items-center justify-between gap-4">
        <p className="text-sm font-medium text-slate-700">填写进度</p>
        <p className="text-sm text-slate-500">第 {currentStep + 1} 步，共 {steps.length} 步</p>
      </div>
      <div
        aria-label={`申请信息填写进度：${currentStep + 1}/${steps.length}`}
        aria-valuemax={steps.length}
        aria-valuemin={1}
        aria-valuenow={currentStep + 1}
        className="h-2 overflow-hidden rounded-full bg-slate-100"
        role="progressbar"
      >
        <div className="h-full rounded-full bg-blue-600 transition-[width]" style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }} />
      </div>
      <ol aria-label="申请信息填写步骤" className="mt-4 grid grid-cols-3 gap-2">
        {steps.map((step, index) => (
          <li
            aria-current={index === currentStep ? 'step' : undefined}
            className={`rounded-lg border px-2 py-3 text-center text-xs font-medium sm:text-sm ${
              index === currentStep ? 'border-blue-200 bg-blue-50 text-blue-800' : 'border-slate-200 bg-white text-slate-500'
            }`}
            key={step}
          >
            {index + 1}. {step}
          </li>
        ))}
      </ol>
    </div>
  )
}
