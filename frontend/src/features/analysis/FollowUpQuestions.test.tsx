import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { FollowUpQuestions } from './FollowUpQuestions'
import { result } from './testFixtures'

afterEach(cleanup)

it('shows questions and validates required answers while allowing optional answers to remain empty', async () => {
  const submit = vi.fn().mockResolvedValue(undefined)
  render(<FollowUpQuestions onSubmit={submit} questions={result().questions} />)
  expect(screen.getByText(/提出原因：当前缺少城市信息/)).toBeTruthy()
  fireEvent.click(screen.getByRole('button', { name: '提交补充信息' }))
  expect(await screen.findByText('请填写此必答问题。')).toBeTruthy()
  expect(submit).not.toHaveBeenCalled()
  fireEvent.change(screen.getByLabelText(/请补充所在城市/), { target: { value: '杭州' } })
  fireEvent.click(screen.getByRole('button', { name: '提交补充信息' }))
  await waitFor(() => expect(submit).toHaveBeenCalledWith([{ question_id: 'q_required', answer: '杭州' }]))
})

it('keeps input after a failed submission and blocks duplicate clicks while saving', async () => {
  let reject!: (error: Error) => void
  const submit = vi.fn(() => new Promise<void>((_, fail) => { reject = fail }))
  render(<FollowUpQuestions onSubmit={submit} questions={result().questions} />)
  const input = screen.getByLabelText(/请补充所在城市/) as HTMLTextAreaElement
  fireEvent.change(input, { target: { value: '保留的回答' } })
  fireEvent.click(screen.getByRole('button', { name: '提交补充信息' }))
  fireEvent.click(screen.getByRole('button', { name: '正在提交…' }))
  expect(submit).toHaveBeenCalledTimes(1)
  reject(new Error('申请内容或版本已经变化，请刷新申请后重新操作。'))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '申请内容或版本已经变化，请刷新申请后重新操作。')
  expect(input.value).toBe('保留的回答')
})

it('renders safely when there are no questions', () => {
  render(<FollowUpQuestions onSubmit={vi.fn()} questions={[]} />)
  expect(screen.getByText('当前没有需要回答的追问。')).toBeTruthy()
})
