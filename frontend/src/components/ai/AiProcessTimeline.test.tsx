import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { AiProcessTimeline } from './AiProcessTimeline'

it('exposes verifiable process states without presenting pending work as active', () => {
  render(<AiProcessTimeline steps={[
    { id: 'done', title: '识别材料', detail: '已完成文字提取。', status: 'complete' },
    { id: 'active', title: '抽取候选事实', detail: '正在调用模型。', status: 'active' },
    { id: 'next', title: '核对证据', detail: '等待事实返回。', status: 'pending' },
  ]} />)

  expect(screen.getByTestId('ai-process-done').dataset.processStatus).toBe('complete')
  expect(screen.getByTestId('ai-process-active').dataset.processStatus).toBe('active')
  expect(screen.getByTestId('ai-process-active').getAttribute('aria-current')).toBe('step')
  expect(screen.getByTestId('ai-process-next').dataset.processStatus).toBe('pending')
  expect(screen.getAllByText('正在处理')).toHaveLength(1)
})
