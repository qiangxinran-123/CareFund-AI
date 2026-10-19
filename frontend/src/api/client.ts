import type { ErrorResponse } from '../types/contracts'

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE'
export type ApiErrorKind = 'http' | 'network' | 'invalid_response'

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly kind: ApiErrorKind,
    public readonly status?: number,
    public readonly response?: ErrorResponse,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export interface RequestOptions {
  method?: HttpMethod
  body?: unknown | FormData
  headers?: HeadersInit
  signal?: AbortSignal
}

const errorCodes = new Set([
  'INVALID_REQUEST', 'RESOURCE_NOT_FOUND', 'UNSUPPORTED_FILE',
  'FILE_TOO_LARGE', 'OCR_FAILED', 'AGENT_UNAVAILABLE',
  'VALIDATION_FAILED', 'STATE_CONFLICT', 'EXPORT_BLOCKED', 'INTERNAL_ERROR',
])

function isErrorResponse(value: unknown): value is ErrorResponse {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  if (typeof candidate.request_id !== 'string') return false
  const error = candidate.error
  if (typeof error !== 'object' || error === null) return false
  const data = error as Record<string, unknown>
  return typeof data.code === 'string' && errorCodes.has(data.code)
    && typeof data.message === 'string'
    && Array.isArray(data.details)
    && data.details.every((detail: unknown) =>
      typeof detail === 'object' && detail !== null
      && typeof (detail as Record<string, unknown>).message === 'string')
}

const baseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers)
  const hasBody = options.body !== undefined
  const isFormData = options.body instanceof FormData
  if (hasBody && !isFormData && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  if (isFormData) headers.delete('Content-Type')
  if (!headers.has('Accept')) headers.set('Accept', 'application/json')

  let response: Response
  try {
    response = await fetch(`${baseUrl}/${path.replace(/^\/+/, '')}`, {
      method: options.method || 'GET',
      headers,
      body: !hasBody ? undefined : isFormData ? options.body as FormData : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw new ApiError('网络请求失败，请检查连接后重试。', 'network')
  }

  const raw = await response.text()
  let data: unknown
  if (raw) {
    try {
      data = JSON.parse(raw)
    } catch {
      throw new ApiError('服务器返回了无效的 JSON 响应。', 'invalid_response', response.status)
    }
  }

  if (!response.ok) {
    const contractError = isErrorResponse(data) ? data : undefined
    throw new ApiError(
      contractError?.error.message || `请求失败（HTTP ${response.status}）。`,
      'http',
      response.status,
      contractError,
    )
  }
  return data as T
}

