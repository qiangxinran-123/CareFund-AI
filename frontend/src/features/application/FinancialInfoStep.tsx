export function FinancialInfoStep() {
  return (
    <section aria-labelledby="financial-info-title">
      <h3 className="text-lg font-semibold text-slate-900" id="financial-info-title">资金情况</h3>
      <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
        <p className="font-medium">当前统一接口契约暂未开放资金字段</p>
        <p className="mt-2">本阶段不会要求或提交已发生费用、筹款目标等未经契约定义的信息。待统一契约补充后，可在此步骤接入。</p>
      </div>
      <p className="mt-5 text-sm leading-6 text-slate-600">请核对前两步内容后保存。保存仅记录您填写的自述信息，不代表事实审核通过。</p>
    </section>
  )
}
