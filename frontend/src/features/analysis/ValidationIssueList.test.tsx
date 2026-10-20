import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { ValidationIssueList } from './ValidationIssueList'
import { result } from './testFixtures'

it('groups missing, conflict, and unsupported issues and preserves severity meaning', () => {
  render(<ValidationIssueList issues={result().validation.issues} />)
  expect(screen.getByText('需要补充')).toBeTruthy()
  expect(screen.getByText('需要核对')).toBeTruthy()
  expect(screen.getByText('需要先处理')).toBeTruthy()
  expect(screen.getByText('需要关注')).toBeTruthy()
  expect(screen.getByText('提醒')).toBeTruthy()
  expect(screen.getByText('目前仅来自用户自述')).toBeTruthy()
  expect(screen.queryByText(/审核未通过|通过率/)).toBeNull()
})

it('shows a neutral empty state without claiming approval', () => {
  render(<ValidationIssueList issues={[]} />)
  expect(screen.getByText('目前没有需要补充或核对的信息。这不代表平台审核通过。')).toBeTruthy()
})
