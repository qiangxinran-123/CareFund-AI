import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { DraftApi } from '../../api/draft'
import { ApiError } from '../../api/client'
import { application, document as uploadedDocument, result } from '../analysis/testFixtures'
import { draft, exportResponse } from './testFixtures'
import { DraftPanel } from './DraftPanel'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function finalizableAnalysis() {
  const base = result()
  return result({ validation: { ...base.validation, can_finalize: true, issues: [] }, questions: [] })
}

function api(overrides: Partial<DraftApi> = {}): DraftApi {
  return {
    generate: vi.fn().mockResolvedValue(draft()),
    getLatest: vi.fn().mockResolvedValue(draft()),
    confirm: vi.fn().mockResolvedValue(draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })),
    exportApplication: vi.fn().mockResolvedValue(exportResponse()),
    ...overrides,
  }
}

it('requires an active user check before confirming, then enables export only after server confirmation', async () => {
  const service = api()
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} documents={[uploadedDocument]} mockMode={false} />)
  const confirm = await screen.findByRole('button', { name: '我已核对，确认草稿' })
  expect((confirm as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '导出申请资料包' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  expect((confirm as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(confirm)
  await screen.findByRole('button', { name: '草稿已确认' })
  expect(service.confirm).toHaveBeenCalledTimes(1)
  expect((screen.getByRole('button', { name: '导出申请资料包' }) as HTMLButtonElement).disabled).toBe(false)
})

it('prevents duplicate confirmation while the request is in flight', async () => {
  let resolveConfirm!: (value: ReturnType<typeof draft>) => void
  const pending = new Promise<ReturnType<typeof draft>>((resolve) => { resolveConfirm = resolve })
  const service = api({ confirm: vi.fn().mockReturnValue(pending) })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} />)
  await screen.findByRole('button', { name: '我已核对，确认草稿' })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: '我已核对，确认草稿' }))
  const busy = screen.getByRole('button', { name: '正在确认…' })
  expect((busy as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(busy)
  expect(service.confirm).toHaveBeenCalledTimes(1)
  resolveConfirm(draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' }))
  await screen.findByRole('button', { name: '草稿已确认' })
})

it('keeps the draft visible and offers retry after confirmation failure', async () => {
  const service = api({ confirm: vi.fn().mockRejectedValue(new ApiError('服务端拒绝确认', 'http', 422)) })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} />)
  await screen.findByText('病情说明')
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: '我已核对，确认草稿' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/服务端拒绝确认/)).toBeTruthy()
  expect(screen.getByText('病情说明')).toBeTruthy()
  expect((screen.getByRole('button', { name: '我已核对，确认草稿' }) as HTMLButtonElement).disabled).toBe(false)
})

it('shows blocking issues and prevents generating, confirming, and exporting', async () => {
  render(<DraftPanel analysis={result()} api={api()} application={application} />)
  await screen.findByText(/1 项需要先处理的信息/)
  expect((screen.getByRole('button', { name: '重新生成申请初稿' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '我已核对，确认草稿' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '导出申请资料包' }) as HTMLButtonElement).disabled).toBe(true)
})

it('allows generation when only non-blocking validation issues remain and can_finalize is true', async () => {
  const analysis = finalizableAnalysis()
  analysis.validation = {
    ...analysis.validation,
    issues: [{
      issue_id: 'issue_info', type: 'unsupported', severity: 'info', field: 'patient.medical_summary',
      message: '仅作提示。', related_fact_ids: ['fact_user'],
    }],
  }
  const generate = vi.fn().mockResolvedValue(draft())
  render(<DraftPanel analysis={analysis} api={api({ generate })} application={application} />)

  const button = await screen.findByRole('button', { name: '重新生成申请初稿' })
  expect((button as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(button)
  await waitFor(() => expect(generate).toHaveBeenCalledWith(
    application.application_id,
    { expected_revision: application.revision },
    expect.any(AbortSignal),
  ))
})

it('marks mismatched revisions stale and disables confirmation and export', async () => {
  const oldDraft = draft({ application_revision: 2, status: 'stale' })
  render(<DraftPanel analysis={finalizableAnalysis()} api={api({ getLatest: vi.fn().mockResolvedValue(oldDraft) })} application={application} />)
  await screen.findByText(/申请信息已更新（当前版本 3）/)
  expect((screen.getByRole('button', { name: '我已核对，确认草稿' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getAllByText(/之前的草稿需要重新生成/).length).toBeGreaterThan(0)
})

it('blocks confirmation when fact references cannot be resolved', async () => {
  const missing = draft({ sections: [{ section_id: 'missing', title: '待核对', content: '内容', fact_ids: ['unknown_fact'] }] })
  render(<DraftPanel analysis={finalizableAnalysis()} api={api({ getLatest: vi.fn().mockResolvedValue(missing) })} application={application} />)
  await screen.findByText(/有 1 项关联信息暂不可用/)
  expect((screen.getByRole('button', { name: '我已核对，确认草稿' }) as HTMLButtonElement).disabled).toBe(true)
})

it('exports contract JSON metadata and recovers from an export failure', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const exportMock = vi.fn()
    .mockRejectedValueOnce(new ApiError('导出暂不可用', 'http', 500))
    .mockResolvedValueOnce(exportResponse())
  const service = api({ getLatest: vi.fn().mockResolvedValue(confirmed), exportApplication: exportMock })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} mockMode={false} />)
  const exportButton = await screen.findByRole('button', { name: '导出申请资料包' })
  fireEvent.click(exportButton)
  await screen.findByText('导出暂不可用')
  expect((exportButton as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(exportButton)
  await screen.findByRole('link', { name: '下载申请资料包' })
  expect(exportMock).toHaveBeenCalledTimes(2)
  expect(screen.queryByText(/PDF 导出成功/)).toBeNull()
})

it('shows a completion view only after a current confirmed draft receives a usable download address', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const service = api({ getLatest: vi.fn().mockResolvedValue(confirmed) })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} mockMode={false} />)

  fireEvent.click(await screen.findByRole('button', { name: '导出申请资料包' }))
  const title = await screen.findByRole('heading', { name: '申请资料已整理完成' })
  expect(document.activeElement).toBe(title)
  expect(screen.getByText(/本系统仅协助整理材料，不代表平台已受理或审核通过/)).toBeTruthy()
  expect(screen.getByRole('link', { name: '下载申请资料包' }).getAttribute('href')).toBe('https://example.test/download/export.json')
  expect(service.exportApplication).toHaveBeenCalledTimes(1)
})

it('does not show completion when the export result has no usable delivery address', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const service = api({ getLatest: vi.fn().mockResolvedValue(confirmed), exportApplication: vi.fn().mockResolvedValue(exportResponse({ download_url: null })) })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} mockMode={false} />)

  fireEvent.click(await screen.findByRole('button', { name: '导出申请资料包' }))
  await screen.findByText('已收到导出结果，但服务端未提供下载地址。')
  expect(screen.queryByRole('heading', { name: '申请资料已整理完成' })).toBeNull()
  expect(screen.queryByRole('link', { name: '下载申请资料包' })).toBeNull()
})

it('returns to the existing draft view without issuing another draft operation', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const service = api({ getLatest: vi.fn().mockResolvedValue(confirmed) })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} mockMode={false} />)

  fireEvent.click(await screen.findByRole('button', { name: '导出申请资料包' }))
  await screen.findByRole('heading', { name: '申请资料已整理完成' })
  fireEvent.click(screen.getByRole('button', { name: '查看申请内容' }))
  await screen.findByRole('heading', { name: '确认并导出申请' })
  expect(screen.getByText('病情说明')).toBeTruthy()
  expect(service.generate).not.toHaveBeenCalled()
  expect(service.confirm).not.toHaveBeenCalled()
  expect(service.exportApplication).toHaveBeenCalledTimes(1)
})

it('invalidates the completion view when the current application revision changes', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const service = api({ getLatest: vi.fn().mockResolvedValue(confirmed) })
  const { rerender } = render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} mockMode={false} />)

  fireEvent.click(await screen.findByRole('button', { name: '导出申请资料包' }))
  await screen.findByRole('heading', { name: '申请资料已整理完成' })
  const updatedApplication = { ...application, revision: application.revision + 1 }
  const latestAnalysis = finalizableAnalysis()
  rerender(<DraftPanel analysis={{ ...latestAnalysis, application_revision: updatedApplication.revision, validation: { ...latestAnalysis.validation, application_revision: updatedApplication.revision } }} api={service} application={updatedApplication} mockMode={false} />)

  await screen.findByRole('heading', { name: '确认并导出申请' })
  expect(screen.queryByTestId('draft-completion')).toBeNull()
})

it('ignores a late draft response after switching applications', async () => {
  let resolveOld!: (value: ReturnType<typeof draft>) => void
  const oldRequest = new Promise<ReturnType<typeof draft>>((resolve) => { resolveOld = resolve })
  const service = api({ getLatest: vi.fn().mockReturnValueOnce(oldRequest).mockResolvedValueOnce(draft({ application_id: 'app_new' })) })
  const { rerender } = render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} />)
  const nextApplication = { ...application, application_id: 'app_new' }
  const nextAnalysis = { ...finalizableAnalysis(), application_id: 'app_new', validation: { ...finalizableAnalysis().validation, application_id: 'app_new' } }
  rerender(<DraftPanel analysis={nextAnalysis} api={service} application={nextApplication} />)
  await screen.findByText('病情说明')
  resolveOld(draft({ sections: [{ section_id: 'old', title: '旧申请内容', content: '不应显示', fact_ids: ['fact_user'] }] }))
  await waitFor(() => expect(screen.queryByText('旧申请内容')).toBeNull())
})
