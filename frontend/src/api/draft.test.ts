import { afterEach, expect, it, vi } from 'vitest'
import { ApiError } from './client'
import { httpDraftApi } from './draft'
import { application } from '../features/analysis/testFixtures'
import { draft, exportResponse } from '../features/draft/testFixtures'

afterEach(() => vi.unstubAllGlobals())

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

it('generates and gets a contract-shaped draft using the formal paths', async () => {
  const fetchMock = vi.fn().mockResolvedValueOnce(response(draft(), 201)).mockResolvedValueOnce(response(draft()))
  vi.stubGlobal('fetch', fetchMock)
  await expect(httpDraftApi.generate(application.application_id, { expected_revision: 3 })).resolves.toEqual(draft())
  await expect(httpDraftApi.getLatest(application.application_id)).resolves.toEqual(draft())
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/applications/app_test_001/draft')
  expect(fetchMock.mock.calls[0][1].method).toBe('POST')
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ expected_revision: 3 })
  expect(fetchMock.mock.calls[1][1].method).toBe('GET')
})

it('keeps generation failures and 409 conflicts as real request failures', async () => {
  const failure = { error: { code: 'AGENT_UNAVAILABLE', message: '草稿服务暂不可用', details: [] }, request_id: 'req_1' }
  const conflict = { error: { code: 'STATE_CONFLICT', message: '版本冲突', details: [] }, request_id: 'req_2' }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response(failure, 503)).mockResolvedValueOnce(response(conflict, 409)))
  await expect(httpDraftApi.generate(application.application_id, { expected_revision: 3 }))
    .rejects.toMatchObject<Partial<ApiError>>({ status: 503, message: '草稿服务暂不可用' })
  await expect(httpDraftApi.generate(application.application_id, { expected_revision: 3 }))
    .rejects.toMatchObject<Partial<ApiError>>({ status: 409, message: '版本冲突' })
})

it('rejects empty or otherwise malformed draft responses', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...draft(), sections: [] })))
  await expect(httpDraftApi.getLatest(application.application_id))
    .rejects.toMatchObject<Partial<ApiError>>({ kind: 'invalid_response' })
})

it('forwards cancellation without converting it to a network error', async () => {
  const controller = new AbortController()
  controller.abort()
  vi.stubGlobal('fetch', vi.fn((_url, options: RequestInit) => options.signal?.aborted
    ? Promise.reject(new DOMException('aborted', 'AbortError'))
    : Promise.resolve(response(draft()))))
  await expect(httpDraftApi.getLatest(application.application_id, controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
})

it('confirms a draft and exports only the contract-defined JSON format', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const fetchMock = vi.fn().mockResolvedValueOnce(response(confirmed)).mockResolvedValueOnce(response(exportResponse()))
  vi.stubGlobal('fetch', fetchMock)
  await httpDraftApi.confirm(application.application_id, {
    draft_id: confirmed.draft_id, draft_revision: 2, expected_application_revision: 3,
  })
  await expect(httpDraftApi.exportApplication(application.application_id, {
    draft_id: confirmed.draft_id, draft_revision: 2, expected_application_revision: 3, format: 'json',
  })).resolves.toEqual(exportResponse())
  expect(fetchMock.mock.calls[0][0]).toContain('/draft/confirm')
  expect(fetchMock.mock.calls[1][0]).toContain('/export')
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).format).toBe('json')
})

it('rejects malformed export metadata', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ ...exportResponse(), format: 'pdf' })))
  await expect(httpDraftApi.exportApplication(application.application_id, {
    draft_id: 'draft_test_001', draft_revision: 2, expected_application_revision: 3, format: 'json',
  })).rejects.toMatchObject<Partial<ApiError>>({ kind: 'invalid_response' })
})
