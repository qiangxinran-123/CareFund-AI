import { AppLayout } from './components/layout/AppLayout'

export default function App() {
  return (
    <AppLayout>
      <section aria-labelledby="status-title" className="rounded-2xl border border-blue-100 bg-white p-7 shadow-sm sm:p-9">
        <span className="inline-flex rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">工程基础已就绪</span>
        <h2 id="status-title" className="mt-5 text-xl font-semibold text-slate-900">申请功能即将开放</h2>
        <p className="mt-3 max-w-2xl text-sm leading-7 text-slate-600">本页展示未来申请流程的基础布局。信息填写、材料上传、AI分析和草稿确认尚未启用。</p>
      </section>
    </AppLayout>
  )
}

