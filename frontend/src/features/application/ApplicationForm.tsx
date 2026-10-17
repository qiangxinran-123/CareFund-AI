import { useEffect, useRef, useState } from 'react'
import { applicationApi as defaultApi, isMockMode as defaultMockMode } from '../../api'
import { ApiError } from '../../api/client'
import type { ApplicationApi } from '../../api/application'
import type { Application } from '../../types/contracts'
import { BasicInfoStep } from './BasicInfoStep'
import { FinancialInfoStep } from './FinancialInfoStep'
import { MedicalInfoStep } from './MedicalInfoStep'
import { StepIndicator } from './StepIndicator'
import {
  fromPatientInfo,
  initialFormValues,
  toPatientInfo,
  validateStep,
  type ApplicationFormValues,
  type FormErrors,
} from './validation'

const storageKey = 'carefund.application_id'

interface Props {
  api?: ApplicationApi
  applicationSnapshot?: Application | null
  mockMode?: boolean
  onApplicationChange?: (application: Application | null) => void
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) return '申请已在其他位置更新，请重新进入页面获取最新内容后再保存。'
    if (error.status === 400 || error.status === 422) {
      const detail = error.response?.error.details[0]?.message
      return detail ? `提交内容未通过服务端校验：${detail}` : `提交内容未通过服务端校验：${error.message}`
    }
    return error.message
  }
  return error instanceof Error ? error.message : '操作失败，请稍后重试。'
}

export function ApplicationForm({
  api = defaultApi,
  applicationSnapshot,
  mockMode = defaultMockMode,
  onApplicationChange,
}: Props) {
  const [currentStep, setCurrentStep] = useState(0)
  const [values, setValues] = useState<ApplicationFormValues>(initialFormValues)
  const [errors, setErrors] = useState<FormErrors>({})
  const [savedApplication, setSavedApplication] = useState<Application | null>(null)
  const [isRestoring, setIsRestoring] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const editGeneration = useRef(0)

  useEffect(() => {
    if (!applicationSnapshot) return
    setSavedApplication((current) => current?.application_id === applicationSnapshot.application_id
      ? applicationSnapshot
      : current)
  }, [applicationSnapshot])

  useEffect(() => {
    const applicationId = window.localStorage.getItem(storageKey)
    if (!applicationId) return

    let active = true
    setIsRestoring(true)
    api.get(applicationId)
      .then((response) => {
        if (!active) return
        setSavedApplication(response.application)
        onApplicationChange?.(response.application)
        setValues(fromPatientInfo(response.application.patient_info))
        setMessage({ kind: 'success', text: `已恢复已保存的申请（版本 ${response.application.revision}）。` })
      })
      .catch((error: unknown) => {
        if (!active) return
        if ((error instanceof ApiError && error.status === 404) || mockMode) {
          window.localStorage.removeItem(storageKey)
          onApplicationChange?.(null)
        }
        setMessage({ kind: 'error', text: `无法恢复已保存的申请：${describeError(error)}` })
      })
      .finally(() => {
        if (active) setIsRestoring(false)
      })

    return () => { active = false }
  }, [api, mockMode])

  function updateField(field: keyof ApplicationFormValues, value: string) {
    editGeneration.current += 1
    setValues((previous) => ({ ...previous, [field]: value }))
    setErrors((previous) => {
      if (!previous[field]) return previous
      const next = { ...previous }
      delete next[field]
      return next
    })
    setMessage(null)
  }

  function goNext() {
    const nextErrors = validateStep(currentStep, values)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length === 0) {
      setCurrentStep((step) => Math.min(step + 1, 2))
      setMessage(null)
    }
  }

  function goBack() {
    setCurrentStep((step) => Math.max(step - 1, 0))
    setErrors({})
    setMessage(null)
  }

  async function saveApplication() {
    const allErrors = { ...validateStep(0, values), ...validateStep(1, values) }
    if (Object.keys(allErrors).length > 0) {
      setErrors(allErrors)
      setCurrentStep(allErrors.displayName ? 0 : 1)
      return
    }

    setIsSaving(true)
    setMessage(null)
    const saveGeneration = editGeneration.current
    try {
      const patientInfo = toPatientInfo(values)
      const response = savedApplication
        ? await api.update(savedApplication.application_id, {
            expected_revision: savedApplication.revision,
            patient_info: patientInfo,
          })
        : await api.create({ patient_info: patientInfo })

      setSavedApplication(response.application)
      onApplicationChange?.(response.application)
      window.localStorage.setItem(storageKey, response.application.application_id)
      if (editGeneration.current === saveGeneration) {
        setValues(fromPatientInfo(response.application.patient_info))
        setMessage({
          kind: 'success',
          text: mockMode
            ? `申请信息已保存到本地 Mock 服务（版本 ${response.application.revision}），不代表真实后端已持久化。`
            : `申请信息已保存（版本 ${response.application.revision}）。`,
        })
      } else {
        setMessage({ kind: 'success', text: '保存请求已完成，但当前仍有未保存的修改。' })
      }
    } catch (error) {
      setMessage({ kind: 'error', text: describeError(error) })
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <section aria-labelledby="application-form-title" className="rounded-2xl border border-blue-100 bg-white p-5 shadow-sm sm:p-8">
      <div className="flex flex-col gap-4 border-b border-slate-100 pb-6 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-sm font-medium text-blue-700">申请流程 · 信息填写</p>
          <h2 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900" id="application-form-title">填写申请信息</h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-600">请如实填写相关信息。AI 仅辅助整理申请内容，具体事实及材料仍需您核对确认。</p>
        </div>
        {mockMode && <span className="w-fit rounded-full bg-amber-100 px-3 py-1 text-xs font-medium text-amber-900">Mock 模式 · 未连接真实后端</span>}
      </div>

      <form className="mt-7" onSubmit={(event) => {
        event.preventDefault()
        if (currentStep < 2) goNext()
        else void saveApplication()
      }}>
        <StepIndicator currentStep={currentStep} />
        <fieldset disabled={isRestoring}>
          <legend className="sr-only">申请信息</legend>
          {currentStep === 0 && <BasicInfoStep errors={errors} onChange={updateField} values={values} />}
          {currentStep === 1 && <MedicalInfoStep errors={errors} onChange={updateField} values={values} />}
          {currentStep === 2 && <FinancialInfoStep />}
        </fieldset>

        <div aria-live="polite" className="mt-6 min-h-6">
          {isRestoring && <p className="text-sm text-blue-700">正在恢复已保存的申请…</p>}
          {message && <p className={`text-sm ${message.kind === 'success' ? 'text-emerald-700' : 'text-red-700'}`} role={message.kind === 'error' ? 'alert' : 'status'}>{message.text}</p>}
        </div>

        <div className="mt-5 flex flex-col-reverse gap-3 border-t border-slate-100 pt-6 sm:flex-row sm:justify-between">
          <button className="button-secondary" disabled={currentStep === 0 || isRestoring} onClick={goBack} type="button">上一步</button>
          {currentStep < 2
            ? <button className="button-primary" disabled={isRestoring} onClick={goNext} type="button">下一步</button>
            : <button className="button-primary" disabled={isSaving || isRestoring} type="submit">{isSaving ? '保存中…' : savedApplication ? '保存修改' : '保存申请'}</button>}
        </div>
      </form>
    </section>
  )
}
