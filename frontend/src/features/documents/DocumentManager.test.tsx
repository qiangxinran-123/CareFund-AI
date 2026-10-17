import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { DocumentApi } from '../../api/documents'
import type { Application, UploadedDocument } from '../../types/contracts'
import { DocumentManager } from './DocumentManager'

const application: Application = {
  application_id: 'app_test_001',
  schema_version: '1.0',
  revision: 3,
  status: 'collecting',
  patient_info: { display_name: '虚构称呼', age_group: null, medical_summary: null },
  created_at: '2026-10-17T01:00:00Z',
  updated_at: '2026-10-17T01:00:00Z',
}

function uploaded(overrides: Partial<UploadedDocument> = {}): UploadedDocument {
  return {
    document_id: 'doc_test_001',
    application_id: 'app_test_001',
    filename: 'record.pdf',
    media_type: 'application/pdf',
    size_bytes: 6,
    uploaded_at: '2026-10-17T01:00:00Z',
    processing_status: 'uploaded',
    ...overrides,
  }
}

function api(overrides: Partial<DocumentApi> = {}): DocumentApi {
  return {
    upload: vi.fn().mockResolvedValue(uploaded()),
    list: vi.fn().mockResolvedValue([]),
    ...overrides,
  }
}

async function waitForEmptyList() {
  expect(await screen.findByText('暂未上传医疗材料。')).toBeTruthy()
}

afterEach(cleanup)

it('renders the upload module and empty list', async () => {
  render(<DocumentManager api={api()} application={application} />)
  expect(screen.getByRole('heading', { name: '上传医疗材料' })).toBeTruthy()
  expect(screen.getByLabelText('选择医疗材料')).toBeTruthy()
  await waitForEmptyList()
})

it('prevents upload without an application id and provides a return entry', () => {
  const documentApi = api()
  render(<DocumentManager api={documentApi} application={null} />)
  expect(screen.getByText(/请先完成并保存申请/)).toBeTruthy()
  expect(screen.getByRole('link', { name: '返回填写申请信息' }).getAttribute('href')).toBe('#application-form-title')
  expect(screen.queryByLabelText('选择医疗材料')).toBeNull()
  expect(documentApi.list).not.toHaveBeenCalled()
})

it('shows the selected file name before upload', async () => {
  render(<DocumentManager api={api()} application={application} />)
  await waitForEmptyList()
  const file = new File(['record'], 'selected.pdf', { type: 'application/pdf' })
  fireEvent.change(screen.getByLabelText('选择医疗材料'), { target: { files: [file] } })
  expect(screen.getByText('selected.pdf')).toBeTruthy()
  expect(screen.getByText(/尚未上传/)).toBeTruthy()
})

it('disables duplicate submission while uploading', async () => {
  let finish!: (value: UploadedDocument) => void
  const upload = vi.fn(() => new Promise<UploadedDocument>((resolve) => { finish = resolve }))
  render(<DocumentManager api={api({ upload })} application={application} />)
  await waitForEmptyList()
  fireEvent.change(screen.getByLabelText('选择医疗材料'), {
    target: { files: [new File(['record'], 'record.pdf', { type: 'application/pdf' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: '上传文件' }))
  const button = screen.getByRole('button', { name: '上传中…' }) as HTMLButtonElement
  expect(button.disabled).toBe(true)
  fireEvent.click(button)
  expect(upload).toHaveBeenCalledTimes(1)
  await act(async () => { finish(uploaded()) })
})

it('shows returned metadata after upload and refreshes the application revision', async () => {
  const refresh = vi.fn().mockResolvedValue(undefined)
  const documentApi = api()
  render(<DocumentManager api={documentApi} application={application} onRefreshApplication={refresh} />)
  await waitForEmptyList()
  fireEvent.change(screen.getByLabelText('选择医疗材料'), {
    target: { files: [new File(['record'], 'record.pdf', { type: 'application/pdf' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: '上传文件' }))
  expect(await screen.findByText('文件上传成功，后续处理状态请以列表为准。')).toBeTruthy()
  expect(screen.getByText('record.pdf')).toBeTruthy()
  expect(screen.getByText('已上传，等待处理')).toBeTruthy()
  expect(refresh).toHaveBeenCalledTimes(1)
  expect(documentApi.upload).toHaveBeenCalledWith(expect.objectContaining({
    applicationId: 'app_test_001', expectedRevision: 3,
  }))
})

it('shows an upload failure and offers an idempotent manual retry', async () => {
  render(<DocumentManager api={api({ upload: vi.fn().mockRejectedValue(new Error('服务暂不可用')) })} application={application} />)
  await waitForEmptyList()
  fireEvent.change(screen.getByLabelText('选择医疗材料'), {
    target: { files: [new File(['record'], 'record.pdf', { type: 'application/pdf' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: '上传文件' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '服务暂不可用')
  expect(screen.getByRole('button', { name: '使用同一幂等键重试' })).toBeTruthy()
})

it('shows a list loading failure and allows refresh', async () => {
  const list = vi.fn().mockRejectedValue(new Error('后端离线'))
  render(<DocumentManager api={api({ list })} application={application} />)
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '无法读取文件列表：后端离线')
  fireEvent.click(screen.getByRole('button', { name: '刷新状态' }))
  expect(list).toHaveBeenCalledTimes(2)
})

it('shows processing failures without calling them approval failures', async () => {
  render(<DocumentManager api={api({ list: vi.fn().mockResolvedValue([uploaded({ processing_status: 'failed' })]) })} application={application} />)
  expect(await screen.findByText('处理失败')).toBeTruthy()
  expect(screen.getByText(/不代表材料审核结果/)).toBeTruthy()
  expect(screen.queryByText('审核未通过')).toBeNull()
})

it('marks Mock mode clearly', async () => {
  render(<DocumentManager api={api()} application={application} mockMode />)
  expect(screen.getByText('Mock 模式 · 文件仅模拟上传')).toBeTruthy()
  await waitForEmptyList()
})

it('does not let an old application request overwrite a newly selected application', async () => {
  let finishFirst!: (value: UploadedDocument[]) => void
  let finishSecond!: (value: UploadedDocument[]) => void
  const list = vi.fn((applicationId: string) => new Promise<UploadedDocument[]>((resolve) => {
    if (applicationId === 'app_test_001') finishFirst = resolve
    else finishSecond = resolve
  }))
  const { rerender } = render(<DocumentManager api={api({ list })} application={application} />)
  const secondApplication = { ...application, application_id: 'app_test_002' }
  rerender(<DocumentManager api={api({ list })} application={secondApplication} />)

  await act(async () => { finishSecond([uploaded({ document_id: 'doc_test_002', application_id: 'app_test_002', filename: 'new.pdf' })]) })
  expect(screen.getByText('new.pdf')).toBeTruthy()
  await act(async () => { finishFirst([uploaded({ filename: 'old.pdf' })]) })
  expect(screen.queryByText('old.pdf')).toBeNull()
})

it('ignores an upload that finishes after switching applications', async () => {
  let finishUpload!: (value: UploadedDocument) => void
  const upload = vi.fn(() => new Promise<UploadedDocument>((resolve) => { finishUpload = resolve }))
  const documentApi = api({ upload })
  const refresh = vi.fn().mockResolvedValue(undefined)
  const { rerender } = render(
    <DocumentManager api={documentApi} application={application} onRefreshApplication={refresh} />,
  )
  await waitForEmptyList()
  fireEvent.change(screen.getByLabelText('选择医疗材料'), {
    target: { files: [new File(['old'], 'old.pdf', { type: 'application/pdf' })] },
  })
  fireEvent.click(screen.getByRole('button', { name: '上传文件' }))

  rerender(
    <DocumentManager
      api={documentApi}
      application={{ ...application, application_id: 'app_test_002' }}
      onRefreshApplication={refresh}
    />,
  )
  await act(async () => { finishUpload(uploaded({ filename: 'old.pdf' })) })
  expect(screen.queryByText('old.pdf')).toBeNull()
  expect(refresh).not.toHaveBeenCalled()
})
