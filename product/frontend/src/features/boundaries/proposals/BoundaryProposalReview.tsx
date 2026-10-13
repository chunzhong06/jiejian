// 先审阅权限，再按需核对业务定义；所有前后对照仍来自服务端冻结提案，不补造历史。
import { StatusBadge } from '../../../shared/ui/StatusBadge'
import { Alert, Button, Checkbox, Segmented } from 'antd'
import { useEffect, useState } from 'react'
import type { BoundaryProposalViewDto, BoundaryReviewValueDto, BoundaryProposalReviewDto } from '../../../api/boundaries/businessBoundaries'
import { effectKindLabels, expectationLabels, relationLabels } from '../draft/boundaryLabels'
import './proposal-review.css'
import { RuleCoveragePreview } from '../RuleCoveragePreview'

type ReviewItem = BoundaryProposalReviewDto['items'][number]
const changeLabels={CREATE:'新增',UPDATE:'修改',RETIRE:'停用',REFERENCE:'沿用'}
export function BoundaryProposalReview({ proposalView, busy, onApprove, onReturnToEdit, onReject, onContinue, onRules }: {
  onContinue?:()=>void
  onRules?:()=>void
  proposalView: BoundaryProposalViewDto; busy: boolean
  onApprove: (reason: string) => void; onReturnToEdit: () => void; onReject: (reason: string) => void
}) {
  const [checked,setChecked]=useState(false)
  const [expectation,setExpectation]=useState<'ALL'|'ALLOW'|'DENY'>('ALL')
  const {proposal,review,decision,change_summary:summary}=proposalView
  useEffect(()=>setChecked(false),[proposal.proposal_id])
  const unavailable=!review||review.basis_state!=='COMPLETE'
  const changed=review?.items.filter(item=>item.change_kind!=='REFERENCE')??[]
  const retained=review?.items.filter(item=>item.change_kind==='REFERENCE')??[]
  const permissions=changed.filter(item=>item.entity_kind==='PERMISSION')
  const definitions=changed.filter(item=>item.entity_kind!=='PERMISSION')
  return <section className="permission-review" aria-label="业务边界变更审阅">
    <header className="permission-review-intro"><div><p className="editorial-eyebrow">{decision?'已保存的提案决定':'本次需要你决定'}</p><h2>{decision?'回看这次业务变更':'核对本次业务变更'}</h2><p>{decision?'这里保留当时审阅的变更与决定；当前工作会按最新状态继续。':'确认谁可以做什么、哪些结果必须受到保护。确认后才会改变正式权限。'}</p></div><StatusBadge kind="lifecycle" tone={decision?.decision==='APPROVED'?'success':'warning'}>{decision?decision.decision==='APPROVED'?'已批准':'已放弃':'等待你的决定'}</StatusBadge>
      <dl className="permission-review-counts"><div><dt>权限变更</dt><dd>{unavailable?'待核对':permissions.length}<small>项</small></dd></div><div><dt>业务定义变更</dt><dd>{unavailable?'待核对':definitions.length}<small>项</small></dd></div><div><dt>继续沿用</dt><dd>{unavailable?'待核对':retained.length}<small>项</small></dd></div></dl>
    </header>
    {unavailable&&<Alert type="warning" showIcon message="无法恢复提案的原始基线" description="暂不提供批准入口。缺失的历史版本不会被当前值或空值替代。"/>}
    {review?.current_state_changed&&!decision&&<Alert type="warning" showIcon message="当前正式状态已经变化" description="下方仍保留提案引用的原始版本，请返回修改并重新形成提案。"/>}
    <div className="permission-review-workspace">
    <div className="permission-review-document work-surface">
    {summary&&<p className="permission-review-summary">新增 {summary.new_actor_count} 个角色、{summary.new_action_count} 个动作。<span>{summary.permission_updates.length} 项权限更新，{summary.permission_carry_forwards.length} 项权限沿用。</span></p>}
    <section className="permission-review-rules" aria-label="本次权限变化"><div className="permission-review-rules-heading"><header><h3>权限规则</h3><p>先核对操作人、资源归属和需要保护的结果。</p></header>
      {!!permissions.length&&<Segmented className="permission-review-filter" aria-label="筛选待审权限" options={[{label:'全部规则',value:'ALL'},{label:'允许',value:'ALLOW'},{label:'禁止',value:'DENY'}]} value={expectation} onChange={value=>setExpectation(value as typeof expectation)}/>}</div>
      {expectation!=='ALL'&&<p className="editorial-muted">当前仅筛选展示，确认仍覆盖整份提案。</p>}
      {permissions.filter(item=>expectation==='ALL'||item.after.expectation===expectation).map(item=><ReviewChange key={item.item_id} item={item}/>)}
      {!!permissions.length&&!permissions.some(item=>expectation==='ALL'||item.after.expectation===expectation)&&<p>没有符合筛选条件的待审规则。</p>}
      {!permissions.length&&!unavailable&&<p>本次没有权限规则变更，请核对下方业务定义与实现定位。</p>}
    </section>
    {!!definitions.length&&<details className="permission-review-support"><summary>业务定义变更 · {definitions.length} 项<span>角色与动作的含义、资源和结果定义</span></summary><div className="permission-definition-grid">{definitions.map(item=><ReviewChange key={item.item_id} item={item}/>)}</div></details>}
    {!!retained.length&&<details className="permission-review-support"><summary>沿用的 {retained.length} 项业务定义与权限<span>本次没有修改，确认范围中继续保留</span></summary><div className="permission-definition-grid">{retained.map(item=><ReviewChange key={item.item_id} item={item}/>)}</div></details>}
    <details className="permission-review-support"><summary>拟采用的当前定位与来源<span>源码关联及提案来源</span></summary><div className="permission-review-support-body"><p>{proposal.provenance}</p>{proposal.proposed_actors.filter(item=>item.source_candidate_ids?.length).map(item=><p key={item.item_id}>{item.display_name} · 使用本提案选定的角色来源</p>)}{proposal.proposed_actions.filter(item=>item.source_candidate_ids?.length).map(item=><p key={item.item_id}>{item.display_name} · 使用本提案选定的动作来源</p>)}<p className="editorial-muted">旧定位没有独立历史记录时，不构造旧定位对照。</p></div></details>
    <RuleCoveragePreview projectId={proposal.project_id} reference={{kind:'PROPOSAL',proposal_id:proposal.proposal_id}}/>
    </div>
    <aside className="permission-review-aside work-aside" aria-label="批准前核对">
    <h3>{decision?'这份提案的决定':'确认这份提案'}</h3><p>{decision?'审阅已经结束。继续当前工作，可核对运行地址和准备检查材料。':'核对正文中的权限变化与沿用要求，再决定是否批准。'}</p>
    {!!proposal.unresolved_questions?.length&&<Alert type="warning" message="仍有未解决问题" description={proposal.unresolved_questions.join('；')}/>}
    {decision?<Alert type="info" message={decision.decision==='APPROVED'?'这份提案已确认':'这份提案已放弃'} description={decision.reason}/>:<footer className="permission-review-decision"><div className="permission-review-acknowledgement"><Checkbox disabled={busy} checked={checked} onChange={e=>setChecked(e.target.checked)}>我已核对本次变更和沿用的业务要求</Checkbox><p>批准后进入材料准备，检查结果另行形成。</p></div><div className="boundary-review-actions"><Button disabled={busy} onClick={onReturnToEdit}>返回修改</Button><Button type="primary" loading={busy} disabled={busy||unavailable||review?.current_state_changed||!checked||Boolean(proposal.unresolved_questions?.length)} onClick={()=>onApprove('用户已勾选确认：已核对本次变更和沿用的业务要求')}>确认这组业务边界</Button></div><div className="permission-review-withdraw"><Button danger disabled={busy} onClick={()=>onReject('用户明确放弃这组业务边界提案')}>放弃这组提案</Button><span>仅对当前提案生效</span></div></footer>}
    {decision&&<div className="boundary-review-actions">{onContinue&&<Button onClick={onContinue}>继续当前工作</Button>}{onRules&&<Button type="primary" onClick={onRules}>返回当前规则列表</Button>}</div>}
    </aside></div>
  </section>
}
function ReviewChange({item}:{item:ReviewItem}) {
  // 只有有可靠原始值的既有对象才做双栏对照；首次新增不重复铺空白基线。
  const compare=item.change_kind!=='CREATE'&&item.change_kind!=='REFERENCE'
  return <article className="permission-review-change"><header><div>{item.after.expectation&&<StatusBadge kind="rule" className="permission-badge" tone={item.after.expectation === 'ALLOW' ? 'success' : 'danger'}>{item.after.expectation==='ALLOW'?'允许':'禁止'}</StatusBadge>}<h4>{item.after.display_name}</h4></div><span className="permission-review-change-kind">{changeLabels[item.change_kind]}</span></header>
    <div className={compare?'permission-review-compare':'permission-review-value'}>{compare&&<section><h5>原始要求</h5>{!item.basis_available?<p>原始版本不可用</p>:item.before?<ReviewValue value={item.before}/>:<p>尚未建立这项业务要求</p>}</section>}<section>{compare&&<h5>拟生效要求</h5>}{!item.basis_available&&!compare&&<p role="status">原始版本不可用，请先核对基线。</p>}<ReviewValue value={item.after}/></section></div>
  </article>
}

function ReviewValue({value}:{value:BoundaryReviewValueDto}) {
  const operations:Record<string,string>={READ:'阅读',CHANGE:'修改',DELETE:'删除',EXPORT:'导出',ADMIN:'管理',CUSTOM:'自定义'}
  return <div className="review-business-value">
    {value.effective_state === 'RETIRED' && <p>停用这项业务要求</p>}
    {value.expectation && value.relation ? <div className="review-permission-value"><div><p>{value.subject}对{value.resource_owner}拥有的资源，{expectationLabels[value.expectation]}“{value.action}”。</p><p>{relationLabels[value.relation]}</p></div><div className="review-protected-results"><span>{value.expectation==='DENY' ? '不允许出现的结果' : '允许获得的结果'}</span>{value.effects.length ? value.effects.map((effect,index)=><EffectMeaning key={index} effect={effect}/>) : <ul>{value.protected_effects.map((label,index)=><li key={index}>{label}</li>)}</ul>}</div></div> : <><p>{value.description}</p>{value.resource_concept && <p>资源：{value.resource_concept}</p>}{value.operation_kind && <p>操作：{operations[value.operation_kind] ?? value.operation_kind} · {value.state_changing ? '会改变业务状态' : '不改变业务状态'}</p>}{value.effects.map((effect,index)=><EffectMeaning key={index} effect={effect}/>)}</>}
  </div>
}

function EffectMeaning({effect}:{effect:BoundaryReviewValueDto['effects'][number]}) {
  return <section className="review-effect-meaning"><strong>{effect.business_label}</strong><p>{effect.description}</p>{effect.effect_kind==='STATE_MUTATION' && <p className="editorial-muted">涉及“曾经发生”的要求，要核对本轮检查窗口内的独立记录，不能只看最终状态。</p>}<details><summary>查看结果定义</summary><p>{effectKindLabels[effect.effect_kind]} · {effect.resource_concept}</p>{effect.expected_state&&<p>对应状态值：<code>{effect.expected_state}</code></p>}{Boolean(effect.protected_projection?.length)&&<p>保护字段：{effect.protected_projection!.join('、')}</p>}</details></section>
}
