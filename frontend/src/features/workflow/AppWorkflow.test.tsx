import { useEffect, useState } from 'react'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'

const mounts = vi.hoisted(() => ({ analysis: 0, documents: 0, draft: 0 }))

vi.mock('../application/ApplicationForm', () => ({
  ApplicationForm: ({ onApplicationChange }: { onApplicationChange?: (application: unknown) => void }) => (
    <section>
      <h2 tabIndex={-1}>填写申请信息</h2>
      <label>测试申请内容<input aria-label="测试申请内容" /></label>
      <button onClick={() => onApplicationChange?.({
        application_id: 'app_test_001',
        schema_version: '1.0',
        revision: 1,
        status: 'collecting',
        patient_info: { display_name: '测试', age_group: null, medical_summary: '测试病情' },
        created_at: '2026-10-17T01:00:00Z',
        updated_at: '2026-10-17T01:00:00Z',
      })} type="button">模拟保存申请</button>
    </section>
  ),
}))

vi.mock('../documents/DocumentManager', () => ({
  DocumentManager: () => {
    useEffect(() => { mounts.documents += 1 }, [])
    const [value, setValue] = useState('')
    return <section><h2 tabIndex={-1}>上传医疗材料</h2><input aria-label="待上传材料说明" onChange={(event) => setValue(event.target.value)} value={value} /></section>
  },
}))

vi.mock('../analysis/AnalysisPanel', () => ({
  AnalysisPanel: () => {
    useEffect(() => { mounts.analysis += 1 }, [])
    return <section><h2 tabIndex={-1}>核对申请信息</h2></section>
  },
}))

vi.mock('../draft/DraftPanel', () => ({
  DraftPanel: () => {
    useEffect(() => { mounts.draft += 1 }, [])
    return <section><h2 tabIndex={-1}>预览并确认申请草稿</h2></section>
  },
}))

function workflowPanel(step: string): HTMLDivElement {
  return document.querySelector(`[data-workflow-panel="${step}"]`) as HTMLDivElement
}

function saveApplication() {
  fireEvent.click(screen.getByRole('button', { name: '模拟保存申请' }))
}

function next() {
  fireEvent.click(screen.getByRole('button', { name: /下一步：/ }))
}

beforeEach(() => {
  mounts.analysis = 0
  mounts.documents = 0
  mounts.draft = 0
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: vi.fn() })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('four-step application workflow', () => {
  it('starts on only the application page and highlights the first outer step', () => {
    render(<App />)
    expect(workflowPanel('application').hidden).toBe(false)
    expect(workflowPanel('documents').hidden).toBe(true)
    expect(workflowPanel('analysis').hidden).toBe(true)
    expect(workflowPanel('draft').hidden).toBe(true)
    expect(screen.getByRole('button', { name: /步骤 1.*填写求助信息/ }).getAttribute('aria-current')).toBe('step')
  })

  it('does not offer a previous action on the first step', () => {
    render(<App />)
    expect(screen.queryByRole('button', { name: /上一步：/ })).toBeNull()
  })

  it('blocks moving past an unsaved application with a clear message', () => {
    render(<App />)
    next()
    expect(screen.getByRole('alert')).toHaveProperty('textContent', '请先完成申请信息的三步填写并成功保存，再进入材料上传。')
    expect(workflowPanel('application').hidden).toBe(false)
  })

  it('unlocks the documents page after save and supports previous navigation', () => {
    render(<App />)
    saveApplication()
    next()
    expect(workflowPanel('documents').hidden).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: /上一步：填写求助信息/ }))
    expect(workflowPanel('application').hidden).toBe(false)
  })

  it('keeps future step buttons disabled until they are visited in order', () => {
    render(<App />)
    expect((screen.getByRole('button', { name: /步骤 2.*上传证明材料/ }) as HTMLButtonElement).disabled).toBe(true)
    saveApplication()
    next()
    expect((screen.getByRole('button', { name: /步骤 2.*上传证明材料/ }) as HTMLButtonElement).disabled).toBe(false)
    expect((screen.getByRole('button', { name: /步骤 3.*核对并补充信息/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('allows safe return to any visited step from the progress navigation', () => {
    render(<App />)
    saveApplication()
    next()
    next()
    fireEvent.click(screen.getByRole('button', { name: /步骤 1.*填写求助信息/ }))
    fireEvent.click(screen.getByRole('button', { name: /步骤 3.*核对并补充信息/ }))
    expect(workflowPanel('analysis').hidden).toBe(false)
  })

  it('does not render an ineffective next action on the fourth step', () => {
    render(<App />)
    saveApplication()
    next()
    next()
    next()
    expect(workflowPanel('draft').hidden).toBe(false)
    expect(screen.queryByRole('button', { name: /下一步：/ })).toBeNull()
  })

  it('keeps all panels mounted so local input and in-flight work survive navigation', () => {
    render(<App />)
    saveApplication()
    next()
    fireEvent.change(screen.getByLabelText('待上传材料说明'), { target: { value: '尚未提交的本地选择' } })
    next()
    fireEvent.click(screen.getByRole('button', { name: /步骤 2.*上传证明材料/ }))
    expect((screen.getByLabelText('待上传材料说明') as HTMLInputElement).value).toBe('尚未提交的本地选择')
    expect(mounts).toEqual({ analysis: 1, documents: 1, draft: 1 })
  })

  it('moves focus to the new page title and scrolls its panel into view', () => {
    render(<App />)
    saveApplication()
    next()
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: '上传医疗材料' }))
    expect(workflowPanel('documents').scrollIntoView).toHaveBeenCalledWith({ block: 'start' })
  })
})
