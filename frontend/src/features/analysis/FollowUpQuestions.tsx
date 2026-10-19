import { useEffect, useState } from 'react'
import type { AgentQuestion, Answer } from '../../types/contracts'
import type { AnalysisStepState } from '../workflow/workflowStatus'
import { fieldLabel } from './analysisDisplay'

interface Props {
  disabled?: boolean
  onSubmit: (answers: Answer[]) => Promise<void>
  onStateChange?: (state: Pick<AnalysisStepState, 'answersSubmitting' | 'hasUnsavedAnswers'>) => void
  questions: AgentQuestion[]
}

export function FollowUpQuestions({ disabled = false, onSubmit, onStateChange, questions }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    setAnswers({})
    setErrors({})
    setMessage(null)
  }, [questions])

  useEffect(() => {
    onStateChange?.({
      answersSubmitting: submitting,
      hasUnsavedAnswers: Object.values(answers).some((answer) => answer.trim().length > 0),
    })
  }, [answers, onStateChange, submitting])

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
      setAnswers({})
      setErrors({})
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '提交失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section aria-labelledby="questions-title" className="mt-8 border-t border-slate-100 pt-7">
      <p className="text-sm font-medium text-blue-700">补充信息</p>
      <h3 className="mt-1 text-xl font-semibold text-slate-900" id="questions-title">还需要了解这些信息</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">请按实际情况补充。您的回答会作为用户补充信息，不会被当作材料证明。</p>
      {questions.length === 0 ? (
        <p className="mt-4 rounded-xl bg-slate-50 p-4 text-sm text-slate-600">暂时没有需要补充的信息。</p>
      ) : (
        <div className="mt-5 space-y-4">
          {questions.map((question, index) => (
            <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5" key={question.question_id}>
              <label className="block break-words text-sm font-semibold leading-6 text-slate-900" htmlFor={`answer-${question.question_id}`}>
                {index + 1}. {question.question} {question.required ? <span className="text-red-700">（必答）</span> : <span className="text-slate-500">（选答）</span>}
              </label>
              <p className="mt-2 break-words text-sm leading-5 text-slate-500">需要补充：{fieldLabel(question.field)}。为什么需要：{question.reason}</p>
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
          <button className="button-primary w-full sm:w-auto" disabled={disabled || submitting} onClick={() => void submit()} type="button">
            {submitting ? '正在提交…' : '提交补充信息'}
          </button>
        </div>
      )}
    </section>
  )
}
