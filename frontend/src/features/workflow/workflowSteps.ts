export const workflowSteps = [
  { id: 'application', label: '填写求助信息' },
  { id: 'documents', label: '上传证明材料' },
  { id: 'analysis', label: '核对并补充信息' },
  { id: 'draft', label: '确认并导出申请' },
] as const

export type WorkflowStepId = (typeof workflowSteps)[number]['id']

export function workflowStepIndex(step: WorkflowStepId): number {
  return workflowSteps.findIndex((item) => item.id === step)
}
