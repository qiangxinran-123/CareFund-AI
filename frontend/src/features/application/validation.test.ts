import { expect, it } from 'vitest'
import { initialFormValues, toFinancialInfo, toPatientInfo, validateStep } from './validation'

it('rejects an empty required display name', () => {
  expect(validateStep(0, initialFormValues)).toEqual({ displayName: '请填写患者称呼。' })
})

it('accepts Unicode Chinese text and optional empty fields', () => {
  const values = { ...initialFormValues, displayName: '小安家属' } as const
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

it('converts financial yuan input to exact integer minor units', () => {
  const values = { ...initialFormValues, paidCost: '1200', estimatedCost: '3500.5', fundingTarget: '4000.08' }
  expect(validateStep(2, values)).toEqual({})
  expect(toFinancialInfo(values)).toEqual({
    paid_cost: { currency: 'CNY', amount_minor: 120000 },
    estimated_cost: { currency: 'CNY', amount_minor: 350050 },
    funding_target: { currency: 'CNY', amount_minor: 400008 },
  })
})

it('rejects negative, exponent and over-precise financial input', () => {
  expect(validateStep(2, { ...initialFormValues, paidCost: '-1' })).toHaveProperty('paidCost')
  expect(validateStep(2, { ...initialFormValues, estimatedCost: '1e3' })).toHaveProperty('estimatedCost')
  expect(validateStep(2, { ...initialFormValues, fundingTarget: '1.234' })).toHaveProperty('fundingTarget')
})
