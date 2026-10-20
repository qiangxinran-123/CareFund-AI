interface Props {
  downloadUrl: string
  onViewDraft: () => void
}

export function DraftCompletion({ downloadUrl, onViewDraft }: Props) {
  return (
    <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-5 sm:p-6" data-testid="draft-completion">
      <span aria-hidden="true" className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-emerald-100 text-xl text-emerald-800">✓</span>
      <p className="mt-4 text-sm leading-6 text-emerald-950">您的申请内容已核对并确认，资料包已准备完成。</p>
      <ul className="mt-4 space-y-2 text-sm leading-6 text-emerald-950">
        <li>求助信息已整理。</li>
        <li>申请草稿已由您确认。</li>
        <li>申请资料包已准备完成。</li>
      </ul>
      <p className="mt-5 text-sm leading-6 text-slate-700">请妥善保存申请资料，并按照目标众筹平台的要求自行提交。本系统仅协助整理材料，不代表平台已受理或审核通过。</p>
      <div className="mt-5 flex flex-col gap-3 sm:flex-row">
        <a className="button-primary w-full text-center sm:w-auto" href={downloadUrl} rel="noopener noreferrer">下载申请资料包</a>
        <button className="button-secondary w-full sm:w-auto" onClick={onViewDraft} type="button">查看申请内容</button>
      </div>
    </div>
  )
}
