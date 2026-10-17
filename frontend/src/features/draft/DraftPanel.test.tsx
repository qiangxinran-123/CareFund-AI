import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { DraftApi } from '../../api/draft'
import { ApiError } from '../../api/client'
import { application, document, result } from '../analysis/testFixtures'
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
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} documents={[document]} mockMode={false} />)
  const confirm = await screen.findByRole('button', { name: '确认此草稿' })
  expect((confirm as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '导出 JSON 申请包' }) as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  expect((confirm as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(confirm)
  await screen.findByRole('button', { name: '草稿已确认' })
  expect(service.confirm).toHaveBeenCalledTimes(1)
  expect((screen.getByRole('button', { name: '导出 JSON 申请包' }) as HTMLButtonElement).disabled).toBe(false)
})

it('prevents duplicate confirmation while the request is in flight', async () => {
  let resolveConfirm!: (value: ReturnType<typeof draft>) => void
  const pending = new Promise<ReturnType<typeof draft>>((resolve) => { resolveConfirm = resolve })
  const service = api({ confirm: vi.fn().mockReturnValue(pending) })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} />)
  await screen.findByRole('button', { name: '确认此草稿' })
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(screen.getByRole('button', { name: '确认此草稿' }))
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
  fireEvent.click(screen.getByRole('button', { name: '确认此草稿' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/服务端拒绝确认/)).toBeTruthy()
  expect(screen.getByText('病情说明')).toBeTruthy()
  expect((screen.getByRole('button', { name: '确认此草稿' }) as HTMLButtonElement).disabled).toBe(false)
})

it('shows blocking issues and prevents confirm/export without preventing generation', async () => {
  render(<DraftPanel analysis={result()} api={api()} application={application} />)
  await screen.findByText(/1 项阻断性问题/)
  expect((screen.getByRole('button', { name: '重新生成草稿' }) as HTMLButtonElement).disabled).toBe(false)
  expect((screen.getByRole('button', { name: '确认此草稿' }) as HTMLButtonElement).disabled).toBe(true)
  expect((screen.getByRole('button', { name: '导出 JSON 申请包' }) as HTMLButtonElement).disabled).toBe(true)
})

it('marks mismatched revisions stale and disables confirmation and export', async () => {
  const oldDraft = draft({ application_revision: 2, status: 'stale' })
  render(<DraftPanel analysis={finalizableAnalysis()} api={api({ getLatest: vi.fn().mockResolvedValue(oldDraft) })} application={application} />)
  await screen.findByText(/草稿对应申请版本 2/)
  expect((screen.getByRole('button', { name: '确认此草稿' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText(/草稿已过期，不能导出/)).toBeTruthy()
})

it('blocks confirmation when fact references cannot be resolved', async () => {
  const missing = draft({ sections: [{ section_id: 'missing', title: '待核对', content: '内容', fact_ids: ['unknown_fact'] }] })
  render(<DraftPanel analysis={finalizableAnalysis()} api={api({ getLatest: vi.fn().mockResolvedValue(missing) })} application={application} />)
  await screen.findByText(/有 1 项关联事实暂不可用/)
  expect((screen.getByRole('button', { name: '确认此草稿' }) as HTMLButtonElement).disabled).toBe(true)
})

it('exports contract JSON metadata and recovers from an export failure', async () => {
  const confirmed = draft({ status: 'confirmed', confirmed_at: '2026-10-17T03:30:00Z' })
  const exportMock = vi.fn()
    .mockRejectedValueOnce(new ApiError('导出暂不可用', 'http', 500))
    .mockResolvedValueOnce(exportResponse())
  const service = api({ getLatest: vi.fn().mockResolvedValue(confirmed), exportApplication: exportMock })
  render(<DraftPanel analysis={finalizableAnalysis()} api={service} application={application} mockMode={false} />)
  const exportButton = await screen.findByRole('button', { name: '导出 JSON 申请包' })
  fireEvent.click(exportButton)
  await screen.findByText('导出暂不可用')
  expect((exportButton as HTMLButtonElement).disabled).toBe(false)
  fireEvent.click(exportButton)
  await screen.findByRole('link', { name: '下载 JSON 申请包' })
  expect(exportMock).toHaveBeenCalledTimes(2)
  expect(screen.queryByText(/PDF 导出成功/)).toBeNull()
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
