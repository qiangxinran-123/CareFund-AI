import { render, screen } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())

it('renders the brand and four-step layout without contacting the backend', () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)

  expect(screen.getByText('CareFund-AI')).toBeTruthy()
  expect(screen.getByRole('main')).toBeTruthy()
  expect(screen.getByRole('heading', { name: '清晰整理每一步' })).toBeTruthy()
  expect(screen.getAllByRole('listitem')).toHaveLength(4)
  expect(screen.getByText('申请功能即将开放')).toBeTruthy()
  expect(fetchMock).not.toHaveBeenCalled()
})

