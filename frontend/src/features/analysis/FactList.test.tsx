import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { FactList } from './FactList'
import { document, result } from './testFixtures'

it('shows normal facts, user statements, supported material, conflicts, and evidence', () => {
  const analysis = result()
  render(<FactList documents={[document]} evidence={analysis.evidence} facts={analysis.facts} />)
  expect(screen.getByText('用户自述内容')).toBeTruthy()
  expect(screen.getByText('还需要确认')).toBeTruthy()
  expect(screen.getByText('材料内容支持')).toBeTruthy()
  expect(screen.getByText('信息有出入')).toBeTruthy()
  expect(screen.getByText('费用清单.pdf · 第 2 页')).toBeTruthy()
  expect(screen.getByText('相关内容：费用合计 12,500 元')).toBeTruthy()
  expect(screen.getByText('证据来源暂不可用')).toBeTruthy()
  expect(screen.queryByText(/医疗机构认证通过/)).toBeNull()
})

it('safely falls back for an unknown field, missing document, and unsupported fact', () => {
  const analysis = result()
  const fact = { ...analysis.facts[1], field: 'custom.unknown', verification_status: 'unsupported' as const }
  render(<FactList documents={[]} evidence={analysis.evidence} facts={[fact]} />)
  expect(screen.getByText(/申请信息 · 来源/)).toBeTruthy()
  expect(screen.getByText('暂无材料支持')).toBeTruthy()
  expect(screen.getByText('材料来源暂不可用 · 第 2 页')).toBeTruthy()
})

it('shows an actionable empty state', () => {
  render(<FactList documents={[]} evidence={[]} facts={[]} />)
  expect(screen.getByText(/暂时还没有可展示的信息/)).toBeTruthy()
})
