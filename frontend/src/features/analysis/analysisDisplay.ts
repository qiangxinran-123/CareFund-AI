import type { FactValue, ValidationIssue } from '../../types/contracts'

const fieldLabels: Record<string, string> = {
  'patient.display_name': '患者称呼',
  'patient.age_group': '年龄阶段',
  'patient.medical_summary': '病情与治疗情况',
  'treatment.estimated_cost': '预计治疗费用',
  'treatment.recorded_date': '治疗记录日期',
  'contact.city': '所在城市',
}

export function fieldLabel(field: string): string {
  return fieldLabels[field] ?? '申请信息'
}

export function factValueText(value: FactValue): string {
  if (value.kind === 'boolean') return value.value ? '是' : '否'
  if (value.kind === 'integer') return String(value.value)
  if (value.kind === 'money') {
    try {
      return new Intl.NumberFormat('zh-CN', {
        style: 'currency', currency: value.value.currency,
      }).format(value.value.amount_minor / 100)
    } catch {
      return `${value.value.currency} ${(value.value.amount_minor / 100).toFixed(2)}`
    }
  }
  return value.value
}

export function issueStatus(issue: ValidationIssue): { label: string; style: string; guidance: string } {
  if (issue.type === 'conflict' || issue.type === 'inconsistent_amount' || issue.type === 'inconsistent_date') {
    return { label: '信息有出入', style: 'bg-red-100 text-red-900', guidance: '建议：核对填写内容与材料内容。' }
  }
  if (issue.type === 'missing' || issue.type === 'unsupported') {
    return { label: '需补充', style: 'bg-amber-100 text-amber-900', guidance: '建议：补充相关信息或材料。' }
  }
  return { label: '待核对', style: 'bg-blue-100 text-blue-900', guidance: '建议：检查填写内容后再提交。' }
}

export function issueGroup(issue: ValidationIssue): '需要补充' | '需要核对' | '其他提醒' {
  if (issue.type === 'missing' || issue.type === 'unsupported') return '需要补充'
  if (issue.type === 'conflict' || issue.type === 'inconsistent_amount' || issue.type === 'inconsistent_date') return '需要核对'
  return '其他提醒'
}
