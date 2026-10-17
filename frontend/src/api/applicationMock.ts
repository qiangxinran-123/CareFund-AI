import type { ApplicationApi } from './application'
import { ApiError } from './client'
import type { ApplicationResponse, ErrorCode, PatientInfo, UploadedDocument } from '../types/contracts'

let current: ApplicationResponse | null = null

function mockError(status: number, code: ErrorCode, message: string): ApiError {
  return new ApiError(message, 'http', status, {
    error: { code, message, details: [] },
    request_id: 'req_mock_documents',
  })
}

function now(): string {
  return new Date().toISOString()
}

function snapshot(patientInfo: PatientInfo, revision: number): ApplicationResponse {
  const createdAt = current?.application.created_at ?? now()
  return {
    application: {
      application_id: 'app_mock_local',
      schema_version: '1.0',
      revision,
      status: 'collecting',
      patient_info: patientInfo,
      created_at: createdAt,
      updated_at: now(),
    },
    documents: current?.documents ?? [],
    evidence: current?.evidence ?? [],
  }
}

export const mockApplicationApi: ApplicationApi = {
  async create(input) {
    current = null
    current = snapshot(input.patient_info, 1)
    return structuredClone(current)
  },
  async get(applicationId) {
    if (!current || current.application.application_id !== applicationId) {
      throw mockError(404, 'RESOURCE_NOT_FOUND', 'Mock 模式中没有可恢复的申请。')
    }
    return structuredClone(current)
  },
  async update(applicationId, input) {
    if (!current || current.application.application_id !== applicationId) {
      throw mockError(404, 'RESOURCE_NOT_FOUND', 'Mock 模式中没有可更新的申请。')
    }
    if (input.expected_revision !== current.application.revision) {
      throw mockError(409, 'STATE_CONFLICT', 'Mock 申请版本已变化，请重新加载。')
    }
    current = snapshot({ ...current.application.patient_info, ...input.patient_info }, input.expected_revision + 1)
    return structuredClone(current)
  },
}

export function getMockDocuments(applicationId: string): UploadedDocument[] {
  if (!current || current.application.application_id !== applicationId) {
    throw mockError(404, 'RESOURCE_NOT_FOUND', 'Mock 模式中没有对应申请。')
  }
  return structuredClone(current.documents)
}

export function appendMockDocument(
  applicationId: string,
  expectedRevision: number,
  document: UploadedDocument,
): void {
  if (!current || current.application.application_id !== applicationId) {
    throw mockError(404, 'RESOURCE_NOT_FOUND', 'Mock 模式中没有对应申请。')
  }
  if (current.application.revision !== expectedRevision) {
    throw mockError(409, 'STATE_CONFLICT', '申请版本已变化，请先刷新申请后再上传。')
  }
  current = {
    ...current,
    application: {
      ...current.application,
      revision: current.application.revision + 1,
      updated_at: now(),
    },
    documents: [...current.documents, document],
  }
}

export function resetMockApplication(): void {
  current = null
}
