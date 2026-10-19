import type { Draft, ExportResponse } from '../../types/contracts'
import { application } from '../analysis/testFixtures'

export function draft(overrides: Partial<Draft> = {}): Draft {
  return {
    schema_version: '1.0', draft_id: 'draft_test_001', application_id: application.application_id,
    application_revision: application.revision, draft_revision: 2, status: 'generated',
    sections: [
      { section_id: 'section_summary', title: '病情说明', content: '第一段内容。\n第二段内容。', fact_ids: ['fact_user'] },
      { section_id: 'section_cost', title: '费用说明', content: '预计费用内容。', fact_ids: ['fact_cost'] },
    ],
    created_at: '2026-10-17T03:00:00Z', confirmed_at: null,
    ...overrides,
  }
}

export function exportResponse(overrides: Partial<ExportResponse> = {}): ExportResponse {
  return {
    export_id: 'export_test_001', application_id: application.application_id, draft_id: 'draft_test_001',
    format: 'json', created_at: '2026-10-17T04:00:00Z', download_url: 'https://example.test/download/export.json',
    ...overrides,
  }
}
