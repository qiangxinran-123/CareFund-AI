import { useEffect, useState } from 'react'
import type { AgentQuestion, Answer } from '../../types/contracts'
import { fieldLabel } from './analysisDisplay'

interface Props {
  disabled?: boolean
  onSubmit: (answers: Answer[]) => Promise<void>
  questions: AgentQuestion[]
}

export function FollowUpQuestions({ disabled = false, onSubmit, questions }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    setAnswers({})
    setErrors({})
    setMessage(null)
  }, [questions])

  async function submit() {
    const nextErrors: Record<string, string> = {}
    questions.forEach((question) => {
      if (question.required && !answers[question.question_id]?.trim()) nextErrors[question.question_id] = '请填写此必答问题。'
    })
    const payload = questions.flatMap((question) => {
      const answer = answers[question.question_id]?.trim()
      return answer ? [{ question_id: question.question_id, answer }] : []
    })
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return
    }
    if (payload.length === 0) {
      setMessage('请至少填写一项回答后再提交。')
      return
    }
    setSubmitting(true)
    setMessage(null)
    try {
      await onSubmit(payload)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '提交失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section aria-labelledby="questions-title" className="mt-8 border-t border-slate-100 pt-7">
      <p className="text-sm font-medium text-blue-700">智能追问</p>
      <h3 className="mt-1 text-xl font-semibold text-slate-900" id="questions-title">补充和确认信息</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">您的回答属于用户补充信息，不会被前端直接标记为已有材料支持。</p>
      {questions.length === 0 ? (
        <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">当前没有需要回答的追问。</p>
      ) : (
        <div className="mt-5 space-y-4">
          {questions.map((question, index) => (
            <div className="rounded-xl border border-slate-200 p-5" key={question.question_id}>
              <label className="block text-sm font-semibold text-slate-900" htmlFor={`answer-${question.question_id}`}>
                {index + 1}. {question.question} {question.required ? <span className="text-red-700">（必答）</span> : <span className="text-slate-500">（选答）</span>}
              </label>
              <p className="mt-2 text-xs leading-5 text-slate-500">需要补充：{fieldLabel(question.field)}。提出原因：{question.reason}</p>
              <textarea
                aria-describedby={errors[question.question_id] ? `answer-error-${question.question_id}` : undefined}
                className="form-control min-h-28 resize-y"
                disabled={disabled || submitting}
                id={`answer-${question.question_id}`}
                maxLength={2000}
                onChange={(event) => {
                  setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))
                  setErrors((current) => ({ ...current, [question.question_id]: '' }))
                  setMessage(null)
                }}
                value={answers[question.question_id] ?? ''}
              />
              {errors[question.question_id] && <p className="field-error" id={`answer-error-${question.question_id}`}>{errors[question.question_id]}</p>}
            </div>
          ))}
          {message && <p className="text-sm text-red-700" role="alert">{message}</p>}
          <button className="button-primary" disabled={disabled || submitting} onClick={() => void submit()} type="button">
            {submitting ? '正在提交…' : '提交补充信息'}
          </button>
        </div>
      )}
    </section>
  )
}
