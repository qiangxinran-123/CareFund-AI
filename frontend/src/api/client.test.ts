import { afterEach, expect, it, vi } from 'vitest'
import { apiRequest } from './client'

afterEach(() => vi.unstubAllGlobals())

it('parses a normal JSON response', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{"value":"ok"}', {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  }))
  vi.stubGlobal('fetch', fetchMock)

  await expect(apiRequest<{ value: string }>('health')).resolves.toEqual({ value: 'ok' })
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/health')
})

it('maps the contract error envelope on HTTP errors', async () => {
  const error = {
    error: { code: 'STATE_CONFLICT', message: '版本已过期', details: [{ field: 'expected_revision', message: '请刷新' }] },
    request_id: 'req_demo_001',
  }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(error), { status: 409 })))

  await expect(apiRequest('applications/demo', { method: 'PATCH', body: { expected_revision: 1 } }))
    .rejects.toMatchObject({
      kind: 'http',
      status: 409,
      message: '版本已过期',
      response: error,
    })
})

it('reports network failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
  await expect(apiRequest('health')).rejects.toMatchObject({ kind: 'network' })
})

it('accepts an empty successful response', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
  await expect(apiRequest<void>('health')).resolves.toBeUndefined()
})

it('does not set a multipart Content-Type for FormData', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 201 }))
  vi.stubGlobal('fetch', fetchMock)
  const form = new FormData()
  form.append('file', new Blob(['demo']), 'demo.txt')
  await apiRequest('applications/demo/documents', {
    method: 'POST',
    body: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  const init = fetchMock.mock.calls[0][1] as RequestInit
  expect((init.headers as Headers).has('Content-Type')).toBe(false)
  expect(init.body).toBe(form)
})

it('reports malformed JSON responses', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{invalid', { status: 200 })))
  await expect(apiRequest('health')).rejects.toMatchObject({ kind: 'invalid_response' })
})

