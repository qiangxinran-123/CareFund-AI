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
    <section aria-labelledby="draft-confirm-title" className="mt-6 rounded-xl border border-blue-100 bg-blue-50/60 p-4 sm:p-5">
      <h3 className="text-base font-semibold text-slate-900" id="draft-confirm-title">核对并确认申请初稿</h3>
      <p className="mt-2 text-sm leading-6 text-slate-700">请仔细核对申请初稿中的病情、费用和其他重要信息。确认无误后再导出。</p>
      {blockedReason && <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-900" role="status">{blockedReason}</p>}
      <label className="mt-4 flex cursor-pointer items-start gap-3 text-sm leading-6 text-slate-800">
        <input checked={checked} className="mt-1 h-4 w-4 shrink-0 accent-blue-700 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-blue-600" disabled={confirmed || confirming || Boolean(blockedReason)} onChange={(event) => onCheckedChange(event.target.checked)} type="checkbox" />
        <span>我已核对申请初稿中的内容和信息来源，并了解这不等同于材料真实性认证或平台审核通过。</span>
      </label>
      <button className="button-primary mt-4 w-full sm:w-auto" disabled={!checked || confirmed || confirming || Boolean(blockedReason)} onClick={onConfirm} type="button">
        {confirming ? '正在确认…' : confirmed ? '草稿已确认' : '我已核对，确认草稿'}
      </button>
    </section>
  )
}
