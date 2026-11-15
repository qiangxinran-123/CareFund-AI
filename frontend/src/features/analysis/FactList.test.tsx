import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { FactList } from './FactList'
import { document, result } from './testFixtures'

afterEach(cleanup)

it('shows normal facts, user statements, supported material, conflicts, and evidence', () => {
  const analysis = result()
  render(<FactList documents={[document]} evidence={analysis.evidence} facts={analysis.facts} />)
  expect(screen.getByText('用户自述内容')).toBeTruthy()
  expect(screen.getByText('pending · 待核对')).toBeTruthy()
  expect(screen.getByText('supported · 有材料支持')).toBeTruthy()
  expect(screen.getByText('conflicting · 信息有出入')).toBeTruthy()
  expect(screen.getByText('来源：用户输入')).toBeTruthy()
  expect(screen.getAllByText('来源：上传材料')).toHaveLength(2)
  expect(screen.getByText('用户已确认')).toBeTruthy()
  expect(screen.getAllByText('等待用户确认')).toHaveLength(2)
  expect(screen.getByText('费用清单.pdf · 第 2 页')).toBeTruthy()
  expect(screen.getByText('提取方式：OCR 识别')).toBeTruthy()
  expect(screen.getByTestId('fact-fact_cost')).toHaveProperty('textContent', expect.stringContaining('原始 OCR/文本片段：费用合计 12,500 元'))
  expect(screen.getByText(/该事实来自用户输入，没有关联材料片段/)).toBeTruthy()
  expect(screen.getByText('证据来源暂不可用')).toBeTruthy()
  expect(screen.queryByText(/医疗机构认证通过/)).toBeNull()
})

it('keeps multiple reliably related issues next to one fact without repeating the fact content', () => {
  const analysis = result()
  const relatedIssues = [
    analysis.validation.issues[1],
    { ...analysis.validation.issues[1], issue_id: 'issue_conflict_2', message: '请补充日期依据' },
  ]
  const view = render(<FactList documents={[document]} evidence={analysis.evidence} facts={analysis.facts} issues={relatedIssues} />)

  const firstIssue = screen.getByTestId('validation-issue-issue_conflict')
  const secondIssue = screen.getByTestId('validation-issue-issue_conflict_2')
  expect(within(firstIssue).getByText('日期信息不一致')).toBeTruthy()
  expect(within(secondIssue).getByText('请补充日期依据')).toBeTruthy()
  expect(within(view.container).getAllByTestId('fact-fact_conflict')).toHaveLength(1)
})

it('safely falls back for an unknown field, missing document, and unsupported fact', () => {
  const analysis = result()
  const fact = { ...analysis.facts[1], field: 'custom.unknown', verification_status: 'unsupported' as const }
  render(<FactList documents={[]} evidence={analysis.evidence} facts={[fact]} />)
  expect(screen.getByText('申请信息')).toBeTruthy()
  expect(screen.getByText('来源：上传材料')).toBeTruthy()
  expect(screen.getByText('unsupported · 暂无材料支持')).toBeTruthy()
  expect(screen.getByText('材料来源暂不可用 · 第 2 页')).toBeTruthy()
})

it('shows an actionable empty state', () => {
  render(<FactList documents={[]} evidence={[]} facts={[]} />)
  expect(screen.getByText(/暂时还没有可展示的信息/)).toBeTruthy()
})
