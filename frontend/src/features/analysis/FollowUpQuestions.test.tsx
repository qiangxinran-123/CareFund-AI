import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { FollowUpQuestions } from './FollowUpQuestions'
import { result } from './testFixtures'

afterEach(cleanup)

it('validates and submits the requested required question without rendering the old inline form', async () => {
  const submit = vi.fn().mockResolvedValue(undefined)
  render(<FollowUpQuestions onSubmit={submit} openQuestionId="q_required" questions={result().questions} />)
  const dialog = await screen.findByRole('dialog')
  expect(within(dialog).getByText(/为什么需要：当前缺少城市信息/)).toBeTruthy()
  expect(screen.queryByRole('button', { name: '提交补充信息' })).toBeNull()
  fireEvent.click(within(dialog).getByRole('button', { name: '确认提交' }))
  expect(await within(dialog).findByText('请填写此必答问题。')).toBeTruthy()
  expect(submit).not.toHaveBeenCalled()
  fireEvent.change(within(dialog).getByLabelText('请填写补充说明'), { target: { value: '杭州' } })
  fireEvent.click(within(dialog).getByRole('button', { name: '确认提交' }))
  await waitFor(() => expect(submit).toHaveBeenCalledWith([{ question_id: 'q_required', answer: '杭州' }]))
})

it('keeps input after a failed submission and blocks duplicate clicks while saving', async () => {
  let reject!: (error: Error) => void
  const submit = vi.fn(() => new Promise<void>((_, fail) => { reject = fail }))
  render(<FollowUpQuestions onSubmit={submit} openQuestionId="q_required" questions={result().questions} />)
  const input = await screen.findByLabelText('请填写补充说明') as HTMLTextAreaElement
  fireEvent.change(input, { target: { value: '保留的回答' } })
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  fireEvent.click(screen.getByRole('button', { name: '正在提交并重新核对…' }))
  expect(submit).toHaveBeenCalledTimes(1)
  reject(new Error('申请内容或版本已经变化，请刷新申请后重新操作。'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '申请内容或版本已经变化，请刷新申请后重新操作。')
  expect(input.value).toBe('保留的回答')
})

it('reports an unsaved answer until submission succeeds', async () => {
  const onStateChange = vi.fn()
  const submit = vi.fn().mockResolvedValue(undefined)
  render(<FollowUpQuestions onStateChange={onStateChange} onSubmit={submit} openQuestionId="q_required" questions={result().questions} />)
  fireEvent.change(await screen.findByLabelText('请填写补充说明'), { target: { value: '虚构城市' } })
  expect(onStateChange).toHaveBeenLastCalledWith({ answersSubmitting: false, hasUnsavedAnswers: true })
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  await waitFor(() => expect(onStateChange).toHaveBeenLastCalledWith({ answersSubmitting: false, hasUnsavedAnswers: false }))
})

it('renders safely when there are no questions', () => {
  render(<FollowUpQuestions onSubmit={vi.fn()} questions={[]} />)
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.queryByRole('heading', { name: '还需要了解这些信息' })).toBeNull()
})

it('keeps an unassociated question reachable as a compact entry instead of an inline form', async () => {
  render(<FollowUpQuestions onSubmit={vi.fn()} questions={result().questions} standaloneQuestionIds={['q_required']} />)
  expect(screen.getByText('请补充所在城市')).toBeTruthy()
  expect(screen.queryByLabelText('请填写补充说明')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '补充信息' }))
  expect(await screen.findByRole('dialog')).toBeTruthy()
})

it('opens a requested question in a dialog, validates it, and closes without submitting', async () => {
  const submit = vi.fn().mockResolvedValue(undefined)
  const onDialogClose = vi.fn()
  render(<FollowUpQuestions onDialogClose={onDialogClose} onSubmit={submit} openQuestionId="q_required" questions={result().questions} />)

  const dialog = await screen.findByRole('dialog')
  expect(screen.getByRole('heading', { name: '请补充所在城市' })).toBeTruthy()
  expect(document.activeElement).toBe(screen.getByLabelText('请填写补充说明'))
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  expect(await within(dialog).findByText('请填写此必答问题。')).toBeTruthy()
  expect(submit).not.toHaveBeenCalled()
  fireEvent(dialog, new Event('cancel', { cancelable: true }))
  expect(onDialogClose).toHaveBeenCalledTimes(1)
  expect(submit).not.toHaveBeenCalled()
})

it('keeps a dialog answer after failure and prevents duplicate dialog submissions', async () => {
  let reject!: (error: Error) => void
  const submit = vi.fn(() => new Promise<void>((_, fail) => { reject = fail }))
  render(<FollowUpQuestions onSubmit={submit} openQuestionId="q_required" questions={result().questions} />)

  const input = await screen.findByLabelText('请填写补充说明') as HTMLTextAreaElement
  fireEvent.change(input, { target: { value: '杭州' } })
  fireEvent.click(screen.getByRole('button', { name: '确认提交' }))
  fireEvent.click(screen.getByRole('button', { name: '正在提交并重新核对…' }))
  expect(submit).toHaveBeenCalledTimes(1)
  reject(new Error('提交失败，请重试。'))
  expect(await within(screen.getByRole('dialog')).findByRole('alert')).toHaveProperty('textContent', '提交失败，请重试。')
  expect(input.value).toBe('杭州')
})
