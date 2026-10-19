import { expect, it } from 'vitest'
import { validateDocumentFile } from './documentValidation'

function file(name: string, type: string, size = 10) {
  return { name, type, size }
}

it.each([
  ['scan.jpg', 'image/jpeg'],
  ['scan.png', 'image/png'],
  ['record.pdf', 'application/pdf'],
])('accepts a valid %s document', (name, type) => {
  expect(validateDocumentFile(file(name, type))).toBeNull()
})

it('rejects an unsupported media type', () => {
  expect(validateDocumentFile(file('notes.txt', 'text/plain'))).toContain('仅支持')
})

it('applies a size limit only when a confirmed limit is supplied', () => {
  expect(validateDocumentFile(file('record.pdf', 'application/pdf', 11), 10)).toContain('大小限制')
  expect(validateDocumentFile(file('record.pdf', 'application/pdf', 11))).toBeNull()
})

it('rejects an empty file', () => {
  expect(validateDocumentFile(file('empty.pdf', 'application/pdf', 0))).toBe('不能上传空文件。')
})

it('rejects invalid file metadata', () => {
  expect(validateDocumentFile(file('', 'application/pdf'))).toContain('文件信息无效')
  expect(validateDocumentFile(file('bad.pdf', 'application/pdf', Number.NaN))).toContain('文件信息无效')
})
