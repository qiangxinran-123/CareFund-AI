import { render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { WorkflowStepper } from './WorkflowStepper'
import type { WorkflowStepState } from './workflowStatus'

const states: Record<'application' | 'documents' | 'analysis' | 'draft', WorkflowStepState> = {
  application: { status: 'completed', label: '已保存' },
  documents: { status: 'pending', label: '尚未处理' },
  analysis: { status: 'needs_attention', label: '需要补充信息' },
  draft: { status: 'pending', label: '尚未生成草稿' },
}

it('keeps all four step names and text statuses available in the responsive progress navigation', () => {
  render(
    <WorkflowStepper
      currentStep="documents"
      onStepSelect={vi.fn()}
      stepStates={states}
      visitedSteps={new Set(['application', 'documents'])}
    />,
  )

  const navigation = screen.getByRole('navigation', { name: '申请向导进度' })
  expect(navigation.querySelector('ol')?.className).toContain('grid-cols-2')
  expect(navigation.querySelector('ol')?.className).toContain('sm:grid-cols-4')
  expect(screen.getByRole('button', { name: /步骤 2.*上传证明材料.*当前步骤.*尚未处理/ }).getAttribute('aria-current')).toBe('step')
  expect(screen.getByRole('button', { name: /步骤 1.*填写求助信息.*已完成.*已保存/ })).toBeTruthy()
  expect((screen.getByRole('button', { name: /步骤 3.*核对并补充信息.*需要补充.*需要补充信息/ }) as HTMLButtonElement).disabled).toBe(true)
})
