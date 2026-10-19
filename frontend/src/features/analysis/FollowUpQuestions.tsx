import { useEffect, useRef, useState } from 'react'
import type { AgentQuestion, Answer } from '../../types/contracts'
import type { AnalysisStepState } from '../workflow/workflowStatus'
import { fieldLabel } from './analysisDisplay'

interface Props {
  disabled?: boolean
  onSubmit: (answers: Answer[]) => Promise<void>
  onStateChange?: (state: Pick<AnalysisStepState, 'answersSubmitting' | 'hasUnsavedAnswers'>) => void
  onDialogClose?: () => void
  dialogTrigger?: HTMLElement | null
  openQuestionId?: string | null
  questions: AgentQuestion[]
  standaloneQuestionIds?: string[]
}

export function FollowUpQuestions({ dialogTrigger, disabled = false, onDialogClose, onSubmit, onStateChange, openQuestionId, questions, standaloneQuestionIds = [] }: Props) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [dialogQuestionId, setDialogQuestionId] = useState<string | null>(null)
  const dialogRef = useRef<HTMLDialogElement | null>(null)
  const dialogTriggerRef = useRef<HTMLElement | null>(null)
  const dialogQuestion = questions.find((question) => question.question_id === dialogQuestionId) ?? null
  const standaloneQuestions = questions.filter((question) => standaloneQuestionIds.includes(question.question_id))

  useEffect(() => {
    setAnswers({})
    setErrors({})
    setMessage(null)
  }, [questions])

  useEffect(() => {
    if (!openQuestionId || !questions.some((question) => question.question_id === openQuestionId)) return
    dialogTriggerRef.current = dialogTrigger ?? (document.activeElement instanceof HTMLElement ? document.activeElement : null)
    setDialogQuestionId(openQuestionId)
  }, [dialogTrigger, openQuestionId, questions])

  useEffect(() => {
    if (!dialogQuestion) return
    const dialog = dialogRef.current
    if (!dialog) return
    if (typeof dialog.showModal === 'function' && !dialog.open) dialog.showModal()
    else dialog.open = true
    window.setTimeout(() => document.getElementById(`dialog-answer-${dialogQuestion.question_id}`)?.focus(), 0)
  }, [dialogQuestion])

  useEffect(() => {
    onStateChange?.({
      answersSubmitting: submitting,
      hasUnsavedAnswers: Object.values(answers).some((answer) => answer.trim().length > 0),
    })
  }, [answers, onStateChange, submitting])

  async function submit(selectedQuestions = questions): Promise<boolean> {
    const nextErrors: Record<string, string> = {}
    selectedQuestions.forEach((question) => {
      if (question.required && !answers[question.question_id]?.trim()) nextErrors[question.question_id] = '请填写此必答问题。'
    })
    const payload = selectedQuestions.flatMap((question) => {
      const answer = answers[question.question_id]?.trim()
      return answer ? [{ question_id: question.question_id, answer }] : []
    })
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors)
      return false
    }
    if (payload.length === 0) {
      setMessage('请至少填写一项回答后再提交。')
      return false
    }
    setSubmitting(true)
    setMessage(null)
    try {
      await onSubmit(payload)
      setAnswers({})
      setErrors({})
      return true
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '提交失败，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
    return false
  }

  function closeDialog() {
    if (submitting) return
    const dialog = dialogRef.current
    if (dialog && typeof dialog.close === 'function') dialog.close()
    else if (dialog) dialog.open = false
    setDialogQuestionId(null)
    onDialogClose?.()
    window.setTimeout(() => dialogTriggerRef.current?.focus(), 0)
  }

  return (
    <>
      {standaloneQuestions.length > 0 && (
        <section aria-labelledby="standalone-questions-title" className="mt-8 border-t border-slate-100 pt-7">
          <p className="text-sm font-medium text-blue-700">需要补充的问题</p>
          <h3 className="mt-1 text-xl font-semibold text-slate-900" id="standalone-questions-title">还需要了解这些信息</h3>
          <div className="mt-4 space-y-3">
            {standaloneQuestions.map((question) => (
              <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5" key={question.question_id}>
                <p className="break-words text-sm font-semibold leading-6 text-slate-900">{question.question} {question.required ? <span className="text-red-700">（必答）</span> : <span className="text-slate-500">（选答）</span>}</p>
                <p className="mt-2 break-words text-sm leading-5 text-slate-500">需要补充：{fieldLabel(question.field)}。为什么需要：{question.reason}</p>
                <button className="button-secondary mt-3" onClick={(event) => {
                  dialogTriggerRef.current = event.currentTarget
                  setDialogQuestionId(question.question_id)
                }} type="button">补充信息</button>
              </div>
            ))}
          </div>
        </section>
      )}
      {dialogQuestion && (
        <dialog aria-labelledby="answer-dialog-title" className="w-[min(32rem,calc(100%-2rem))] rounded-2xl border border-slate-200 bg-white p-0 shadow-xl" onCancel={(event) => { event.preventDefault(); closeDialog() }} ref={dialogRef}>
          <div className="p-5 sm:p-6">
            <p className="text-sm font-medium text-blue-700">补充信息</p>
            <h4 className="mt-1 text-xl font-semibold text-slate-900" id="answer-dialog-title">{dialogQuestion.question}</h4>
            <p className="mt-3 text-sm leading-6 text-slate-600">需要补充：{fieldLabel(dialogQuestion.field)}。为什么需要：{dialogQuestion.reason}</p>
            <label className="mt-5 block text-sm font-semibold text-slate-900" htmlFor={`dialog-answer-${dialogQuestion.question_id}`}>请填写补充说明</label>
            <textarea
              aria-describedby={errors[dialogQuestion.question_id] ? `dialog-answer-error-${dialogQuestion.question_id}` : undefined}
              className="form-control mt-2 min-h-32 resize-y"
              disabled={disabled || submitting}
              id={`dialog-answer-${dialogQuestion.question_id}`}
              maxLength={2000}
              onChange={(event) => {
                setAnswers((current) => ({ ...current, [dialogQuestion.question_id]: event.target.value }))
                setErrors((current) => ({ ...current, [dialogQuestion.question_id]: '' }))
                setMessage(null)
              }}
              value={answers[dialogQuestion.question_id] ?? ''}
            />
            {errors[dialogQuestion.question_id] && <p className="field-error" id={`dialog-answer-error-${dialogQuestion.question_id}`}>{errors[dialogQuestion.question_id]}</p>}
            {message && <p className="mt-3 text-sm text-red-700" role="alert">{message}</p>}
            <div className="mt-6 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
              <button className="button-secondary" disabled={submitting} onClick={closeDialog} type="button">取消</button>
              <button className="button-primary" disabled={disabled || submitting} onClick={() => void submit([dialogQuestion]).then((submitted) => { if (submitted) closeDialog() })} type="button">
                {submitting ? '正在提交并重新核对…' : '确认提交'}
              </button>
            </div>
          </div>
        </dialog>
      )}
    </>
  )
}
