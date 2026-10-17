import type { ReactNode } from 'react'

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-5 py-5 sm:px-8">
          <span aria-hidden="true" className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-700 text-lg font-semibold text-white">C</span>
          <div>
            <p className="text-lg font-semibold tracking-tight text-slate-900">CareFund-AI</p>
            <p className="text-xs text-slate-500">医疗众筹智能申请助手</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-10 sm:px-8 sm:py-14">
        <div className="mb-10">
          <p className="text-sm font-medium text-blue-700">申请流程</p>
          <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-900 sm:text-4xl">清晰整理每一步</h1>
          <p className="mt-3 max-w-2xl text-base leading-7 text-slate-600">从填写信息、上传医疗材料到 AI 辅助核对，逐步整理申请所需内容。草稿确认功能将在后续阶段开放。</p>
        </div>

        {children}
      </main>
    </div>
  )
}

