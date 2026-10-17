import { beforeEach, expect, it } from 'vitest'
import { mockApplicationApi, resetMockApplication } from './applicationMock'
import { mockDocumentApi, resetMockDocuments } from './documentsMock'

beforeEach(() => {
  resetMockApplication()
  resetMockDocuments()
})

async function createApplication() {
  return mockApplicationApi.create({
    patient_info: { display_name: '虚构称呼', age_group: null, medical_summary: null },
  })
}

it('stores only contract metadata and increments the Mock application revision', async () => {
  const created = await createApplication()
  const file = new File(['record'], 'record.pdf', { type: 'application/pdf' })
  const first = await mockDocumentApi.upload({
    applicationId: created.application.application_id,
    expectedRevision: created.application.revision,
    file,
    idempotencyKey: 'upload_mock_001',
  })
  const repeated = await mockDocumentApi.upload({
    applicationId: created.application.application_id,
    expectedRevision: created.application.revision,
    file,
    idempotencyKey: 'upload_mock_001',
  })

  expect(repeated).toEqual(first)
  expect(first).toMatchObject({ filename: 'record.pdf', size_bytes: 6, processing_status: 'uploaded' })
  expect(await mockDocumentApi.list(created.application.application_id)).toEqual([first])
  expect((await mockApplicationApi.get(created.application.application_id)).application.revision).toBe(2)
})

it('loses its in-memory file list after the Mock application is reset', async () => {
  const created = await createApplication()
  await mockDocumentApi.upload({
    applicationId: created.application.application_id,
    expectedRevision: 1,
    file: new File(['image'], 'scan.jpg', { type: 'image/jpeg' }),
    idempotencyKey: 'upload_mock_002',
  })
  resetMockApplication()
  await expect(mockDocumentApi.list(created.application.application_id)).rejects.toMatchObject({ status: 404 })
})
