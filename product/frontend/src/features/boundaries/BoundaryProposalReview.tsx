// 不可变业务边界提案审阅：展示完整摘要，只允许明确批准、拒绝或返回新草稿。

import { Alert, Button, Input, Space, Typography } from 'antd'
import { useState } from 'react'
import type { BoundaryProposalViewDto, BusinessBoundaryViewDto } from '../../api/businessBoundaries'
import { effectKindLabels, expectationLabels, relationLabels } from './boundaryLabels'

export function BoundaryProposalReview({ proposalView, currentBoundary, busy, onApprove, onReturnToEdit, onReject }: {
  currentBoundary?: BusinessBoundaryViewDto
  proposalView: BoundaryProposalViewDto
  busy: boolean
  onApprove: (reason: string) => void
  onReturnToEdit: () => void
  onReject: (reason: string) => void
}) {
  const [reason, setReason] = useState('')
  const proposal = proposalView.proposal
  const summary = proposalView.change_summary
  const actors = new Map(proposal.proposed_actors.map((item) => [item.item_id, item]))
  const actions = new Map(proposal.proposed_actions.map((item) => [item.item_id, item]))

  return <section className="boundary-review" aria-labelledby="boundary-review-title">
    <div className="boundary-section-heading"><div><Typography.Title level={3} id="boundary-review-title">待确认业务边界</Typography.Title><Typography.Paragraph type="secondary">这份提案正文已经冻结。返回修改会建立新的本地草稿，不会改写当前提案。</Typography.Paragraph></div><span className="semantic-state is-warning">等待你的决定</span></div>
    <p className="editorial-muted">只有下方明确批准才会改变正式规则。代码实现定位与业务权限分开审阅。</p>
    {summary && <section aria-label="业务边界变更摘要"><h4>这次会改变什么</h4><ul>
      {summary.new_actor_count > 0 && <li>新增 {summary.new_actor_count} 个业务主体</li>}
      {summary.new_action_count > 0 && <li>新增 {summary.new_action_count} 个业务动作</li>}
      {summary.business_revision_updates.map((text) => <li key={`revision:${text}`}>{text} → 更新业务版本</li>)}
      {summary.retirements.map((text) => <li key={`retire:${text}`}>{text} → 停用</li>)}
      {summary.permission_updates.map((text) => <li key={`permission:${text}`}>{text} → 更新权限</li>)}
      {summary.permission_carry_forwards.map((text) => <li key={`carry:${text}`}>{text} → 沿用权限</li>)}
      {summary.permission_retirements.map((text) => <li key={`permission-retire:${text}`}>{text} → 停用权限</li>)}
      {summary.implementation_rebinds.map((text) => <li key={`binding:${text}`}>{text} → 重新绑定到当前源码证据</li>)}
    </ul></section>}
    <div className="proposal-diff" aria-label="当前与提议后的差异">
      {proposal.proposed_actions.filter((item) => item.write_mode !== 'REFERENCE').map((item) => {
        const before = currentBoundary?.actions.find((current) => current.action_id === item.action_id)
        return <section key={item.item_id}><h4>{item.display_name}</h4><div className="proposal-diff-columns"><div><p className="editorial-eyebrow">当前</p><p>{before ? `${before.display_name}：${before.description}` : '尚未建立这项动作'}</p>{before && <p>{before.effect_catalog.map((effect) => effect.business_label).join('、')}</p>}</div><div><p className="editorial-eyebrow">提议后</p><p>{item.effective_state === 'RETIRED' ? '停用' : item.description}</p><p>{item.effect_catalog.map((effect) => `${effect.business_label} · ${effect.resource_concept}`).join('；')}</p></div></div></section>
      })}
      {proposal.proposed_actors.filter((item) => item.write_mode !== 'REFERENCE').map((item) => <section key={item.item_id}><h4>{item.display_name}</h4><p>{currentBoundary?.actors.find((current) => current.actor_id === item.actor_id)?.description ?? '尚未建立此主体'} → {item.effective_state === 'RETIRED' ? '停用' : item.description}</p></section>)}
      {proposal.proposed_permissions.filter((item) => item.write_mode !== 'REFERENCE').map((item) => {
        const subject = actors.get(item.subject_actor_item_id)?.display_name ?? '未命名主体'
        const owner = actors.get(item.resource_owner_actor_item_id)?.display_name ?? '未命名主体'
        const action = actions.get(item.business_action_item_id)
        const before = currentBoundary?.permission_intents.find((current) => current.intent_id === item.intent_id)
        return <section key={item.item_id}><h4>{subject} · {action?.display_name ?? '业务动作'}</h4><div className="proposal-diff-columns"><div><p className="editorial-eyebrow">当前</p><p>{before ? `${currentBoundary?.actors.find((actor) => actor.actor_id === before.subject_actor_id)?.display_name ?? '原操作主体'} 对${currentBoundary?.actors.find((actor) => actor.actor_id === before.resource_owner_actor_id)?.display_name ?? '原资源所有者'}拥有的资源，${expectationLabels[before.expectation]}“${currentBoundary?.actions.find((action) => action.action_id === before.business_action_id)?.display_name ?? '原业务动作'}”；${relationLabels[before.relation]}。` : '尚未确认这条权限'}</p>{before && <p>必须保护：{before.protected_effect_ids.map((id) => currentBoundary?.actions.find((action) => action.action_id === before.business_action_id)?.effect_catalog.find((effect) => effect.effect_id === id)?.business_label ?? '原规则已确认的业务结果').join('、')}。</p>}</div><div><p className="editorial-eyebrow">提议后</p><p>{subject} 对{item.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${owner}账号` : owner}拥有的资源，{item.effective_state === 'RETIRED' ? '停用这条规则' : `${expectationLabels[item.expectation]}“${action?.display_name ?? '业务动作'}”`}。</p><p>必须保护：{item.protected_effect_item_ids.map((id) => action?.effect_catalog.find((effect) => effect.item_id === id)?.business_label ?? '已确认的业务结果').join('、')}。</p></div></div></section>
      })}
    </div>
    <p className="editorial-muted">依据：{proposal.provenance}</p>
    {!!proposal.unresolved_questions?.length && <p role="alert">仍有未解决问题：{proposal.unresolved_questions.join('；')}</p>}
    <Input.TextArea aria-label="确认或放弃原因" value={reason} placeholder="说明你为什么确认或放弃这组业务边界" autoSize={{ minRows: 2 }} onChange={(event) => setReason(event.target.value)} />
    <Space wrap className="boundary-review-actions">
      <Button onClick={onReturnToEdit} disabled={busy}>返回修改</Button>
      <Button danger onClick={() => onReject(reason.trim() || '用户放弃这组业务边界提案')} disabled={busy}>放弃这组提案</Button>
      <Button type="primary" loading={busy} disabled={!reason.trim() || (proposal.unresolved_questions?.length ?? 0) > 0} onClick={() => onApprove(reason.trim())}>确认这组业务边界</Button>
    </Space>
  </section>
}
