import type { AgeGroup, FinancialInfo, Money, PatientInfo } from '../../types/contracts'

export interface ApplicationFormValues {
  displayName: string
  ageGroup: AgeGroup | ''
  medicalSummary: string
  paidCost: string
  estimatedCost: string
  fundingTarget: string
}

export type FormErrors = Partial<Record<keyof ApplicationFormValues, string>>

export const initialFormValues: ApplicationFormValues = {
  displayName: '',
  ageGroup: '',
  medicalSummary: '',
  paidCost: '',
  estimatedCost: '',
  fundingTarget: '',
}

const moneyFields = ['paidCost', 'estimatedCost', 'fundingTarget'] as const

function toMoney(value: string): Money | null {
  const normalized = value.trim()
  if (!normalized) return null
  const [yuan, fraction = ''] = normalized.split('.')
  return { currency: 'CNY', amount_minor: Number(yuan) * 100 + Number(fraction.padEnd(2, '0')) }
}

function fromMoney(value: Money | null): string {
  if (!value) return ''
  const yuan = Math.floor(value.amount_minor / 100)
  const fraction = String(value.amount_minor % 100).padStart(2, '0')
  return fraction === '00' ? String(yuan) : `${yuan}.${fraction.replace(/0$/, '')}`
}

export function validateStep(step: number, values: ApplicationFormValues): FormErrors {
  const errors: FormErrors = {}
  if (step === 0) {
    const displayName = values.displayName.trim()
    if (!displayName) errors.displayName = '请填写患者称呼。'
    else if (displayName.length > 100) errors.displayName = '患者称呼不能超过 100 个字符。'
  }
  if (step === 1 && values.medicalSummary.trim().length > 2000) {
    errors.medicalSummary = '病情自述不能超过 2000 个字符。'
  }
  if (step === 2) {
    for (const field of moneyFields) {
      const value = values[field].trim()
      if (!value) continue
      if (!/^(0|[1-9]\d*)(\.\d{1,2})?$/.test(value)) {
        errors[field] = '请输入有效金额，最多保留两位小数。'
      } else if ((toMoney(value)?.amount_minor ?? 0) > Number.MAX_SAFE_INTEGER) {
        errors[field] = '金额过大，请检查后重新填写。'
      }
    }
  }
  return errors
}

export function toFinancialInfo(values: ApplicationFormValues): FinancialInfo {
  return {
    paid_cost: toMoney(values.paidCost),
    estimated_cost: toMoney(values.estimatedCost),
    funding_target: toMoney(values.fundingTarget),
  }
}

export function toPatientInfo(values: ApplicationFormValues): PatientInfo {
  const medicalSummary = values.medicalSummary.trim()
  return {
    display_name: values.displayName.trim(),
    age_group: values.ageGroup || null,
    medical_summary: medicalSummary || null,
  }
}

export function fromApplicationInfo(patientInfo: PatientInfo, financialInfo: FinancialInfo): ApplicationFormValues {
  return {
    displayName: patientInfo.display_name,
    ageGroup: patientInfo.age_group ?? '',
    medicalSummary: patientInfo.medical_summary ?? '',
    paidCost: fromMoney(financialInfo.paid_cost),
    estimatedCost: fromMoney(financialInfo.estimated_cost),
    fundingTarget: fromMoney(financialInfo.funding_target),
  }
}
