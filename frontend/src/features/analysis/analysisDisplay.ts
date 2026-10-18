import type { FactValue } from '../../types/contracts'

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
