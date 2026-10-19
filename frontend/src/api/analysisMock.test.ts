import { beforeEach, expect, it } from 'vitest'
import { mockAnalysisApi, resetMockAnalysis } from './analysisMock'
import { mockApplicationApi, resetMockApplication } from './applicationMock'

beforeEach(() => {
  resetMockAnalysis()
  resetMockApplication()
})

it('models an idempotent queued-running-succeeded analysis lifecycle', async () => {
  const created = await mockApplicationApi.create({ patient_info: { display_name: '虚构用户', medical_summary: '演示自述' } })
  const id = created.application.application_id
  const input = { expected_revision: 1, idempotency_key: 'mock_key_001' }
  const first = await mockAnalysisApi.start(id, input)
  const duplicate = await mockAnalysisApi.start(id, input)
  expect(duplicate.job_id).toBe(first.job_id)
  expect((await mockAnalysisApi.getJob(id, first.job_id)).status).toBe('running')
  expect((await mockAnalysisApi.getJob(id, first.job_id)).status).toBe('succeeded')
  const analysis = await mockAnalysisApi.getLatest(id)
  expect(analysis.facts.some((fact) => fact.verification_status === 'supported')).toBe(true)
  expect(analysis.facts.some((fact) => fact.verification_status === 'conflicting')).toBe(true)
  expect(analysis.validation.issues.some((issue) => issue.type === 'unsupported')).toBe(true)
})

it('submits contract-shaped answers, advances revision, and queues reanalysis', async () => {
  const created = await mockApplicationApi.create({ patient_info: { display_name: '虚构用户', medical_summary: '演示自述' } })
  const id = created.application.application_id
  const started = await mockAnalysisApi.start(id, { expected_revision: 1, idempotency_key: 'mock_key_001' })
  await mockAnalysisApi.getJob(id, started.job_id)
  await mockAnalysisApi.getJob(id, started.job_id)
  const answerJob = await mockAnalysisApi.submitAnswers(id, {
    expected_revision: 1, answers: [{ question_id: 'question_mock_date', answer: '是' }],
  })
  expect(answerJob.application_revision).toBe(2)
  expect((await mockApplicationApi.get(id)).application.revision).toBe(2)
  await expect(mockAnalysisApi.submitAnswers(id, {
    expected_revision: 1, answers: [{ question_id: 'question_mock_date', answer: '再次提交' }],
  })).rejects.toMatchObject({ status: 409 })
})
