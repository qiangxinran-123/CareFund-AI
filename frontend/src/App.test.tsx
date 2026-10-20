import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => vi.unstubAllGlobals())
beforeEach(() => window.localStorage.clear())

it('renders the brand, overall flow, and application form without contacting the backend', () => {
  const fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
  render(<App />)

  expect(screen.getByText('CareFund-AI')).toBeTruthy()
  expect(screen.getByRole('main')).toBeTruthy()
  expect(screen.getByRole('heading', { name: '清晰整理每一步' })).toBeTruthy()
  expect(screen.getByRole('heading', { name: '填写求助信息' })).toBeTruthy()
  expect(screen.getByText('1. 基本信息')).toBeTruthy()
  expect(screen.getByRole('button', { name: /步骤 2.*上传证明材料/ })).toBeTruthy()
  expect(fetchMock).not.toHaveBeenCalled()
})

