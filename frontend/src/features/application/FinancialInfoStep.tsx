export function FinancialInfoStep() {
  return (
    <section aria-labelledby="financial-info-title">
      <h3 className="text-lg font-semibold text-slate-900" id="financial-info-title">资金情况</h3>
      <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm leading-6 text-amber-950">
        <p className="font-medium">目前此申请还不能填写费用或筹款目标</p>
        <p className="mt-2">当前接口暂不支持保存费用或筹款目标。为保证信息能被正确保存，本次只记录前两步内容。</p>
      </div>
      <p className="mt-5 text-sm leading-6 text-slate-600">请核对前两步内容后保存。保存只记录您填写的信息，不代表事实已核实或申请已审核。</p>
    </section>
  )
}
