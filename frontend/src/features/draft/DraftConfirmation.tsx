interface Props {
  blockedReason: string | null
  checked: boolean
  confirmed: boolean
  confirming: boolean
  onCheckedChange: (checked: boolean) => void
  onConfirm: () => void
}

export function DraftConfirmation({ blockedReason, checked, confirmed, confirming, onCheckedChange, onConfirm }: Props) {
  return (
    <section aria-labelledby="draft-confirm-title" className="mt-6 rounded-xl border border-blue-100 bg-blue-50/60 p-5">
      <h3 className="text-base font-semibold text-slate-900" id="draft-confirm-title">确认草稿</h3>
      <p className="mt-2 text-sm leading-6 text-slate-700">请核对草稿中的病情、治疗经历、费用及其他重要信息。AI 仅辅助整理，最终内容需要您确认。</p>
      {blockedReason && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900" role="status">{blockedReason}</p>}
      <label className="mt-4 flex cursor-pointer items-start gap-3 text-sm leading-6 text-slate-800">
        <input checked={checked} className="mt-1 h-4 w-4 accent-blue-700" disabled={confirmed || confirming || Boolean(blockedReason)} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" />
        <span>我已逐项核对草稿内容及信息来源，并理解用户确认不等同于医疗真实性认证或平台审核通过。</span>
      </label>
      <button className="button-primary mt-4 w-full sm:w-auto" disabled={!checked || confirmed || confirming || Boolean(blockedReason)} onClick={onConfirm} type="button">
        {confirming ? '正在确认…' : confirmed ? '草稿已确认' : '确认此草稿'}
      </button>
    </section>
  )
}
