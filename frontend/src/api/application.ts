import { ApiError, apiRequest } from './client'
import type {
  ApplicationResponse,
  CreateApplicationRequest,
  UpdateApplicationRequest,
} from '../types/contracts'

export interface ApplicationApi {
  create(input: CreateApplicationRequest): Promise<ApplicationResponse>
  get(applicationId: string): Promise<ApplicationResponse>
  update(applicationId: string, input: UpdateApplicationRequest): Promise<ApplicationResponse>
}

function assertApplicationResponse(value: ApplicationResponse | undefined): ApplicationResponse {
  if (
    !value
    || typeof value !== 'object'
    || !value.application
    || typeof value.application.application_id !== 'string'
    || !Number.isInteger(value.application.revision)
    || !value.application.patient_info
    || !Array.isArray(value.documents)
    || !Array.isArray(value.evidence)
  ) {
    throw new ApiError('服务器返回的申请数据格式异常。', 'invalid_response')
  }
  return value
}

export const httpApplicationApi: ApplicationApi = {
  async create(input) {
    return assertApplicationResponse(await apiRequest<ApplicationResponse>('applications', {
      method: 'POST',
      body: input,
    }))
  },
  async get(applicationId) {
    return assertApplicationResponse(await apiRequest<ApplicationResponse>(
      `applications/${encodeURIComponent(applicationId)}`,
    ))
  },
  async update(applicationId, input) {
    return assertApplicationResponse(await apiRequest<ApplicationResponse>(
      `applications/${encodeURIComponent(applicationId)}`,
      { method: 'PATCH', body: input },
    ))
  },
}
