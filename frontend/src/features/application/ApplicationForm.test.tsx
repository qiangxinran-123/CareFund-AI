import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ApplicationApi } from '../../api/application'
import type { ApplicationResponse } from '../../types/contracts'
import { ApplicationForm } from './ApplicationForm'

function response(revision = 1, displayName = '虚构称呼'): ApplicationResponse {
  return {
    application: {
      application_id: 'app_test_001',
      schema_version: '1.0',
      revision,
      status: 'collecting',
      patient_info: { display_name: displayName, age_group: null, medical_summary: '虚构的用户自述内容' },
      created_at: '2026-10-17T01:00:00Z',
      updated_at: '2026-10-17T01:00:00Z',
    },
    documents: [],
    evidence: [],
  }
}

function api(overrides: Partial<ApplicationApi> = {}): ApplicationApi {
  return {
    create: vi.fn().mockResolvedValue(response()),
    get: vi.fn().mockResolvedValue(response()),
    update: vi.fn().mockResolvedValue(response(2)),
    ...overrides,
  }
}

function fillRequiredAndReachFinalStep() {
  fireEvent.change(screen.getByLabelText(/患者称呼/), { target: { value: '虚构申请人称呼' } })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.change(screen.getByLabelText(/病情与治疗情况自述/), { target: { value: '这是一段虚构的用户自述。' } })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
}

beforeEach(() => window.localStorage.clear())
afterEach(cleanup)

it('renders the first of three steps', () => {
  render(<ApplicationForm api={api()} />)
  expect(screen.getByRole('heading', { name: '填写申请信息' })).toBeTruthy()
  expect(screen.getByText('1. 基本信息').getAttribute('aria-current')).toBe('step')
  expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('1')
})

it('blocks missing required input and clears the error after editing', () => {
  render(<ApplicationForm api={api()} />)
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  expect(screen.getByText('请填写患者称呼。')).toBeTruthy()
  expect(screen.getByText('1. 基本信息').getAttribute('aria-current')).toBe('step')

  fireEvent.change(screen.getByLabelText(/患者称呼/), { target: { value: '修正后的称呼' } })
  expect(screen.queryByText('请填写患者称呼。')).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  expect(screen.getByText('2. 医疗情况').getAttribute('aria-current')).toBe('step')
})

it('uses Enter to advance instead of saving before the final step', () => {
  const create = vi.fn().mockResolvedValue(response())
  render(<ApplicationForm api={api({ create })} />)
  const nameInput = screen.getByLabelText(/患者称呼/)
  fireEvent.change(nameInput, { target: { value: '键盘操作称呼' } })
  fireEvent.submit(nameInput.closest('form')!)
  expect(screen.getByText('2. 医疗情况').getAttribute('aria-current')).toBe('step')
  expect(create).not.toHaveBeenCalled()
})

it('switches all steps and retains values when going back', () => {
  render(<ApplicationForm api={api()} />)
  fillRequiredAndReachFinalStep()
  expect(screen.getByText('3. 资金情况').getAttribute('aria-current')).toBe('step')
  expect(screen.getByText('当前统一接口契约暂未开放资金字段')).toBeTruthy()

  fireEvent.click(screen.getByRole('button', { name: '上一步' }))
  expect((screen.getByLabelText(/病情与治疗情况自述/) as HTMLTextAreaElement).value).toBe('这是一段虚构的用户自述。')
  fireEvent.click(screen.getByRole('button', { name: '上一步' }))
  expect((screen.getByLabelText(/患者称呼/) as HTMLInputElement).value).toBe('虚构申请人称呼')
})

it('shows and then clears a long-text validation error', () => {
  render(<ApplicationForm api={api()} />)
  fireEvent.change(screen.getByLabelText(/患者称呼/), { target: { value: '虚构称呼' } })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.change(screen.getByLabelText(/病情与治疗情况自述/), { target: { value: '述'.repeat(2001) } })
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  expect(screen.getByText('病情自述不能超过 2000 个字符。')).toBeTruthy()
  fireEvent.change(screen.getByLabelText(/病情与治疗情况自述/), { target: { value: '已修正' } })
  expect(screen.queryByText('病情自述不能超过 2000 个字符。')).toBeNull()
})

it('prevents duplicate submission while saving', async () => {
  let finish!: (value: ApplicationResponse) => void
  const create = vi.fn(() => new Promise<ApplicationResponse>((resolve) => { finish = resolve }))
  render(<ApplicationForm api={api({ create })} />)
  fillRequiredAndReachFinalStep()

  fireEvent.click(screen.getByRole('button', { name: '保存申请' }))
  const savingButton = screen.getByRole('button', { name: '保存中…' }) as HTMLButtonElement
  expect(savingButton.disabled).toBe(true)
  fireEvent.click(savingButton)
  expect(create).toHaveBeenCalledTimes(1)

  await act(async () => { finish(response()) })
  expect(await screen.findByText('申请已保存（版本 1）。')).toBeTruthy()
  expect(window.localStorage.getItem('carefund.application_id')).toBe('app_test_001')
})

it('keeps user input after a save failure', async () => {
  const create = vi.fn().mockRejectedValue(new Error('服务暂不可用'))
  render(<ApplicationForm api={api({ create })} />)
  fillRequiredAndReachFinalStep()
  fireEvent.click(screen.getByRole('button', { name: '保存申请' }))
  expect(await screen.findByRole('alert')).toHaveProperty('textContent', '服务暂不可用')

  fireEvent.click(screen.getByRole('button', { name: '上一步' }))
  fireEvent.click(screen.getByRole('button', { name: '上一步' }))
  expect((screen.getByLabelText(/患者称呼/) as HTMLInputElement).value).toBe('虚构申请人称呼')
})

it('restores saved server data and updates with the current revision', async () => {
  window.localStorage.setItem('carefund.application_id', 'app_test_001')
  const get = vi.fn().mockResolvedValue(response(4, '服务端保存称呼'))
  const update = vi.fn().mockResolvedValue(response(5, '服务端保存称呼'))
  render(<ApplicationForm api={api({ get, update })} />)

  expect(await screen.findByText('已恢复已保存的申请（版本 4）。')).toBeTruthy()
  expect((screen.getByLabelText(/患者称呼/) as HTMLInputElement).value).toBe('服务端保存称呼')
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '保存修改' }))
  await screen.findByText('申请已保存（版本 5）。')
  expect(update).toHaveBeenCalledWith('app_test_001', expect.objectContaining({ expected_revision: 4 }))
})

it('uses a refreshed attachment revision without overwriting current form input', async () => {
  window.localStorage.setItem('carefund.application_id', 'app_test_001')
  const update = vi.fn().mockResolvedValue(response(6, '用户正在编辑的称呼'))
  const applicationApi = api({ get: vi.fn().mockResolvedValue(response(4, '初始称呼')), update })
  const { rerender } = render(<ApplicationForm api={applicationApi} />)
  await screen.findByText('已恢复已保存的申请（版本 4）。')
  fireEvent.change(screen.getByLabelText(/患者称呼/), { target: { value: '用户正在编辑的称呼' } })

  rerender(<ApplicationForm api={applicationApi} applicationSnapshot={response(5).application} />)
  expect((screen.getByLabelText(/患者称呼/) as HTMLInputElement).value).toBe('用户正在编辑的称呼')
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '下一步' }))
  fireEvent.click(screen.getByRole('button', { name: '保存修改' }))
  await screen.findByText('申请已保存（版本 6）。')
  expect(update).toHaveBeenCalledWith('app_test_001', expect.objectContaining({ expected_revision: 5 }))
})
