import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import type { AnalysisApi } from '../../api/analysis'
import { ApiError } from '../../api/client'
import type { AnalysisJob, AnalysisResult } from '../../types/contracts'
import { AnalysisPanel } from './AnalysisPanel'
import { application, document, job, result } from './testFixtures'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function notFound() {
  return new ApiError('尚无结果', 'http', 404)
}

function api(overrides: Partial<AnalysisApi> = {}): AnalysisApi {
  return {
    start: vi.fn().mockResolvedValue(job('queued')),
    getJob: vi.fn().mockResolvedValue(job('succeeded')),
    getLatest: vi.fn().mockRejectedValue(notFound()),
    submitAnswers: vi.fn().mockResolvedValue(job('queued', application.revision + 1)),
    ...overrides,
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

it('disables analysis when there is no saved application', () => {
  const analysisApi = api()
  render(<AnalysisPanel api={analysisApi} application={null} />)
  expect(screen.getByText(/请先填写并保存求助信息/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: '开始整理和核对' })).toBeNull()
  expect(analysisApi.getLatest).not.toHaveBeenCalled()
})

it('shows no-material guidance without inventing a hard requirement', async () => {
  render(<AnalysisPanel api={api()} application={application} documents={[]} />)
  expect(await screen.findByRole('button', { name: '开始整理和核对' })).toBeTruthy()
  expect(screen.getByText(/仍可以整理已填写的内容/)).toBeTruthy()
})

it('combines reliably related validation issues with their facts and keeps unassociated issues visible', async () => {
  const analysisApi = api({ getLatest: vi.fn().mockResolvedValue(result()) })
  render(<AnalysisPanel api={analysisApi} application={application} documents={[document]} />)

  expect(await screen.findByRole('heading', { name: '核对您的申请信息' })).toBeTruthy()
  expect(screen.getByText('需要处理：3 项 · 其他已整理信息：1 条')).toBeTruthy()
  expect(screen.getByText('需要处理的信息')).toBeTruthy()
  expect(screen.getByTestId('validation-issue-issue_conflict')).toBeTruthy()
  expect(screen.getByTestId('validation-issue-issue_unsupported')).toBeTruthy()
  expect(screen.getByTestId('validation-issue-issue_missing')).toBeTruthy()
  expect(screen.getAllByTestId('validation-issue-issue_conflict')).toHaveLength(1)
  expect(screen.queryByText('已确认')).toBeNull()
  expect(analysisApi.start).not.toHaveBeenCalled()
  expect(analysisApi.submitAnswers).not.toHaveBeenCalled()
})

it('does not show an empty independent issue section when every issue is already attached to a fact', async () => {
  const analysis = result()
  analysis.validation = { ...analysis.validation, issues: [analysis.validation.issues[1]] }
  render(<AnalysisPanel api={api({ getLatest: vi.fn().mockResolvedValue(analysis) })} application={application} />)

  expect(await screen.findByTestId('validation-issue-issue_conflict')).toBeTruthy()
  expect(screen.queryByRole('heading', { name: '需要您核对的信息' })).toBeNull()
  expect(screen.queryByText('目前没有需要补充或核对的信息。这不代表平台审核通过。')).toBeNull()
})

it('opens the unique formal follow-up path from an issue card and reuses answer submission', async () => {
  const refreshed = result({ application_revision: application.revision + 1, questions: [] })
  refreshed.validation = { ...refreshed.validation, application_revision: application.revision + 1, issues: [] }
  const submitAnswers = vi.fn().mockResolvedValue(job('queued', application.revision + 1))
  const analysisApi = api({
    getLatest: vi.fn().mockResolvedValueOnce(result()).mockResolvedValueOnce(refreshed),
    getJob: vi.fn().mockResolvedValue(job('succeeded', application.revision + 1)),
    submitAnswers,
  })
  render(<AnalysisPanel api={analysisApi} application={application} pollIntervalMs={0} />)

  const missingIssue = await screen.findByTestId('validation-issue-issue_missing')
  const questionButton = await within(missingIssue).findByRole('button', { name: '补充信息' })
  expect(within(screen.getByTestId('validation-issue-issue_conflict')).queryByRole('button', { name: '补充信息' })).toBeNull()
  fireEvent.click(questionButton)
  const dialog = await screen.findByRole('dialog')
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  await waitFor(() => expect(globalThis.document.activeElement).toBe(questionButton))
  expect(submitAnswers).not.toHaveBeenCalled()
  fireEvent.click(questionButton)
  const input = await screen.findByLabelText('请填写补充说明')
  expect(globalThis.document.activeElement).toBe(input)
  fireEvent.change(input, { target: { value: '杭州' } })
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  await waitFor(() => expect(submitAnswers).toHaveBeenCalledWith(application.application_id, {
    expected_revision: application.revision,
    answers: [{ question_id: 'q_required', answer: '杭州' }],
  }, expect.any(AbortSignal)))
  expect(await screen.findByText('信息已更新，核对完成。')).toBeTruthy()
})

it('shows submitting and prevents duplicate analysis requests', async () => {
  const pending = deferred<AnalysisJob>()
  const start = vi.fn(() => pending.promise)
  render(<AnalysisPanel api={api({ start })} application={application} />)
  const button = await screen.findByRole('button', { name: '开始整理和核对' })
  fireEvent.click(button)
  expect(await screen.findByText('正在提交整理请求…')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '正在整理资料…' }))
  expect(start).toHaveBeenCalledTimes(1)
  await act(async () => { pending.resolve(job('failed')) })
})

it('shows queued and running states, then fetches the result and stops polling', async () => {
  const firstPoll = deferred<AnalysisJob>()
  const secondPoll = deferred<AnalysisJob>()
  const getJob = vi.fn()
    .mockImplementationOnce(() => firstPoll.promise)
    .mockImplementationOnce(() => secondPoll.promise)
  const latest = vi.fn()
    .mockRejectedValueOnce(notFound())
    .mockResolvedValueOnce(result())
  const analysisApi = api({ getJob, getLatest: latest })
  render(<AnalysisPanel api={analysisApi} application={application} documents={[document]} pollIntervalMs={0} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始整理和核对' }))
  expect(await screen.findByText('已收到请求，正在等待处理。')).toBeTruthy()
  await act(async () => { firstPoll.resolve(job('running')) })
  expect(await screen.findByText('正在整理您的资料，请稍候。')).toBeTruthy()
  await act(async () => { secondPoll.resolve(job('succeeded')) })
  expect(await screen.findByText('资料整理完成，请查看需要核对的信息。')).toBeTruthy()
  expect(screen.getByText('需要处理：3 项 · 其他已整理信息：1 条')).toBeTruthy()
  expect(getJob).toHaveBeenCalledTimes(2)
  await new Promise((resolve) => window.setTimeout(resolve, 5))
  expect(getJob).toHaveBeenCalledTimes(2)
})

it('shows task failure and network errors without a false success', async () => {
  const failedApi = api({ start: vi.fn().mockResolvedValue({ ...job('failed'), error: { code: 'AGENT_UNAVAILABLE', message: '分析服务暂不可用', details: [] } }) })
  const { unmount } = render(<AnalysisPanel api={failedApi} application={application} pollIntervalMs={0} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始整理和核对' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '分析服务暂不可用')
  unmount()

  const networkApi = api({ start: vi.fn().mockRejectedValue(new ApiError('网络请求失败，请检查连接后重试。', 'network')) })
  render(<AnalysisPanel api={networkApi} application={application} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始整理和核对' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '网络请求失败，请检查连接后重试。')
  expect(screen.queryByText('资料整理完成，请查看需要核对的信息。')).toBeNull()
})

it('does not let an old application request overwrite the current application', async () => {
  const oldRequest = deferred<AnalysisResult>()
  const latest = vi.fn()
    .mockImplementationOnce(() => oldRequest.promise)
    .mockRejectedValueOnce(notFound())
  const analysisApi = api({ getLatest: latest })
  const { rerender } = render(<AnalysisPanel api={analysisApi} application={application} />)
  const nextApplication = { ...application, application_id: 'app_test_002' }
  rerender(<AnalysisPanel api={analysisApi} application={nextApplication} />)
  expect(await screen.findByRole('button', { name: '开始整理和核对' })).toBeTruthy()
  await act(async () => { oldRequest.resolve(result()) })
  expect(screen.queryByText('用户自述内容')).toBeNull()
  expect(screen.getByText('app_test_002')).toBeTruthy()
})

it('does not show a result from a different revision', async () => {
  const stale = result({ application_revision: application.revision - 1 })
  stale.validation = { ...stale.validation, application_revision: application.revision - 1 }
  render(<AnalysisPanel api={api({ getLatest: vi.fn().mockResolvedValue(stale) })} application={application} />)
  expect(await screen.findByText(/申请信息已更新，之前的整理结果不能继续使用/)).toBeTruthy()
  expect(screen.queryByText('用户自述内容')).toBeNull()
})

it('submits answers, follows the returned revision, and refreshes the latest result', async () => {
  const refreshed = result({ application_revision: application.revision + 1, questions: [] })
  refreshed.validation = { ...refreshed.validation, application_revision: application.revision + 1, issues: [] }
  const latest = vi.fn().mockResolvedValueOnce(result()).mockResolvedValueOnce(refreshed)
  const refreshApplication = vi.fn().mockResolvedValue(undefined)
  const analysisApi = api({
    getLatest: latest,
    submitAnswers: vi.fn().mockResolvedValue(job('queued', application.revision + 1)),
    getJob: vi.fn().mockResolvedValue(job('succeeded', application.revision + 1)),
  })
  render(<AnalysisPanel api={analysisApi} application={application} onRefreshApplication={refreshApplication} pollIntervalMs={0} />)
  fireEvent.click(within(await screen.findByTestId('validation-issue-issue_missing')).getByRole('button', { name: '补充信息' }))
  fireEvent.change(await screen.findByLabelText('请填写补充说明'), { target: { value: '杭州' } })
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  expect(await screen.findByText('信息已更新，核对完成。')).toBeTruthy()
  expect(analysisApi.submitAnswers).toHaveBeenCalledWith(application.application_id, {
    expected_revision: application.revision,
    answers: [{ question_id: 'q_required', answer: '杭州' }],
  }, expect.any(AbortSignal))
  expect(refreshApplication).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('heading', { name: '还需要了解这些信息' })).toBeNull()
})

it('keeps an answer after a 409 revision conflict', async () => {
  const analysisApi = api({
    getLatest: vi.fn().mockResolvedValue(result()),
    submitAnswers: vi.fn().mockRejectedValue(new ApiError('冲突', 'http', 409)),
  })
  render(<AnalysisPanel api={analysisApi} application={application} />)
  fireEvent.click(within(await screen.findByTestId('validation-issue-issue_missing')).getByRole('button', { name: '补充信息' }))
  const input = await screen.findByLabelText('请填写补充说明') as HTMLTextAreaElement
  fireEvent.change(input, { target: { value: '仍需保留' } })
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '申请信息已更新，请刷新后重新操作。')
  expect(input.value).toBe('仍需保留')
})

it('pauses finite polling and allows continuing the same task', async () => {
  const getJob = vi.fn().mockResolvedValue(job('running'))
  render(<AnalysisPanel api={api({ getJob })} application={application} maxPollAttempts={1} pollIntervalMs={0} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始整理和核对' }))
  expect(await screen.findByText(/已暂停自动查询/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '继续查看进度' })).toBeTruthy()
  expect(getJob).toHaveBeenCalledTimes(1)
})
