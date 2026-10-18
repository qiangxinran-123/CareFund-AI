import { fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { DraftExport } from './DraftExport'

it('does not claim a file is ready when the export response has no download address', () => {
  render(
    <DraftExport
      blockedReason={null}
      exporting={false}
      mockMode={false}
      onExport={vi.fn()}
      result={{
        export_id: 'export_1',
        application_id: 'app_1',
        draft_id: 'draft_1',
        format: 'json',
        created_at: '2026-10-18T00:00:00Z',
        download_url: null,
      }}
    />,
  )

  expect(screen.getByText('已收到导出结果，但服务端未提供下载地址。')).toBeTruthy()
  expect(screen.queryByText('申请资料包已准备好，请下载保存。')).toBeNull()
  expect(screen.queryByRole('link', { name: '下载申请资料包' })).toBeNull()
})

it('uses an action-oriented export label without changing the export callback', () => {
  const onExport = vi.fn()
  render(<DraftExport blockedReason={null} exporting={false} mockMode={false} onExport={onExport} result={null} />)

  fireEvent.click(screen.getByRole('button', { name: '导出申请资料包' }))
  expect(onExport).toHaveBeenCalledTimes(1)
})
