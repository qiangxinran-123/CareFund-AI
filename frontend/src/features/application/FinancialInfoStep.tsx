import type { ApplicationFormValues, FormErrors } from './validation'

interface Props {
  values: ApplicationFormValues
  errors: FormErrors
  onChange: (field: keyof ApplicationFormValues, value: string) => void
}

const fields = [
  { key: 'paidCost', label: '已支付医疗费用（选填）', hint: '填写截至目前已经支付的医疗相关费用。' },
  { key: 'estimatedCost', label: '预计后续治疗费用（选填）', hint: '如有医院预估或明确依据，可填写预计还需支付的费用。' },
  { key: 'fundingTarget', label: '筹款目标（选填）', hint: '请按实际需要自行填写，系统不会根据其他金额自动推算。' },
] as const

export function FinancialInfoStep({ values, errors, onChange }: Props) {
  return (
    <section aria-labelledby="financial-info-title">
      <h3 className="text-lg font-semibold text-slate-900" id="financial-info-title">资金情况</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">金额均以人民币元填写，最多保留两位小数。未知或暂时无法确认的项目可以留空。</p>
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        {fields.map(({ key, label, hint }) => (
          <div key={key}>
            <label className="block text-sm font-medium text-slate-800" htmlFor={key}>{label}</label>
            <div className="relative mt-2">
              <span aria-hidden="true" className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-slate-500">¥</span>
              <input
                aria-describedby={errors[key] ? `${key}-error` : `${key}-hint`}
                aria-invalid={Boolean(errors[key])}
                className="form-control pl-8"
                id={key}
                inputMode="decimal"
                onChange={(event) => onChange(key, event.target.value)}
                placeholder="0.00"
                value={values[key]}
              />
            </div>
            {errors[key]
              ? <p className="field-error" id={`${key}-error`} role="alert">{errors[key]}</p>
              : <p className="field-hint" id={`${key}-hint`}>{hint}</p>}
          </div>
        ))}
      </div>
      <p className="mt-6 rounded-xl bg-blue-50 p-4 text-sm leading-6 text-blue-900">保存只记录您填写的信息，不代表金额已经材料核实或申请已经审核。后续分析会把已支付费用和预计后续费用与上传材料分别核对。</p>
    </section>
  )
}
