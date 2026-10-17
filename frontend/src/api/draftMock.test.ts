import { beforeEach, expect, it } from 'vitest'
import { mockAnalysisApi, resetMockAnalysis } from './analysisMock'
import { mockApplicationApi, resetMockApplication } from './applicationMock'
import { mockDraftApi, resetMockDraft } from './draftMock'

beforeEach(() => {
  resetMockDraft()
  resetMockAnalysis()
  resetMockApplication()
})

async function analyzedApplication() {
  const created = await mockApplicationApi.create({ patient_info: { display_name: '虚构用户', medical_summary: '完全虚构的自述' } })
  const id = created.application.application_id
  const job = await mockAnalysisApi.start(id, { expected_revision: 1, idempotency_key: 'draft_mock_key' })
  await mockAnalysisApi.getJob(id, job.job_id)
  await mockAnalysisApi.getJob(id, job.job_id)
  return id
}

it('generates multiple fictional sections with valid fact references', async () => {
  const id = await analyzedApplication()
  const generated = await mockDraftApi.generate(id, { expected_revision: 1 })
  expect(generated.sections).toHaveLength(2)
  expect(generated.sections.flatMap((section) => section.fact_ids)).toEqual(['fact_mock_summary', 'fact_mock_cost'])
})

it('marks an old draft stale and rejects confirmation with a revision conflict', async () => {
  const id = await analyzedApplication()
  const generated = await mockDraftApi.generate(id, { expected_revision: 1 })
  await mockApplicationApi.update(id, { expected_revision: 1, patient_info: { medical_summary: '虚构修改' } })
  await expect(mockDraftApi.getLatest(id)).resolves.toMatchObject({ status: 'stale', application_revision: 1 })
  await expect(mockDraftApi.confirm(id, {
    draft_id: generated.draft_id, draft_revision: generated.draft_revision, expected_application_revision: 1,
  })).rejects.toMatchObject({ status: 409 })
})

it('blocks confirmation while validation cannot finalize', async () => {
  const id = await analyzedApplication()
  const generated = await mockDraftApi.generate(id, { expected_revision: 1 })
  await expect(mockDraftApi.confirm(id, {
    draft_id: generated.draft_id, draft_revision: generated.draft_revision, expected_application_revision: 1,
  })).rejects.toMatchObject({ status: 422 })
})

it('confirms and exports after follow-up revalidation clears blocking issues', async () => {
  const id = await analyzedApplication()
  const answerJob = await mockAnalysisApi.submitAnswers(id, {
    expected_revision: 1, answers: [{ question_id: 'question_mock_date', answer: '虚构确认' }],
  })
  await mockAnalysisApi.getJob(id, answerJob.job_id)
  await mockAnalysisApi.getJob(id, answerJob.job_id)
  const generated = await mockDraftApi.generate(id, { expected_revision: 2 })
  const confirmed = await mockDraftApi.confirm(id, {
    draft_id: generated.draft_id, draft_revision: generated.draft_revision, expected_application_revision: 2,
  })
  expect(confirmed.status).toBe('confirmed')
  await expect(mockDraftApi.exportApplication(id, {
    draft_id: confirmed.draft_id, draft_revision: confirmed.draft_revision,
    expected_application_revision: 2, format: 'json',
  })).resolves.toMatchObject({ format: 'json', download_url: null })
})
