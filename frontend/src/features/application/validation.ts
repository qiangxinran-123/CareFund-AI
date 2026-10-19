import type { AgeGroup, PatientInfo } from '../../types/contracts'

export interface ApplicationFormValues {
  displayName: string
  ageGroup: AgeGroup | ''
  medicalSummary: string
}

export type FormErrors = Partial<Record<keyof ApplicationFormValues, string>>

export const initialFormValues: ApplicationFormValues = {
  displayName: '',
  ageGroup: '',
  medicalSummary: '',
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
  return errors
}

export function toPatientInfo(values: ApplicationFormValues): PatientInfo {
  const medicalSummary = values.medicalSummary.trim()
  return {
    display_name: values.displayName.trim(),
    age_group: values.ageGroup || null,
    medical_summary: medicalSummary || null,
  }
}

export function fromPatientInfo(patientInfo: PatientInfo): ApplicationFormValues {
  return {
    displayName: patientInfo.display_name,
    ageGroup: patientInfo.age_group ?? '',
    medicalSummary: patientInfo.medical_summary ?? '',
  }
}
