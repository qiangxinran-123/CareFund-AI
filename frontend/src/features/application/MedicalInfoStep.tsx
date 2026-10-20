import type { ApplicationFormValues, FormErrors } from './validation'

interface Props {
  values: ApplicationFormValues
  errors: FormErrors
  onChange: (field: keyof ApplicationFormValues, value: string) => void
}

export function MedicalInfoStep({ values, errors, onChange }: Props) {
  return (
    <section aria-labelledby="medical-info-title">
      <h3 className="text-lg font-semibold text-slate-900" id="medical-info-title">医疗情况</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">请简要描述目前的病情和治疗情况，尽量依据实际经历填写。这属于您的自述，不代表诊断或审核结论。</p>
      <div className="mt-6">
        <label className="block text-sm font-medium text-slate-800" htmlFor="medical-summary">病情与治疗情况自述（选填）</label>
        <textarea
          aria-describedby={errors.medicalSummary ? 'medical-summary-error' : 'medical-summary-hint'}
          aria-invalid={Boolean(errors.medicalSummary)}
          className="form-control min-h-40 resize-y"
          id="medical-summary"
          maxLength={2001}
          onChange={(event) => onChange('medicalSummary', event.target.value)}
          placeholder="请用自己的话说明当前病情和已知治疗经历；不确定的信息可以不填。"
          value={values.medicalSummary}
        />
        {errors.medicalSummary ? <p className="field-error" id="medical-summary-error" role="alert">{errors.medicalSummary}</p> : <p className="field-hint" id="medical-summary-hint">最多 2000 个字符，可留空。</p>}
      </div>
    </section>
  )
}
