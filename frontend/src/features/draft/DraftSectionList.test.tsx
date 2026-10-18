import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, it } from 'vitest'
import { document, result } from '../analysis/testFixtures'
import { draft } from './testFixtures'
import { DraftSectionList } from './DraftSectionList'

afterEach(cleanup)

it('renders multiple sections in service order and preserves original line breaks', () => {
  const analysis = result()
  render(<DraftSectionList documents={[document]} evidence={analysis.evidence} facts={analysis.facts} sections={draft().sections} />)
  const headings = screen.getAllByRole('heading', { level: 3 })
  expect(headings.map((heading) => heading.textContent)).toEqual(['病情说明', '费用说明'])
  expect(screen.getByText(/第一段内容/).className).toContain('whitespace-pre-wrap')
})

it('distinguishes user statements from document support without overstating verification', () => {
  const analysis = result()
  render(<DraftSectionList documents={[document]} evidence={analysis.evidence} facts={analysis.facts} sections={draft().sections} />)
  expect(screen.getAllByText(/来源：用户填写或自述/)).toHaveLength(1)
  expect(screen.getByText(/有材料内容支持（不代表真实性认证）/)).toBeTruthy()
  expect(screen.getByText(/费用清单.pdf/)).toBeTruthy()
})

it('degrades safely when a referenced fact is missing', () => {
  const broken = draft({ sections: [{ section_id: 's_missing', title: '缺失引用', content: '待核对内容', fact_ids: ['fact_missing'] }] })
  render(<DraftSectionList documents={[]} evidence={[]} facts={[]} sections={broken.sections} />)
  expect(screen.getByText(/关联事实暂不可用/)).toBeTruthy()
  expect(screen.getByText(/请勿据此认定内容已经证实/)).toBeTruthy()
})

it('shows an explicit empty state without inventing example content', () => {
  render(<DraftSectionList documents={[]} evidence={[]} facts={[]} sections={[]} />)
  expect(screen.getByText(/没有可显示的章节/)).toBeTruthy()
})
