import type { DraftApi } from './draft'
import { ApiError } from './client'
import { getMockLatestAnalysis } from './analysisMock'
import { mockApplicationApi } from './applicationMock'
import type { Draft, ErrorCode, ExportResponse } from '../types/contracts'

const drafts = new Map<string, Draft>()
let draftSequence = 0
let exportSequence = 0

function mockError(status: number, code: ErrorCode, message: string): ApiError {
  return new ApiError(message, 'http', status, {
    error: { code, message, details: [] },
    request_id: 'req_mock_draft',
  })
}

function ensureActive(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError')
}

async function currentRevision(applicationId: string): Promise<number> {
  return (await mockApplicationApi.get(applicationId)).application.revision
}

function currentDraft(applicationId: string): Draft | undefined {
  return drafts.get(applicationId)
}

export const mockDraftApi: DraftApi = {
  async generate(applicationId, input, signal) {
    ensureActive(signal)
    const revision = await currentRevision(applicationId)
    if (revision !== input.expected_revision) {
      throw mockError(409, 'STATE_CONFLICT', '申请版本已变化，请刷新后重新生成草稿。')
    }
    const analysis = getMockLatestAnalysis(applicationId)
    if (!analysis || analysis.application_revision !== revision) {
      throw mockError(409, 'STATE_CONFLICT', '当前申请尚无有效分析结果，请先完成分析。')
    }
    draftSequence += 1
    const draft: Draft = {
      schema_version: '1.0',
      draft_id: `draft_mock_${draftSequence}`,
      application_id: applicationId,
      application_revision: revision,
      draft_revision: (currentDraft(applicationId)?.draft_revision ?? 0) + 1,
      status: 'generated',
      sections: [
        {
          section_id: 'section_mock_treatment',
          title: '病情与治疗情况',
          content: '以下为完全虚构的 Mock 草稿内容。\n患者目前正在接受示例性治疗，具体情况请以用户核对结果为准。',
          fact_ids: ['fact_mock_summary'],
        },
        {
          section_id: 'section_mock_cost',
          title: '费用情况',
          content: '虚构示例材料中记录了预计治疗费用。\n该金额仅用于演示事实与材料来源的关联。',
          fact_ids: ['fact_mock_cost'],
        },
      ],
      created_at: new Date().toISOString(),
      confirmed_at: null,
    }
    drafts.set(applicationId, draft)
    return structuredClone(draft)
  },
  async getLatest(applicationId, signal) {
    ensureActive(signal)
    const draft = currentDraft(applicationId)
    if (!draft) throw mockError(404, 'RESOURCE_NOT_FOUND', '当前申请尚无草稿。')
    const revision = await currentRevision(applicationId)
    return structuredClone(revision === draft.application_revision ? draft : { ...draft, status: 'stale' })
  },
  async confirm(applicationId, input, signal) {
    ensureActive(signal)
    const revision = await currentRevision(applicationId)
    const draft = currentDraft(applicationId)
    if (!draft || draft.draft_id !== input.draft_id || draft.draft_revision !== input.draft_revision
      || revision !== input.expected_application_revision || draft.application_revision !== revision) {
      throw mockError(409, 'STATE_CONFLICT', '草稿或申请版本已变化，请重新生成草稿。')
    }
    const analysis = getMockLatestAnalysis(applicationId)
    if (!analysis?.validation.can_finalize) {
      throw mockError(422, 'VALIDATION_FAILED', '仍有阻断性问题，暂时不能确认草稿。')
    }
    const confirmed = { ...draft, status: 'confirmed' as const, confirmed_at: new Date().toISOString() }
    drafts.set(applicationId, confirmed)
    return structuredClone(confirmed)
  },
  async exportApplication(applicationId, input, signal) {
    ensureActive(signal)
    const revision = await currentRevision(applicationId)
    const draft = currentDraft(applicationId)
    const analysis = getMockLatestAnalysis(applicationId)
    if (!draft || draft.status !== 'confirmed' || draft.draft_id !== input.draft_id
      || draft.draft_revision !== input.draft_revision || revision !== input.expected_application_revision
      || draft.application_revision !== revision) {
      throw mockError(409, 'STATE_CONFLICT', '草稿未确认或版本已变化，无法导出。')
    }
    if (!analysis?.validation.can_finalize) {
      throw mockError(422, 'EXPORT_BLOCKED', '当前校验结果不允许导出。')
    }
    exportSequence += 1
    const response: ExportResponse = {
      export_id: `export_mock_${exportSequence}`,
      application_id: applicationId,
      draft_id: draft.draft_id,
      format: 'json',
      created_at: new Date().toISOString(),
      download_url: null,
    }
    return response
  },
}

export function resetMockDraft(): void {
  drafts.clear()
  draftSequence = 0
  exportSequence = 0
}
