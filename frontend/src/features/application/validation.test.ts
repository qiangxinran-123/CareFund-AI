import { expect, it } from 'vitest'
import { initialFormValues, toPatientInfo, validateStep } from './validation'

it('rejects an empty required display name', () => {
  expect(validateStep(0, initialFormValues)).toEqual({ displayName: '请填写患者称呼。' })
})

it('accepts Unicode Chinese text and optional empty fields', () => {
  const values = { displayName: '小安家属', ageGroup: '', medicalSummary: '' } as const
  expect(validateStep(0, values)).toEqual({})
  expect(validateStep(1, values)).toEqual({})
  expect(toPatientInfo(values)).toEqual({
    display_name: '小安家属',
    age_group: null,
    medical_summary: null,
  })
})

it('rejects contract-exceeding long strings', () => {
  expect(validateStep(0, { ...initialFormValues, displayName: '称'.repeat(101) })).toHaveProperty('displayName')
  expect(validateStep(1, { ...initialFormValues, medicalSummary: '述'.repeat(2001) })).toHaveProperty('medicalSummary')
})
