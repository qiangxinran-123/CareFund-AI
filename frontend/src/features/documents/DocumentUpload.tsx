import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/client'
import type { DocumentApi } from '../../api/documents'
import type { UploadedDocument } from '../../types/contracts'
import type { DocumentUploadState } from '../workflow/workflowStatus'
import { documentAccept, formatFileSize, validateDocumentFile } from './documentValidation'

interface Selection {
  file: File
  idempotencyKey: string
}

interface Props {
  api: DocumentApi
  applicationId: string
  disabled?: boolean
  expectedRevision: number
  maxSizeBytes?: number
  onUploaded: (document: UploadedDocument) => Promise<void> | void
  onStateChange?: (state: DocumentUploadState) => void
}

function describeUploadError(error: unknown): string {
  if (error instanceof DOMException && error.name === 'AbortError') return '上传已取消。'
  if (error instanceof ApiError) {
    if (error.kind === 'network') {
      return '网络连接中断，上传结果暂时无法确认。请先刷新材料列表确认是否已上传，再重试。'
    }
    if (error.status === 413 || error.response?.error.code === 'FILE_TOO_LARGE') {
      return `文件超过服务端允许的大小。${error.response?.error.message ? ` ${error.response.error.message}` : ''}`
    }
    if (error.status === 415 || error.response?.error.code === 'UNSUPPORTED_FILE') {
      return '这种文件暂不支持，请选择 JPG、PNG 或 PDF。'
    }
    if (error.status === 404) return '申请信息不可用，请先返回并重新保存申请。'
    if (error.status === 409) return '申请信息已更新，请刷新页面后重新上传。'
    return error.message
  }
  return error instanceof Error ? error.message : '上传失败，请稍后重试。'
}

function createIdempotencyKey(): string {
  return `upload_${crypto.randomUUID()}`
}

export function DocumentUpload({
  api,
  applicationId,
  disabled = false,
  expectedRevision,
  maxSizeBytes,
  onUploaded,
  onStateChange,
}: Props) {
  const [selection, setSelection] = useState<Selection | null>(null)
  const [validationError, setValidationError] = useState<string | null>(null)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [uploading, setUploading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const mountedRef = useRef(true)
  const uploadController = useRef<AbortController | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      uploadController.current?.abort()
    }
  }, [])

  useEffect(() => {
    onStateChange?.(uploading ? 'uploading' : message?.kind === 'error' ? 'error' : selection ? 'selected' : 'idle')
  }, [message?.kind, onStateChange, selection, uploading])

  function selectFile(file: File | undefined) {
    setMessage(null)
    if (!file) {
      setSelection(null)
      setValidationError(null)
      return
    }
    const error = validateDocumentFile(file, maxSizeBytes)
    setValidationError(error)
    setSelection(error ? null : { file, idempotencyKey: createIdempotencyKey() })
  }

  async function upload() {
    if (!selection) {
      setValidationError('请先选择要上传的文件。')
      return
    }
    if (uploading || disabled) return

    const controller = new AbortController()
    uploadController.current = controller
    setUploading(true)
    setMessage(null)
    try {
      const document = await api.upload({
        applicationId,
        expectedRevision,
        file: selection.file,
        idempotencyKey: selection.idempotencyKey,
        signal: controller.signal,
      })
      if (controller.signal.aborted || !mountedRef.current) return
      void Promise.resolve(onUploaded(document)).catch(() => undefined)
      if (!mountedRef.current) return
      setSelection(null)
      setValidationError(null)
      if (inputRef.current) inputRef.current.value = ''
      setMessage({ kind: 'success', text: '材料已上传，您可以继续添加其他材料。后续处理状态请以列表为准。' })
    } catch (error) {
      if (!controller.signal.aborted) {
        setMessage({ kind: 'error', text: describeUploadError(error) })
      }
    } finally {
      if (uploadController.current === controller) uploadController.current = null
      if (mountedRef.current) setUploading(false)
    }
  }

  return (
    <div>
      <label className="block text-sm font-medium text-slate-800" htmlFor="medical-document">选择材料</label>
      <input
        accept={documentAccept}
        className="form-control max-w-full file:mr-3 file:rounded-lg file:border-0 file:bg-blue-50 file:px-3 file:py-2 file:text-sm file:font-medium file:text-blue-800"
        disabled={disabled || uploading}
        id="medical-document"
        onChange={(event) => selectFile(event.target.files?.[0])}
        ref={inputRef}
        type="file"
      />
      <p className="field-hint">支持 JPG、PNG、PDF。文件大小限制以服务端实际提示为准。</p>

      {selection && (
        <div className="mt-4 rounded-xl border border-blue-100 bg-blue-50 p-4" aria-label="待上传文件">
          <p className="break-words text-sm font-medium leading-6 text-slate-900">{selection.file.name}</p>
          <p className="mt-1 text-xs text-slate-600">{selection.file.type} · {formatFileSize(selection.file.size)} · 尚未上传</p>
        </div>
      )}
      {validationError && <p className="field-error" role="alert">{validationError}</p>}
      {message && (
        <p className={`mt-3 text-sm ${message.kind === 'success' ? 'text-emerald-700' : 'text-red-700'}`} role={message.kind === 'error' ? 'alert' : 'status'}>
          {message.text}
        </p>
      )}

      <button className="button-primary mt-4 w-full sm:w-auto" disabled={disabled || uploading || !selection} onClick={() => void upload()} type="button">
        {uploading ? '正在上传…' : message?.kind === 'error' ? '重新上传' : message?.kind === 'success' ? '继续上传材料' : '上传材料'}
      </button>
    </div>
  )
}
