// 业务边界页面：在现有产品壳内完成候选整理、不可变提案与 LOCAL_GUI 明确批准。

import { Alert, Button, Result, Spin, Typography } from 'antd'
import { useEffect, useState } from 'react'
import {
  businessBoundariesApi,
  type BoundaryMaintenanceCommandDto,
  type BoundaryMaintenanceDraftDto,
  type BoundaryProposalCommandDto,
  type BoundaryProposalDto,
  type BoundaryProposalViewDto,
  type BusinessBoundaryViewDto,
} from '../../api/businessBoundaries'
import type { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { BoundaryMaintenanceEditor } from './BoundaryMaintenanceEditor'
import { BoundaryProposalEditor } from './BoundaryProposalEditor'
import { BoundaryProposalReview } from './BoundaryProposalReview'
import { effectKindLabels, expectationLabels, relationLabels } from './boundaryLabels'

export function BusinessBoundaryPage({ project, onError, onStateChanged, onBack }: {
  project: ProjectDto
  onError: (error: ApiError) => void
  onStateChanged: () => Promise<unknown> | unknown
  onBack: () => void
}) {
  const [boundary, setBoundary] = useState<BusinessBoundaryViewDto>()
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof businessBoundariesApi.preview>>>()
  const [maintenanceDraft, setMaintenanceDraft] = useState<BoundaryMaintenanceDraftDto>()
  const [proposalView, setProposalView] = useState<BoundaryProposalViewDto>()
  const [initialCommand, setInitialCommand] = useState<BoundaryProposalCommandDto>()
  const [initialMaintenanceCommand, setInitialMaintenanceCommand] = useState<BoundaryMaintenanceCommandDto>()
  const [editorKey, setEditorKey] = useState(0)
  const [editing, setEditing] = useState<'INITIAL' | 'MAINTENANCE' | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState<string>()

  useEffect(() => {
    let active = true
    setLoading(true)
    void Promise.all([
      businessBoundariesApi.current(project.project_id),
      businessBoundariesApi.preview(project.project_id),
      businessBoundariesApi.proposals(project.project_id, true),
    ]).then(async ([current, draft, pending]) => {
      if (!active) return
      const maintenance = current.actors.length
        ? await businessBoundariesApi.maintenanceDraft(project.project_id)
        : undefined
      if (!active) return
      setBoundary(current)
      setPreview(draft)
      setMaintenanceDraft(maintenance)
      setProposalView(pending.proposals.at(-1))
      setEditing(pending.proposals.length ? null : current.actors.length ? null : 'INITIAL')
    }).catch((error) => { if (active) onError(error as ApiError) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [onError, project.project_id])

  const createProposal = async (command: BoundaryProposalCommandDto) => {
    setBusy(true)
    setSuccess(undefined)
    try {
      const created = await businessBoundariesApi.createProposal(project.project_id, command)
      setProposalView(created)
      setEditing(null)
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const createMaintenanceProposal = async (command: BoundaryMaintenanceCommandDto) => {
    setBusy(true)
    setSuccess(undefined)
    try {
      const created = await businessBoundariesApi.createMaintenanceProposal(project.project_id, command)
      setProposalView(created)
      setEditing(null)
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const approve = async (target: BoundaryProposalViewDto['proposal'], reason: string) => {
    const current = await businessBoundariesApi.approve(project.project_id, target, reason)
    setBoundary(current)
    setMaintenanceDraft(await businessBoundariesApi.maintenanceDraft(project.project_id))
    setProposalView(undefined)
    setInitialCommand(undefined)
    setInitialMaintenanceCommand(undefined)
    setEditing(null)
    setSuccess('当前业务边界已经由你确认。界鉴只应用本次提案中的 revision、权限或实现映射变化。')
    await onStateChanged()
  }
  const approveCurrent = async (reason: string) => {
    if (!proposalView) return
    setBusy(true)
    try { await approve(proposalView.proposal, reason) }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const rejectCurrent = async (reason: string) => {
    if (!proposalView) return
    setBusy(true)
    try {
      await businessBoundariesApi.reject(project.project_id, proposalView.proposal, reason)
      setProposalView(undefined)
      setInitialCommand(undefined)
      setInitialMaintenanceCommand(undefined)
      setEditing(boundary?.actors.length ? 'MAINTENANCE' : 'INITIAL')
      setSuccess('这组提案已放弃；正式业务边界没有被改写。')
      await onStateChanged()
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const returnToEdit = async () => {
    if (!proposalView) return
    setBusy(true)
    try {
      await businessBoundariesApi.reject(
        project.project_id,
        proposalView.proposal,
        '用户返回修改，保留正式边界并放弃当前不可变提案',
      )
      if (boundary?.actors.length && maintenanceDraft) {
        setInitialMaintenanceCommand(commandFromMaintenanceProposal(proposalView.proposal, maintenanceDraft))
        setEditing('MAINTENANCE')
      } else {
        setInitialCommand(commandFromProposal(proposalView.proposal))
        setEditing('INITIAL')
      }
      setProposalView(undefined)
      setEditorKey((value) => value + 1)
      await onStateChanged()
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  if (loading) return <div className="boundary-page"><PageTaskHeader title="业务边界" description="建立稳定业务主体、动作、结果与权限。" status="正在读取" /><div className="boundary-loading"><Spin /><Typography.Text type="secondary">正在读取当前业务边界和待审提案</Typography.Text></div></div>
  if (!boundary || !preview) return <Result status="warning" title="当前业务边界事实暂时不可用" subTitle="请刷新后重试；界鉴不会回退到旧权限表。" extra={<Button onClick={onBack}>返回工作台</Button>} />

  const permissionsComplete = boundary.actions.length > 0
    && boundary.permission_statuses.every((item) => item.permission_semantics_confirmed)
  return <div className="boundary-page">
    <PageTaskHeader title="业务边界" description="先确认稳定业务语义，再按需追加 revision、沿用权限或重新绑定当前代码实现。" status={proposalView ? '等待人工确认' : permissionsComplete ? '业务权限状态 已确认' : '需要确认当前权限'} />
    {success && <Alert type="success" showIcon message={success} />}
    <CurrentBoundary boundary={boundary} />

    {proposalView
      ? <BoundaryProposalReview proposalView={proposalView} busy={busy} onApprove={(reason) => void approveCurrent(reason)} onReturnToEdit={() => { void returnToEdit() }} onReject={(reason) => void rejectCurrent(reason)} />
      : editing === 'INITIAL'
        ? <BoundaryProposalEditor key={editorKey} preview={preview} initialCommand={initialCommand} busy={busy} onSubmit={(command) => void createProposal(command)} />
        : editing === 'MAINTENANCE' && maintenanceDraft
          ? <BoundaryMaintenanceEditor key={editorKey} draft={maintenanceDraft} initialCommand={initialMaintenanceCommand} busy={busy} onSubmit={(command) => void createMaintenanceProposal(command)} />
          : <div className="boundary-new-proposal"><Typography.Text type="secondary">调整会从 current stable IDs/revisions 开始，并形成新的不可变提案；现有正式边界不会被原地改写。</Typography.Text><Button onClick={() => { setInitialMaintenanceCommand(undefined); setEditorKey((value) => value + 1); setEditing(boundary.actors.length ? 'MAINTENANCE' : 'INITIAL') }}>{boundary.actors.length ? '调整当前业务边界' : '建立业务边界'}</Button></div>}
  </div>
}

function CurrentBoundary({ boundary }: { boundary: BusinessBoundaryViewDto }) {
  const actors = new Map(boundary.actors.map((item) => [item.actor_id, item]))
  const actionBindings = new Map(boundary.action_bindings.map((item) => [item.action_id, item.status]))
  if (boundary.actors.length === 0) return <section className="current-boundary-empty"><Typography.Text className="workbench-eyebrow">当前正式事实</Typography.Text><Typography.Title level={3}>还没有正式业务边界</Typography.Title><Typography.Paragraph type="secondary">可以从当前源码候选整理，也可以完全手工补充；没有实现映射不会阻止业务语义成立。</Typography.Paragraph></section>
  const permissionsComplete = boundary.actions.length > 0
    && boundary.permission_statuses.every((item) => item.permission_semantics_confirmed)
  return <section className="current-boundary" aria-labelledby="current-boundary-title">
    <div className="boundary-section-heading"><div><Typography.Text className="workbench-eyebrow">当前正式事实</Typography.Text><Typography.Title level={3} id="current-boundary-title">{permissionsComplete ? '业务权限状态 已确认' : '当前权限需要确认'}</Typography.Title></div><span className={`semantic-state${permissionsComplete ? ' is-safe' : ''}`}>{permissionsComplete ? '已确认' : '待确认'}</span></div>
    <div className="current-boundary-actors"><Typography.Text strong>业务主体</Typography.Text><span>{boundary.actors.map((item) => item.display_name).join('、')}</span></div>
    <div className="current-boundary-actions">{boundary.actions.map((action) => {
      const status = boundary.permission_statuses.find((item) => item.action_id === action.action_id)
      const permissions = boundary.permission_intents.filter((item) => item.business_action_id === action.action_id && item.action_revision === action.revision && item.effective_state === 'ACTIVE')
      const binding = actionBindings.get(action.action_id)
      return <article key={action.action_id} className="current-boundary-action">
        <div><Typography.Title level={4}>{action.display_name}</Typography.Title><Typography.Paragraph type="secondary">{action.description}</Typography.Paragraph></div>
        <div className="current-boundary-effects"><Typography.Text strong>业务结果</Typography.Text><ul>{action.effect_catalog.map((effect) => <li key={effect.effect_id}><b>{effect.business_label}</b><span>{effect.resource_concept} · {effectKindLabels[effect.effect_kind]}{effect.protected_projection?.length ? ` · 有限字段：${effect.protected_projection.join('、')}` : ''}</span></li>)}</ul></div>
        <div className="current-boundary-permissions"><Typography.Text strong>允许 / 拒绝</Typography.Text><ul>{permissions.map((permission, index) => <li key={`${permission.subject_actor_id}-${permission.expectation}-${index}`}><b>{actors.get(permission.subject_actor_id)?.display_name ?? '当前业务主体'} · {expectationLabels[permission.expectation]}</b><span>{actors.get(permission.resource_owner_actor_id)?.display_name ?? '当前资源主体'} · {relationLabels[permission.relation]}</span></li>)}</ul></div>
        {binding === 'MISSING' ? <Alert type="info" showIcon message="业务边界已确认" description="当前代码中还没有可靠定位到这项动作。" /> : binding && binding !== 'CURRENT' ? <Alert type="warning" showIcon message="业务语义保持有效" description="当前代码定位需要后续重新确认。" /> : null}
        {status?.reason_codes.includes('PERMISSION_REVISION_REVIEW_REQUIRED')
          ? <Alert type="warning" showIcon message="当前 revision 需要重新确认权限" description="这项业务动作已经形成新 revision，原权限仍保留为历史，但当前 revision 需要重新确认权限。" />
          : status?.reason_codes.includes('PERMISSION_SEMANTICS_REQUIRED')
            ? <Alert type="warning" showIcon message="当前权限尚未确认" description="这项业务动作还没有当前权限规则。" />
            : status && !status.validation_contract_complete
              ? <Alert type={status.allow_control_available ? 'info' : 'warning'} showIcon message="权限语义已确认，验证合同暂不完整" description={status.allow_control_available ? '完整新检查主链尚未重新接入；这不影响当前业务权限事实。' : '当前规则缺少覆盖同一业务结果的允许对照，但拒绝语义仍已保存。'} />
              : null}
      </article>
    })}</div>
  </section>
}

function commandFromProposal(proposal: BoundaryProposalDto): BoundaryProposalCommandDto {
  return { proposed_actors: proposal.proposed_actors, proposed_actions: proposal.proposed_actions, proposed_permissions: proposal.proposed_permissions, unresolved_questions: proposal.unresolved_questions, provenance: proposal.provenance }
}

function commandFromMaintenanceProposal(
  proposal: BoundaryProposalDto,
  draft: BoundaryMaintenanceDraftDto,
): BoundaryMaintenanceCommandDto {
  return {
    expected_boundary_state_fingerprint: draft.boundary_state_fingerprint,
    actors: proposal.proposed_actors.map((item) => ({
      item_id: item.item_id,
      actor_id: item.actor_id ?? null,
      expected_current_revision: item.expected_current_revision ?? null,
      display_name: item.display_name,
      description: item.description,
      effective_state: item.effective_state,
      source_candidate_ids: item.source_candidate_ids ?? [],
    })),
    actions: proposal.proposed_actions.map((item) => ({
      item_id: item.item_id,
      action_id: item.action_id ?? null,
      expected_current_revision: item.expected_current_revision ?? null,
      display_name: item.display_name,
      description: item.description,
      primary_resource_concept: item.primary_resource_concept,
      operation_kind: item.operation_kind,
      state_changing: item.state_changing,
      effects: item.effect_catalog,
      effective_state: item.effective_state,
      source_candidate_ids: item.source_candidate_ids ?? [],
    })),
    permissions: proposal.proposed_permissions.map((item) => ({
      item_id: item.item_id,
      intent_id: item.intent_id ?? null,
      expected_current_revision: item.expected_current_revision ?? null,
      effective_state: item.effective_state,
      subject_actor_item_id: item.subject_actor_item_id,
      business_action_item_id: item.business_action_item_id,
      resource_owner_actor_item_id: item.resource_owner_actor_item_id,
      relation: item.relation,
      expectation: item.expectation,
      protected_effect_item_ids: item.protected_effect_item_ids,
    })),
    provenance: proposal.provenance,
  }
}
