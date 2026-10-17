import { afterEach, expect, it, vi } from 'vitest'
import { httpDocumentApi } from './documents'

const document = {
  document_id: 'doc_test_001',
  application_id: 'app_test_001',
  filename: 'record.pdf',
  media_type: 'application/pdf' as const,
  size_bytes: 6,
  uploaded_at: '2026-10-17T01:00:00Z',
  processing_status: 'uploaded' as const,
}

afterEach(() => vi.unstubAllGlobals())

it('uploads contract FormData without setting multipart Content-Type', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(document), { status: 201 }))
  vi.stubGlobal('fetch', fetchMock)
  const file = new File(['record'], 'record.pdf', { type: 'application/pdf' })

  await expect(httpDocumentApi.upload({
    applicationId: 'app_test_001',
    expectedRevision: 3,
    file,
    idempotencyKey: 'upload_key_001',
  })).resolves.toEqual(document)

  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/applications/app_test_001/documents')
  const init = fetchMock.mock.calls[0][1] as RequestInit
  const headers = init.headers as Headers
  const body = init.body as FormData
  expect(init.method).toBe('POST')
  expect(headers.has('Content-Type')).toBe(false)
  expect(headers.get('Idempotency-Key')).toBe('upload_key_001')
  expect(body.get('file')).toBe(file)
  expect(body.get('expected_revision')).toBe('3')
})

it('reads the document list for the encoded application id', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([document]), { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await expect(httpDocumentApi.list('app_test_001')).resolves.toEqual([document])
  expect(fetchMock.mock.calls[0][0]).toBe('/api/v1/applications/app_test_001/documents')
})

it('preserves HTTP errors from upload and list requests', async () => {
  const error = {
    error: { code: 'FILE_TOO_LARGE', message: '文件过大', details: [] },
    request_id: 'req_test_001',
  }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(
    () => Promise.resolve(new Response(JSON.stringify(error), { status: 413 })),
  ))
  const file = new File(['record'], 'record.pdf', { type: 'application/pdf' })
  await expect(httpDocumentApi.upload({
    applicationId: 'app_test_001', expectedRevision: 1, file, idempotencyKey: 'upload_key_001',
  })).rejects.toMatchObject({ kind: 'http', status: 413, response: error })
  await expect(httpDocumentApi.list('app_test_001')).rejects.toMatchObject({ kind: 'http', status: 413 })
})

it('reports network failures', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('offline')))
  await expect(httpDocumentApi.list('app_test_001')).rejects.toMatchObject({ kind: 'network' })
})

it('preserves request cancellation', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
  const controller = new AbortController()
  controller.abort()
  await expect(httpDocumentApi.list('app_test_001', controller.signal)).rejects.toMatchObject({ name: 'AbortError' })
})

it('rejects malformed upload and list responses', async () => {
  vi.stubGlobal('fetch', vi.fn()
    .mockResolvedValueOnce(new Response('{}', { status: 201 }))
    .mockResolvedValueOnce(new Response('[{"filename":"missing fields"}]', { status: 200 })))
  const file = new File(['record'], 'record.pdf', { type: 'application/pdf' })
  await expect(httpDocumentApi.upload({
    applicationId: 'app_test_001', expectedRevision: 1, file, idempotencyKey: 'upload_key_001',
  })).rejects.toMatchObject({ kind: 'invalid_response' })
  await expect(httpDocumentApi.list('app_test_001')).rejects.toMatchObject({ kind: 'invalid_response' })
})
