import type {
  Draft,
  DraftConfirmationRequest,
  DraftGenerationRequest,
  ExportRequest,
  ExportResponse,
} from '../types/contracts'
import { ApiError, apiRequest } from './client'

export interface DraftApi {
  generate(applicationId: string, input: DraftGenerationRequest, signal?: AbortSignal): Promise<Draft>
  getLatest(applicationId: string, signal?: AbortSignal): Promise<Draft>
  confirm(applicationId: string, input: DraftConfirmationRequest, signal?: AbortSignal): Promise<Draft>
  exportApplication(applicationId: string, input: ExportRequest, signal?: AbortSignal): Promise<ExportResponse>
}

const statuses = new Set(['generated', 'confirmed', 'stale'])

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : null
}

function positiveInteger(value: unknown): boolean {
  return Number.isInteger(value) && Number(value) >= 1
}

function utcDate(value: unknown): boolean {
  return typeof value === 'string' && value.endsWith('Z') && !Number.isNaN(Date.parse(value))
}

export function assertDraft(value: unknown): Draft {
  const item = record(value)
  const sectionsValid = Array.isArray(item?.sections) && item.sections.length > 0 && item.sections.every((entry) => {
    const section = record(entry)
    return section
      && typeof section.section_id === 'string' && section.section_id.length > 0
      && typeof section.title === 'string' && section.title.length > 0
      && typeof section.content === 'string' && section.content.length > 0
      && Array.isArray(section.fact_ids) && section.fact_ids.length > 0
      && section.fact_ids.every((id) => typeof id === 'string' && id.length > 0)
      && new Set(section.fact_ids).size === section.fact_ids.length
  })
  if (!item || item.schema_version !== '1.0' || typeof item.draft_id !== 'string'
    || typeof item.application_id !== 'string' || !positiveInteger(item.application_revision)
    || !positiveInteger(item.draft_revision) || !statuses.has(item.status as string)
    || !sectionsValid || !utcDate(item.created_at)
    || (item.confirmed_at !== undefined && item.confirmed_at !== null && !utcDate(item.confirmed_at))) {
    throw new ApiError('服务器返回的草稿格式异常。', 'invalid_response')
  }
  return value as Draft
}

export function assertExportResponse(value: unknown): ExportResponse {
  const item = record(value)
  const validUrl = item?.download_url === null || (typeof item?.download_url === 'string' && item.download_url.length > 0)
  if (!item || typeof item.export_id !== 'string' || typeof item.application_id !== 'string'
    || typeof item.draft_id !== 'string' || item.format !== 'json' || !utcDate(item.created_at)
    || !validUrl) {
    throw new ApiError('服务器返回的导出结果格式异常。', 'invalid_response')
  }
  return value as ExportResponse
}

function applicationPath(applicationId: string, suffix: string): string {
  return `applications/${encodeURIComponent(applicationId)}/${suffix}`
}

export const httpDraftApi: DraftApi = {
  async generate(applicationId, input, signal) {
    return assertDraft(await apiRequest(applicationPath(applicationId, 'draft'), {
      method: 'POST', body: input, signal,
    }))
  },
  async getLatest(applicationId, signal) {
    return assertDraft(await apiRequest(applicationPath(applicationId, 'draft'), { signal }))
  },
  async confirm(applicationId, input, signal) {
    return assertDraft(await apiRequest(applicationPath(applicationId, 'draft/confirm'), {
      method: 'POST', body: input, signal,
    }))
  },
  async exportApplication(applicationId, input, signal) {
    return assertExportResponse(await apiRequest(applicationPath(applicationId, 'export'), {
      method: 'POST', body: input, signal,
    }))
  },
}
