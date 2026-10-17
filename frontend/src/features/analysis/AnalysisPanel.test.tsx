import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
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
  expect(screen.getByText(/请先完成并保存申请/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: '开始分析' })).toBeNull()
  expect(analysisApi.getLatest).not.toHaveBeenCalled()
})

it('shows no-material guidance without inventing a hard requirement', async () => {
  render(<AnalysisPanel api={api()} application={application} documents={[]} />)
  expect(await screen.findByRole('button', { name: '开始分析' })).toBeTruthy()
  expect(screen.getByText(/仍可尝试分析用户自述/)).toBeTruthy()
})

it('shows submitting and prevents duplicate analysis requests', async () => {
  const pending = deferred<AnalysisJob>()
  const start = vi.fn(() => pending.promise)
  render(<AnalysisPanel api={api({ start })} application={application} />)
  const button = await screen.findByRole('button', { name: '开始分析' })
  fireEvent.click(button)
  expect(await screen.findByText('正在提交分析请求…')).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '分析处理中…' }))
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
  fireEvent.click(await screen.findByRole('button', { name: '开始分析' }))
  expect(await screen.findByText('分析任务已进入等待队列。')).toBeTruthy()
  await act(async () => { firstPoll.resolve(job('running')) })
  expect(await screen.findByText('正在整理您提交的信息，请稍候。')).toBeTruthy()
  await act(async () => { secondPoll.resolve(job('succeeded')) })
  expect(await screen.findByText('分析已完成，请核对以下结果。')).toBeTruthy()
  expect(screen.getByText(/共整理 3 项事实/)).toBeTruthy()
  expect(getJob).toHaveBeenCalledTimes(2)
  await new Promise((resolve) => window.setTimeout(resolve, 5))
  expect(getJob).toHaveBeenCalledTimes(2)
})

it('shows task failure and network errors without a false success', async () => {
  const failedApi = api({ start: vi.fn().mockResolvedValue({ ...job('failed'), error: { code: 'AGENT_UNAVAILABLE', message: '分析服务暂不可用', details: [] } }) })
  const { unmount } = render(<AnalysisPanel api={failedApi} application={application} pollIntervalMs={0} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始分析' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '分析服务暂不可用')
  unmount()

  const networkApi = api({ start: vi.fn().mockRejectedValue(new ApiError('网络请求失败，请检查连接后重试。', 'network')) })
  render(<AnalysisPanel api={networkApi} application={application} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始分析' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '网络请求失败，请检查连接后重试。')
  expect(screen.queryByText('分析已完成，请核对以下结果。')).toBeNull()
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
  expect(await screen.findByRole('button', { name: '开始分析' })).toBeTruthy()
  await act(async () => { oldRequest.resolve(result()) })
  expect(screen.queryByText('用户自述内容')).toBeNull()
  expect(screen.getByText('app_test_002')).toBeTruthy()
})

it('does not show a result from a different revision', async () => {
  const stale = result({ application_revision: application.revision - 1 })
  stale.validation = { ...stale.validation, application_revision: application.revision - 1 }
  render(<AnalysisPanel api={api({ getLatest: vi.fn().mockResolvedValue(stale) })} application={application} />)
  expect(await screen.findByText(/现有分析结果与当前申请版本不一致/)).toBeTruthy()
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
  fireEvent.change(await screen.findByLabelText(/请补充所在城市/), { target: { value: '杭州' } })
  fireEvent.click(screen.getByRole('button', { name: '提交补充信息' }))
  expect(await screen.findByText('补充信息已提交，分析结果已更新。')).toBeTruthy()
  expect(analysisApi.submitAnswers).toHaveBeenCalledWith(application.application_id, {
    expected_revision: application.revision,
    answers: [{ question_id: 'q_required', answer: '杭州' }],
  }, expect.any(AbortSignal))
  expect(refreshApplication).toHaveBeenCalledTimes(1)
  expect(screen.getByText('当前没有需要回答的追问。')).toBeTruthy()
})

it('keeps an answer after a 409 revision conflict', async () => {
  const analysisApi = api({
    getLatest: vi.fn().mockResolvedValue(result()),
    submitAnswers: vi.fn().mockRejectedValue(new ApiError('冲突', 'http', 409)),
  })
  render(<AnalysisPanel api={analysisApi} application={application} />)
  const input = await screen.findByLabelText(/请补充所在城市/) as HTMLTextAreaElement
  fireEvent.change(input, { target: { value: '仍需保留' } })
  fireEvent.click(screen.getByRole('button', { name: '提交补充信息' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '申请内容或版本已经变化，请刷新申请后重新操作。')
  expect(input.value).toBe('仍需保留')
})

it('pauses finite polling and allows continuing the same task', async () => {
  const getJob = vi.fn().mockResolvedValue(job('running'))
  render(<AnalysisPanel api={api({ getJob })} application={application} maxPollAttempts={1} pollIntervalMs={0} />)
  fireEvent.click(await screen.findByRole('button', { name: '开始分析' }))
  expect(await screen.findByText(/已暂停自动查询/)).toBeTruthy()
  expect(screen.getByRole('button', { name: '继续查询任务' })).toBeTruthy()
  expect(getJob).toHaveBeenCalledTimes(1)
})
