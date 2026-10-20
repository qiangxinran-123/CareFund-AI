import { afterEach, expect, it, vi } from 'vitest'
import { httpApplicationApi } from './application'

const response = {
  application: {
    application_id: 'app_test_001',
    schema_version: '1.0' as const,
    revision: 1,
    status: 'collecting' as const,
    patient_info: { display_name: '虚构称呼', age_group: null, medical_summary: null },
    created_at: '2026-10-17T01:00:00Z',
    updated_at: '2026-10-17T01:00:00Z',
  },
  documents: [],
  evidence: [],
}

afterEach(() => vi.unstubAllGlobals())

it('creates an application with the contract request', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 201 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(httpApplicationApi.create({ patient_info: response.application.patient_info })).resolves.toEqual(response)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/applications')
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: JSON.stringify({ patient_info: response.application.patient_info }) })
})

it('gets a saved application', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(response), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(httpApplicationApi.get('app_test_001')).resolves.toEqual(response)
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/applications/app_test_001')
})

it('updates with expected_revision', async () => {
  const updated = { ...response, application: { ...response.application, revision: 2 } }
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(updated), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(httpApplicationApi.update('app_test_001', {
    expected_revision: 1,
    patient_info: { display_name: '修改后的虚构称呼' },
  })).resolves.toEqual(updated)
  expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toMatchObject({ expected_revision: 1 })
})

it.each([400, 422, 409])('preserves contract errors for HTTP %s', async (status) => {
  const error = {
    error: { code: status === 409 ? 'STATE_CONFLICT' : 'VALIDATION_FAILED', message: '请求失败', details: [] },
    request_id: 'req_test_001',
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(error), { status })))
  await expect(httpApplicationApi.get('app_test_001')).rejects.toMatchObject({ kind: 'http', status })
})

it('reports network, empty, and malformed successful responses', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValueOnce(new TypeError('offline')))
  await expect(httpApplicationApi.get('app_test_001')).rejects.toMatchObject({ kind: 'network' })

  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response(null, { status: 204 })))
  await expect(httpApplicationApi.get('app_test_001')).rejects.toMatchObject({ kind: 'invalid_response' })

  vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(new Response('{bad', { status: 200 })))
  await expect(httpApplicationApi.get('app_test_001')).rejects.toMatchObject({ kind: 'invalid_response' })
})
