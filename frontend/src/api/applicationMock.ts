import type { ApplicationApi } from './application'
import type { ApplicationResponse, PatientInfo } from '../types/contracts'

let current: ApplicationResponse | null = null

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
    documents: [],
    evidence: [],
  }
}

export const mockApplicationApi: ApplicationApi = {
  async create(input) {
    current = snapshot(input.patient_info, 1)
    return structuredClone(current)
  },
  async get(applicationId) {
    if (!current || current.application.application_id !== applicationId) {
      throw new Error('Mock 模式中没有可恢复的申请。')
    }
    return structuredClone(current)
  },
  async update(applicationId, input) {
    if (!current || current.application.application_id !== applicationId) {
      throw new Error('Mock 模式中没有可更新的申请。')
    }
    if (input.expected_revision !== current.application.revision) {
      throw new Error('Mock 申请版本已变化，请重新加载。')
    }
    current = snapshot({ ...current.application.patient_info, ...input.patient_info }, input.expected_revision + 1)
    return structuredClone(current)
  },
}

export function resetMockApplication(): void {
  current = null
}
