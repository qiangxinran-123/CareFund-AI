import { afterEach, expect, it, vi } from 'vitest'
import { ApiError } from './client'
import { httpAnalysisApi } from './analysis'
import { application, job, result } from '../features/analysis/testFixtures'

afterEach(() => vi.unstubAllGlobals())

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

it('uses the contract paths and request bodies for analysis and answers', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(response(job('queued'), 202))
    .mockResolvedValueOnce(response(job('running')))
    .mockResolvedValueOnce(response(result()))
    .mockResolvedValueOnce(response(job('queued', 4), 202))
  vi.stubGlobal('fetch', fetchMock)
  await httpAnalysisApi.start(application.application_id, { expected_revision: 3, idempotency_key: 'analysis_key_001' })
  await httpAnalysisApi.getJob(application.application_id, 'job_test_001')
  await httpAnalysisApi.getLatest(application.application_id)
  await httpAnalysisApi.submitAnswers(application.application_id, {
    expected_revision: 3, answers: [{ question_id: 'q_required', answer: '杭州' }],
  })
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/applications/app_test_001/analyze')
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ expected_revision: 3, idempotency_key: 'analysis_key_001' })
  expect(fetchMock.mock.calls[1][0]).toBe('/api/v1/applications/app_test_001/analysis/jobs/job_test_001')
  expect(fetchMock.mock.calls[2][0]).toBe('/api/v1/applications/app_test_001/analysis')
  expect(fetchMock.mock.calls[3][0]).toBe('/api/v1/applications/app_test_001/answers')
})

it('rejects malformed jobs and analysis results instead of displaying them', async () => {
  const fetchMock = vi.fn()
    .mockResolvedValueOnce(response({ job_id: 'broken', status: 'almost_done' }))
    .mockResolvedValueOnce(response({ ...result(), facts: [{ unsafe: true }] }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(httpAnalysisApi.start(application.application_id, { expected_revision: 3, idempotency_key: 'analysis_key_001' }))
    .rejects.toMatchObject<Partial<ApiError>>({ kind: 'invalid_response' })
  await expect(httpAnalysisApi.getLatest(application.application_id))
    .rejects.toMatchObject<Partial<ApiError>>({ kind: 'invalid_response' })
})
