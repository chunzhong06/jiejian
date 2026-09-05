// 不可变业务边界提案审阅：展示完整摘要，只允许明确批准、拒绝或返回新草稿。

import { Alert, Button, Input, Space, Typography } from 'antd'
import { useState } from 'react'
import type { BoundaryProposalViewDto } from '../../api/businessBoundaries'
import { effectKindLabels, expectationLabels, relationLabels } from './boundaryLabels'

export function BoundaryProposalReview({ proposalView, busy, onApprove, onReturnToEdit, onReject }: {
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
    <Alert type="info" showIcon message="变更摘要由服务端当前事实生成" description="代码实现映射与业务 revision 分开审阅；候选无需先确认，批准仍只由当前用户完成。" />
    {summary && <div className="boundary-review-grid" aria-label="业务边界变更摘要">
      <SummaryCard title="业务主体与动作" lines={[
        summary.new_actor_count ? `新增 ${summary.new_actor_count} 个业务主体` : '',
        summary.new_action_count ? `新增 ${summary.new_action_count} 个业务动作` : '',
        ...summary.business_revision_updates.map((item) => `${item} → 新 revision`),
        ...summary.retirements.map((item) => `${item} → 停用`),
        !summary.new_actor_count && !summary.new_action_count && !summary.business_revision_updates.length && !summary.retirements.length ? '现有业务主体与动作保持不变' : '',
      ]} />
      <SummaryCard title="权限" lines={[
        ...summary.permission_updates.map((item) => `${item} → 更新`),
        ...summary.permission_carry_forwards.map((item) => `${item} → 沿用到新 revision`),
        ...summary.permission_retirements.map((item) => `${item} → 停用`),
        !summary.permission_updates.length && !summary.permission_carry_forwards.length && !summary.permission_retirements.length ? '现有权限保持不变' : '',
      ]} />
      <SummaryCard title="代码实现" lines={summary.implementation_rebinds.length
        ? summary.implementation_rebinds.map((item) => `${item} → 重新绑定到当前源码证据`)
        : ['现有代码实现映射保持不变']} />
    </div>}
    <div className="boundary-review-grid">
      <article><Typography.Text className="workbench-secondary-label">待确认业务主体</Typography.Text><ul>{proposal.proposed_actors.map((item) => <li key={item.item_id}><strong>{item.display_name}</strong><span>{item.description}</span></li>)}</ul></article>
      <article><Typography.Text className="workbench-secondary-label">待确认业务动作与结果</Typography.Text><ul>{proposal.proposed_actions.map((item) => <li key={item.item_id}><strong>{item.display_name}</strong><span>{item.description}</span><ul>{item.effect_catalog.map((effect) => <li key={effect.item_id}>{effect.business_label} · {effectKindLabels[effect.effect_kind]} · {effect.resource_concept}{effect.protected_projection?.length ? ` · 有限字段：${effect.protected_projection.join('、')}` : ''}</li>)}</ul></li>)}</ul></article>
      <article><Typography.Text className="workbench-secondary-label">待确认权限规则</Typography.Text><ul>{proposal.proposed_permissions.map((item) => {
        const subject = actors.get(item.subject_actor_item_id)?.display_name ?? '未命名主体'
        const owner = actors.get(item.resource_owner_actor_item_id)?.display_name ?? '未命名主体'
        const action = actions.get(item.business_action_item_id)?.display_name ?? '未命名动作'
        return <li key={item.item_id}><strong>{subject} · {expectationLabels[item.expectation]}</strong><span>{action} · {owner} · {relationLabels[item.relation]}</span></li>
      })}</ul></article>
      <article><Typography.Text className="workbench-secondary-label">来源摘要</Typography.Text><Typography.Paragraph>{proposal.provenance}</Typography.Paragraph>{proposal.unresolved_questions?.length ? <Alert type="warning" message="仍有未解决问题" description={proposal.unresolved_questions.join('；')} /> : <Typography.Text type="secondary">当前提案没有未解决问题。</Typography.Text>}</article>
    </div>
    <Input.TextArea aria-label="确认或放弃原因" value={reason} placeholder="说明你为什么确认或放弃这组业务边界" autoSize={{ minRows: 2 }} onChange={(event) => setReason(event.target.value)} />
    <Space wrap className="boundary-review-actions">
      <Button onClick={onReturnToEdit} disabled={busy}>返回修改</Button>
      <Button danger onClick={() => onReject(reason.trim() || '用户放弃这组业务边界提案')} disabled={busy}>放弃这组提案</Button>
      <Button type="primary" loading={busy} disabled={!reason.trim() || (proposal.unresolved_questions?.length ?? 0) > 0} onClick={() => onApprove(reason.trim())}>确认这组业务边界</Button>
    </Space>
  </section>
}

function SummaryCard({ title, lines }: { title: string; lines: string[] }) {
  return <article><Typography.Text className="workbench-secondary-label">{title}</Typography.Text><ul>{lines.filter(Boolean).map((line) => <li key={line}>{line}</li>)}</ul></article>
}
