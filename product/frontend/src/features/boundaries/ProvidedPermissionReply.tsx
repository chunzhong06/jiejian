// 官方草稿在候选工作面模拟 Agent 回复；人的选择仍进入普通提案审阅，不自动批准。
import { Button, Radio } from 'antd'
import type { ReactNode } from 'react'

export type DownloadChoice = boolean | 'OTHER' | 'DEFER' | undefined

export function ProvidedPermissionReply({ requiresDownloadChoice, choice, busy, manualOpen, onChoice, onReview, onManual, children }: {
  requiresDownloadChoice: boolean; choice: DownloadChoice; busy: boolean; manualOpen: boolean
  onChoice: (choice: DownloadChoice) => void; onReview: () => void; onManual: () => void; children?: ReactNode
}) {
  return <section className="boundary-provided-proposal provided-permission-reply" aria-label="提供的权限材料">
    <header className="provided-reply-heading">
      <span className="provided-reply-author">Agent 整理结果</span>
      <span className="provided-reply-state">示例模拟 · 尚未批准</span>
    </header>
    <div className="provided-reply-body">
      <h2>权限草稿</h2>
      <p className="editorial-muted">示例用预置内容模拟 Agent 的整理回复。确认下面的要求后，在这里继续审阅并批准完整规则。</p>
      {requiresDownloadChoice ? <>
        <p>这份草稿把评审和负责人的权限分开：</p>
        <ul className="provided-reply-rules">
          <li><strong>评审可以查看公开内容。</strong><span>允许查看作品标题和公开说明。</span></li>
          <li><strong>评审不能取得内部完整包。</strong><span>也不能在处理过程中临时向评审开放内部包。</span></li>
          <li><strong>负责人可以取得自己的资料。</strong><span>保留本人内部完整包和公开展示版的下载权限。</span></li>
        </ul>
        <fieldset className="provided-reply-choice">
          <legend>还有一项需要你确认：评审是否可以下载公开展示版？</legend>
          <p>展示版只含公开内容；你的选择不会改变内部完整包的限制。</p>
          <Radio.Group className="rule-meaning-options product-choice-cards" aria-label="展示版下载要求" value={choice} disabled={busy} onChange={event=>onChoice(event.target.value)}>
            <Radio value={true} aria-label="允许下载展示版"><strong>允许下载展示版</strong><span>可以离线查看已经公开的内容。</span></Radio>
            <Radio value={false} aria-label="仅允许在线预览"><strong>仅允许在线预览</strong><span>保留在线浏览，不提供展示版下载。</span></Radio>
            <Radio value="OTHER" aria-label="这些都不是"><strong>这些都不是</strong><span>现有选项不符合要求，改为整理自己的约定。</span></Radio>
            <Radio value="DEFER" aria-label="暂不确定"><strong>暂不确定</strong><span>先不作决定，明确需求后再继续。</span></Radio>
          </Radio.Group>
          <p className="provided-reply-selection" role="status">{choice === 'OTHER'
            ? '请在下方编写符合实际业务的权限要求，再审阅完整规则。'
            : choice === 'DEFER' ? '当前不生成权限提案。明确需求后，再选择符合要求的选项。'
            : choice === true ? '你的选择：评审可以下载公开展示版。'
            : choice === false ? '你的选择：评审仅可在线预览，不可下载展示版。'
            : '选择后进入完整规则审阅；最终批准前，草稿不会生效。'}</p>
        </fieldset>
      </> : <p>可以继续查看示例提供的完整角色、动作及权限规则。核对后由你批准，也可以按实际业务重新整理。</p>}
    </div>
    <div className="boundary-entry-actions">
      <Button type={choice==='OTHER'?'primary':'link'} disabled={busy} aria-expanded={manualOpen} onClick={onManual}>{manualOpen?'收起自定义草稿':choice==='OTHER'?'编写我的权限要求':'自行编写权限草稿'}</Button>
      {choice !== 'OTHER' && <Button type="primary" loading={busy} disabled={requiresDownloadChoice && typeof choice !== 'boolean'} onClick={onReview}>继续审阅完整规则</Button>}
    </div>
    {children}
  </section>
}
