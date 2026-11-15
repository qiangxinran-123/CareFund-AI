import { AiProcessTimeline, type AiProcessStep } from '../../components/ai/AiProcessTimeline'
import type { AnalysisResult, UploadedDocument } from '../../types/contracts'
import type { AnalysisPhase } from '../workflow/workflowStatus'
import { fieldLabel } from './analysisDisplay'

interface Props {
  documents: UploadedDocument[]
  phase: AnalysisPhase
  result: AnalysisResult | null
}

function resultSteps(result: AnalysisResult): AiProcessStep[] {
  const linkedEvidence = new Set(result.facts.flatMap((fact) => fact.evidence_ids))
  const blocking = result.validation.issues.filter((issue) => issue.severity === 'blocking')
  const conflicts = result.validation.issues.filter((issue) => issue.type === 'conflict' || issue.type === 'inconsistent_amount' || issue.type === 'inconsistent_date')
  const unconfirmed = result.facts.filter((fact) => !fact.user_confirmed)
  const waitingForUser = !result.validation.can_finalize || blocking.length > 0 || unconfirmed.length > 0 || result.questions.some((question) => question.required)
  return [
    {
      id: 'extract', title: '抽取候选事实', status: 'complete',
      detail: `已整理 ${result.facts.length} 条候选事实，并保留原始来源。`,
    },
    {
      id: 'evidence', title: '核对证据', status: 'complete',
      detail: `已核对 ${result.evidence.length} 条材料片段，其中 ${linkedEvidence.size} 条被事实引用。`,
    },
    {
      id: 'conflicts', title: '检查冲突', status: conflicts.length > 0 ? 'blocked' : 'complete',
      detail: conflicts.length > 0 ? `发现 ${conflicts.length} 项来源或取值冲突，需要人工核对。` : '未发现会阻断流程的取值冲突。',
    },
    {
      id: 'confirmation', title: '等待用户确认', status: waitingForUser ? 'waiting_user' : 'complete',
      detail: waitingForUser ? `有 ${blocking.length} 项阻断问题、${unconfirmed.length} 条未确认事实等待处理。` : '当前正式 Policy 已允许进入草稿生成。',
    },
  ]
}

export function AnalysisProcessView({ documents, phase, result }: Props) {
  const failedDocuments = documents.filter((document) => document.processing_status === 'failed')
  const processingDocuments = documents.filter((document) => document.processing_status === 'processing' || document.processing_status === 'uploaded')
  const materialStep: AiProcessStep = documents.length === 0
    ? { id: 'materials', title: '识别材料', status: 'pending', detail: '未上传材料；系统只能整理用户输入，不能提供材料证据链。' }
    : failedDocuments.length > 0
      ? { id: 'materials', title: '识别材料', status: 'blocked', detail: `${failedDocuments.length} 份材料识别失败，请重新上传清晰文件。` }
      : processingDocuments.length > 0
        ? { id: 'materials', title: '正在识别材料', status: 'active', detail: `${processingDocuments.length} 份材料仍在提取可见文字。` }
        : { id: 'materials', title: '识别材料', status: 'complete', detail: `${documents.length} 份材料已完成文字提取，可用于证据核对。` }

  let steps: AiProcessStep[]
  if (result) {
    steps = [materialStep, ...resultSteps(result)]
  } else {
    const failed = phase === 'failed' || phase === 'error' || phase === 'stale'
    steps = [
      materialStep,
      {
        id: 'extract', title: phase === 'running' ? '正在抽取候选事实' : '抽取候选事实',
        status: failed ? 'blocked' : phase === 'running' ? 'active' : 'pending',
        detail: failed ? '任务未完成，未生成可展示的候选事实。' : phase === 'running' ? '模型正在从用户输入和材料片段中提取结构化事实。' : phase === 'queued' || phase === 'submitting' ? '请求已提交，等待服务端开始处理。' : '开始整理后，模型会提取结构化候选事实。',
      },
      { id: 'evidence', title: '核对证据', status: 'pending', detail: '候选事实返回后，系统才会逐条验证 Evidence 引用。' },
      { id: 'conflicts', title: '检查冲突', status: 'pending', detail: '证据核对后，系统会检查金额、日期和同字段取值冲突。' },
      { id: 'confirmation', title: '等待用户确认', status: 'pending', detail: '校验完成后，需要用户处理阻断项并确认事实。' },
    ]
  }

  return (
    <>
      <AiProcessTimeline
        caption="进度依据服务端任务状态、材料状态和最终校验结果展示；服务端未返回的内部子步骤不会被伪装为正在运行。"
        steps={steps}
        title="AI 资料整理过程"
      />
      {result && <ContinuationGate result={result} />}
    </>
  )
}

function ContinuationGate({ result }: { result: AnalysisResult }) {
  const blocking = result.validation.issues.filter((issue) => issue.severity === 'blocking')
  const unconfirmed = result.facts.filter((fact) => !fact.user_confirmed)
  const requiredQuestions = result.questions.filter((question) => question.required)
  const canContinue = result.validation.can_finalize && blocking.length === 0 && unconfirmed.length === 0 && requiredQuestions.length === 0
  const reasons = [
    ...blocking.map((issue) => issue.message),
    ...requiredQuestions.map((question) => `${fieldLabel(question.field)}：${question.reason}`),
    ...(unconfirmed.length > 0 ? [`还有 ${unconfirmed.length} 条候选事实等待用户确认。`] : []),
  ]
  if (!canContinue && reasons.length === 0) reasons.push('正式 Policy 尚未允许生成草稿，请根据校验提示补充或核对信息。')

  return (
    <section aria-labelledby="continuation-gate-title" className={`mt-4 rounded-xl border p-4 ${canContinue ? 'border-emerald-200 bg-emerald-50' : 'border-amber-300 bg-amber-50'}`}>
      <h3 className={`text-sm font-semibold ${canContinue ? 'text-emerald-900' : 'text-amber-950'}`} id="continuation-gate-title">
        {canContinue ? 'AI 可以继续生成草稿' : '为什么 AI 现在不能继续'}
      </h3>
      {canContinue ? (
        <p className="mt-2 text-sm leading-6 text-emerald-800">当前没有 blocking 问题。info 和 warning 仍会保留展示，但不会单独阻断生成。</p>
      ) : (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm leading-6 text-amber-900">
          {Array.from(new Set(reasons)).map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
    </section>
  )
}
