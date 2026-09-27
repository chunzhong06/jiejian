// 审阅只消费服务端不可变基线对照；当前正式边界不能充当历史版本。
import { Alert, Button, Checkbox, Input } from 'antd'
import { useState } from 'react'
import type { BoundaryProposalViewDto, BoundaryReviewValueDto } from '../../../api/businessBoundaries'
import { effectKindLabels, expectationLabels, relationLabels } from '../draft/boundaryLabels'

export function BoundaryProposalReview({ proposalView, busy, onApprove, onReturnToEdit, onReject }: {
  proposalView: BoundaryProposalViewDto; busy: boolean
  onApprove: (reason: string) => void; onReturnToEdit: () => void; onReject: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  const [checked, setChecked] = useState(false)
  const {proposal,review,change_summary:summary,decision} = proposalView
  const unavailable = !review || review.basis_state !== 'COMPLETE'
  const changed = review?.items.filter(item => item.change_kind !== 'REFERENCE') ?? []
  const retained = review?.items.filter(item => item.change_kind === 'REFERENCE') ?? []
  return <section className="boundary-review review-layout" aria-label="业务边界变更审阅">
    <article className="proposal-sheet">
      <div className="boundary-section-heading"><h2>核对本次业务变更</h2><span className="semantic-state is-warning">{decision ? '已有决定' : '等待你的决定'}</span></div>
      {unavailable && <Alert type="warning" showIcon message="无法恢复提案的原始基线" description="暂不提供批准入口。缺失的历史版本不会被当前值或空值替代。" />}
      {review?.current_state_changed && !decision && <Alert type="warning" showIcon message="当前正式状态已经变化" description="下方仍保留提案引用的原始版本，请返回修改并重新形成提案。" />}
      <div className="proposal-diff" aria-label="原始基线与提议后的差异">{changed.map(item => <section key={item.item_id}>
        <div className="proposal-item-heading"><h3>{item.after.display_name}</h3><span className="permission-badge">{{CREATE:'新增',UPDATE:'修改',RETIRE:'停用',REFERENCE:'沿用'}[item.change_kind]}</span></div>
        <div className="proposal-diff-columns"><div><p className="editorial-eyebrow">提案引用的原始基线</p>{!item.basis_available ? <p>原始版本不可用</p> : item.before ? <ReviewValue value={item.before}/> : <p>尚未建立这项业务要求</p>}</div><div><p className="editorial-eyebrow">提议应用后</p><ReviewValue value={item.after}/></div></div>
      </section>)}</div>
      {!!retained.length && <details className="boundary-secondary"><summary>沿用的 {retained.length} 项业务定义与权限</summary>{retained.map(item => <section key={item.item_id}><h3>{item.after.display_name}</h3><ReviewValue value={item.after}/></section>)}</details>}
      {!changed.length && !unavailable && <p>业务语义保持不变，请核对本次拟采用的实现定位。</p>}
      <details className="boundary-secondary"><summary>拟采用的当前定位与来源</summary><p>{proposal.provenance}</p>{proposal.proposed_actors.filter(item => item.source_candidate_ids?.length).map(item => <p key={item.item_id}>{item.display_name} · 使用本提案选定的角色来源</p>)}{proposal.proposed_actions.filter(item => item.source_candidate_ids?.length).map(item => <p key={item.item_id}>{item.display_name} · 使用本提案选定的动作来源</p>)}<p className="editorial-muted">旧定位没有独立历史记录时，不构造旧定位对照。</p></details>
      {!!proposal.unresolved_questions?.length && <Alert type="warning" message="仍有未解决问题" description={proposal.unresolved_questions.join('；')}/>}
      {decision ? <Alert type="info" message={decision.decision === 'APPROVED' ? '这份提案已确认' : '这份提案已放弃'} description={decision.reason}/> : <div className="boundary-approval">
        <label htmlFor="boundary-approval-reason">确认或放弃原因</label><Input.TextArea id="boundary-approval-reason" aria-label="确认或放弃原因" value={reason} placeholder="说明这次变化为什么符合业务要求" autoSize={{minRows:3}} onChange={e=>setReason(e.target.value)}/>
        <Checkbox checked={checked} onChange={e=>setChecked(e.target.checked)}>我已核对本次变更和沿用的业务要求</Checkbox>
        <div className="boundary-review-actions"><Button type="primary" loading={busy} disabled={busy || unavailable || review?.current_state_changed || !checked || !reason.trim() || Boolean(proposal.unresolved_questions?.length)} onClick={()=>onApprove(reason.trim())}>确认这组业务边界</Button><Button disabled={busy} onClick={onReturnToEdit}>返回修改</Button><Button type="text" disabled={busy} onClick={()=>onReject(reason.trim()||'用户放弃这组业务边界提案')}>放弃这组提案</Button></div>
      </div>}
    </article>
    <aside className="review-context"><h3>本次决定</h3><p>只有明确确认，才会改变正式业务权限。</p>{summary && <><h3>变化摘要</h3><p>新增 {summary.new_actor_count} 个角色、{summary.new_action_count} 个动作。</p><p>{summary.permission_updates.length} 项权限更新，{summary.permission_carry_forwards.length} 项权限沿用。</p></>}<h3>确认之后</h3><p>重新读取当前工作，继续准备检查。</p></aside>
  </section>
}

function ReviewValue({value}:{value:BoundaryReviewValueDto}) {
  const operations:Record<string,string>={READ:'阅读',CHANGE:'修改',DELETE:'删除',EXPORT:'导出',ADMIN:'管理',CUSTOM:'自定义'}
  return <div className="review-business-value">
    {value.effective_state === 'RETIRED' && <p>停用这项业务要求</p>}
    {value.expectation && value.relation ? <><p>{value.subject}对{value.resource_owner}拥有的资源，{expectationLabels[value.expectation]}“{value.action}”。</p><p>{relationLabels[value.relation]}</p><p>保护结果：{value.protected_effects.join('、')}</p></> : <><p>{value.description}</p>{value.resource_concept && <p>资源：{value.resource_concept}</p>}{value.operation_kind && <p>操作：{operations[value.operation_kind] ?? value.operation_kind} · {value.state_changing ? '会改变业务状态' : '不改变业务状态'}</p>}{value.effects.map((effect,index)=><div key={index}><strong>{effect.business_label}</strong><p>{effectKindLabels[effect.effect_kind]} · {effect.resource_concept}</p><p>{effect.description}</p>{effect.expected_state&&<p>预期状态：{effect.expected_state}</p>}{Boolean(effect.protected_projection?.length)&&<p>保护字段：{effect.protected_projection!.join('、')}</p>}</div>)}</>}
  </div>
}
