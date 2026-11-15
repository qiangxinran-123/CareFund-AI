import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { AnalysisProcessView } from './AnalysisProcessView'
import { document, result } from './testFixtures'

afterEach(cleanup)

it('shows only the extraction stage as active while the coarse backend job is running', () => {
  render(<AnalysisProcessView documents={[document]} phase="running" result={null} />)

  expect(screen.getByTestId('ai-process-materials').dataset.processStatus).toBe('complete')
  expect(screen.getByTestId('ai-process-extract').dataset.processStatus).toBe('active')
  expect(screen.getByTestId('ai-process-evidence').dataset.processStatus).toBe('pending')
  expect(screen.getByTestId('ai-process-conflicts').dataset.processStatus).toBe('pending')
  expect(screen.getByText(/未返回的内部子步骤不会被伪装为正在运行/)).toBeTruthy()
})

it('explains evidence, conflicts, confirmation, and why generation is blocked', () => {
  render(<AnalysisProcessView documents={[document]} phase="succeeded" result={result()} />)

  expect(screen.getByTestId('ai-process-extract').dataset.processStatus).toBe('complete')
  expect(screen.getByTestId('ai-process-evidence')).toHaveProperty('textContent', expect.stringContaining('1 条材料片段'))
  expect(screen.getByTestId('ai-process-conflicts').dataset.processStatus).toBe('blocked')
  expect(screen.getByTestId('ai-process-confirmation').dataset.processStatus).toBe('waiting_user')
  const gate = screen.getByRole('heading', { name: '为什么 AI 现在不能继续' }).parentElement!
  expect(within(gate).getByText('日期信息不一致')).toBeTruthy()
  expect(within(gate).getByText(/当前缺少城市信息/)).toBeTruthy()
  expect(within(gate).getByText(/2 条候选事实等待用户确认/)).toBeTruthy()
})

it('marks missing materials as unavailable instead of claiming OCR is running', () => {
  render(<AnalysisProcessView documents={[]} phase="queued" result={null} />)
  expect(screen.getByTestId('ai-process-materials').dataset.processStatus).toBe('pending')
  expect(screen.getByText(/未上传材料；系统只能整理用户输入/)).toBeTruthy()
})
