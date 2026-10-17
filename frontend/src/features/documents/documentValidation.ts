import type { DocumentMediaType } from '../../types/contracts'

export const acceptedDocumentTypes = ['image/jpeg', 'image/png', 'application/pdf'] as const
export const documentAccept = acceptedDocumentTypes.join(',')

const acceptedTypes = new Set<string>(acceptedDocumentTypes)

export interface FileMetadata {
  name: string
  type: string
  size: number
}

export function validateDocumentFile(file: FileMetadata, maxSizeBytes?: number): string | null {
  if (!file.name.trim() || !Number.isFinite(file.size) || file.size < 0 || typeof file.type !== 'string') {
    return '文件信息无效，请重新选择文件。'
  }
  if (!acceptedTypes.has(file.type)) {
    return '仅支持 JPEG、PNG 或 PDF 文件。'
  }
  if (file.size === 0) {
    return '不能上传空文件。'
  }
  if (maxSizeBytes !== undefined && file.size > maxSizeBytes) {
    return `文件超过当前确认的大小限制（${formatFileSize(maxSizeBytes)}）。`
  }
  return null
}

export function isDocumentMediaType(value: string): value is DocumentMediaType {
  return acceptedTypes.has(value)
}

export function formatFileSize(sizeBytes: number): string {
  if (sizeBytes < 1024) return `${sizeBytes} B`
  if (sizeBytes < 1024 ** 2) return `${(sizeBytes / 1024).toFixed(1)} KB`
  return `${(sizeBytes / 1024 ** 2).toFixed(1)} MB`
}
