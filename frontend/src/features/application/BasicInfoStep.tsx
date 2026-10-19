import type { ChangeEvent } from 'react'
import type { ApplicationFormValues, FormErrors } from './validation'

interface Props {
  values: ApplicationFormValues
  errors: FormErrors
  onChange: (field: keyof ApplicationFormValues, value: string) => void
}

export function BasicInfoStep({ values, errors, onChange }: Props) {
  return (
    <section aria-labelledby="basic-info-title">
      <h3 className="text-lg font-semibold text-slate-900" id="basic-info-title">基本信息</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">填写患者的基本情况，后续仍可修改。无需填写身份证号或详细住址。</p>
      <div className="mt-6 grid gap-6 sm:grid-cols-2">
        <div>
          <label className="block text-sm font-medium text-slate-800" htmlFor="display-name">患者称呼 <span className="text-red-600">*</span></label>
          <input
            aria-describedby={errors.displayName ? 'display-name-error' : 'display-name-hint'}
            aria-invalid={Boolean(errors.displayName)}
            className="form-control"
            id="display-name"
            maxLength={101}
            onChange={(event) => onChange('displayName', event.target.value)}
            placeholder="例如：患者本人或家属常用称呼"
            value={values.displayName}
          />
          {errors.displayName ? <p className="field-error" id="display-name-error" role="alert">{errors.displayName}</p> : <p className="field-hint" id="display-name-hint">最多 100 个字符。</p>}
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-800" htmlFor="age-group">年龄阶段（选填）</label>
          <select
            className="form-control"
            id="age-group"
            onChange={(event: ChangeEvent<HTMLSelectElement>) => onChange('ageGroup', event.target.value)}
            value={values.ageGroup}
          >
            <option value="">暂不提供</option>
            <option value="child">儿童</option>
            <option value="adult">成年人</option>
            <option value="older_adult">老年人</option>
            <option value="unknown">不确定</option>
          </select>
          <p className="field-hint">年龄阶段由您选择，系统不会自行推断。</p>
        </div>
      </div>
    </section>
  )
}
