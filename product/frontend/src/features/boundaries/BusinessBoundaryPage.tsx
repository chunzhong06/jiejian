// 业务边界页面：在现有产品壳内完成候选整理、不可变提案与 LOCAL_GUI 明确批准。

import { Alert, Button, Result, Spin, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
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
import { EditorialHeader, EditorialPage, RuleSentence } from '../../shared/ui/Editorial'
import './boundary.css'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { BoundaryMaintenanceEditor } from './BoundaryMaintenanceEditor'
import { BoundaryProposalEditor } from './BoundaryProposalEditor'
import { BoundaryProposalReview } from './BoundaryProposalReview'
import { effectKindLabels, expectationLabels, relationLabels } from './boundaryLabels'

export function BusinessBoundaryPage({ project, onError, onStateChanged, onBack, onProvidedProposal }: {
  project: ProjectDto
  onProvidedProposal?: () => Promise<BoundaryProposalViewDto>
  onError: (error: ApiError) => void
  onStateChanged: () => Promise<unknown> | unknown
  onBack: () => void
}) {
  const providedInFlight = useRef(false)
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

  const loadProvidedProposal = async () => {
    if (!onProvidedProposal || providedInFlight.current || busy) return
    providedInFlight.current = true; setBusy(true)
    try { setProposalView(await onProvidedProposal()); setEditing(null) }
    catch (error) {
      onError(error as ApiError)
      // 生成回执不明时仅恢复已存在提案，不重复生成，也不批准。
      try { const pending = await businessBoundariesApi.proposals(project.project_id, true); if (pending.proposals.length) { setProposalView(pending.proposals.at(-1)); setEditing(null) } } catch { /* 原错误保留。 */ }
    } finally { providedInFlight.current = false; setBusy(false) }
  }
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
  return <EditorialPage label="权限规则文档">
    <EditorialHeader eyebrow="权限 · 由你确认的业务规则" title={proposalView ? '审阅这次权限变化，再决定是否批准' : editing ? '把权限写清楚，再形成待审提案' : '谁可以对谁的资源做什么'}><p className="editorial-muted">{permissionsComplete ? '业务权限状态 已确认' : '需要确认当前权限'}</p></EditorialHeader>
    {success && <Alert type="success" showIcon message={success} />}
    {!proposalView && !editing && <CurrentBoundary boundary={boundary} />}

    {proposalView
      ? <BoundaryProposalReview currentBoundary={boundary} proposalView={proposalView} busy={busy} onApprove={(reason) => void approveCurrent(reason)} onReturnToEdit={() => { void returnToEdit() }} onReject={(reason) => void rejectCurrent(reason)} />
      : editing === 'INITIAL'
        ? onProvidedProposal && !initialCommand ? <section aria-label="提供的权限材料">
            <p>这个项目已提供一份业务权限提案。先核对操作人、资源所有者和真实结果，再决定是否批准。</p>
            <Button type="primary" loading={busy} onClick={() => void loadProvidedProposal()}>使用已提供的权限提案</Button>
            <details><summary>自行编写权限草稿</summary><BoundaryProposalEditor key={editorKey} preview={preview} busy={busy} onSubmit={(command) => void createProposal(command)} /></details>
          </section> : <BoundaryProposalEditor key={editorKey} preview={preview} initialCommand={initialCommand} busy={busy} onSubmit={(command) => void createProposal(command)} />
        : editing === 'MAINTENANCE' && maintenanceDraft
          ? <BoundaryMaintenanceEditor key={editorKey} draft={maintenanceDraft} initialCommand={initialMaintenanceCommand} busy={busy} onSubmit={(command) => void createMaintenanceProposal(command)} />
          : <div className="boundary-new-proposal"><Typography.Text type="secondary">调整会从当前已确认的业务对象开始，并形成新的不可变提案；现有正式边界不会被原地改写。</Typography.Text><Button onClick={() => { setInitialMaintenanceCommand(undefined); setEditorKey((value) => value + 1); setEditing(boundary.actors.length ? 'MAINTENANCE' : 'INITIAL') }}>{boundary.actors.length ? '调整当前业务边界' : '建立业务边界'}</Button></div>}
  </EditorialPage>
}

function CurrentBoundary({ boundary }: { boundary: BusinessBoundaryViewDto }) {
  const [selectedId, setSelectedId] = useState<string>()
  const action = boundary.actions.find((item) => item.action_id === selectedId) ?? boundary.actions[0]
  const actors = new Map(boundary.actors.map((item) => [item.actor_id, item]))
  if (!action) return <p>还没有正式业务边界。先整理一项动作和它必须保护的真实结果。</p>
  const status = boundary.permission_statuses.find((item) => item.action_id === action.action_id)
  const binding = boundary.action_bindings.find((item) => item.action_id === action.action_id)?.status
  const permissions = boundary.permission_intents.filter((item) => item.business_action_id === action.action_id && item.action_revision === action.revision && item.effective_state === 'ACTIVE')
  return <section className="boundary-document" aria-label="当前业务动作与权限">
    <nav className="action-index" aria-label="业务动作索引">{boundary.actions.map((item) => <button key={item.action_id} aria-current={item.action_id === action.action_id ? 'true' : undefined} onClick={() => setSelectedId(item.action_id)}>{item.display_name}</button>)}</nav>
    <article className="boundary-action-document"><h2>{action.display_name}</h2><p className="editorial-muted">{action.description}</p>
      <h3>这项动作会产生什么真实结果</h3><ul>{action.effect_catalog.map((effect) => <li key={effect.effect_id}><strong>{effect.business_label}</strong> · {effect.resource_concept}</li>)}</ul>
      <h3>你确认的权限</h3>{permissions.length ? permissions.map((permission, index) => <RuleSentence key={permission.intent_id ?? index}>
        <strong>{actors.get(permission.subject_actor_id)?.display_name ?? '当前业务主体'}</strong> 对<strong>{permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${actors.get(permission.resource_owner_actor_id)?.display_name ?? '同权限组'}账号` : actors.get(permission.resource_owner_actor_id)?.display_name ?? '当前资源主体'}</strong>拥有的资源，<strong>{permission.expectation === 'ALLOW' ? '可以' : '不可以'}{action.display_name}</strong>。
        <span className="rule-effect-note">必须保护：{permission.protected_effect_ids.map((id) => action.effect_catalog.find((effect) => effect.effect_id === id)?.business_label ?? '已确认的业务结果').join('、')}。</span>
      </RuleSentence>) : <p>这项动作还没有当前权限规则。</p>}
      <section className="boundary-implementation"><h3>当前实现与这份规则</h3><p>{binding === 'CURRENT' ? '当前代码定位与已确认动作相符。' : binding === 'MISSING' ? '当前代码中还没有可靠定位到这项动作。业务语义仍保留。' : '当前代码定位需要重新确认；它不会自动改写权限。'}</p>
      {status?.reason_codes.includes('PERMISSION_REVISION_REVIEW_REQUIRED') && <p role="status">当前业务版本需要重新确认权限；原权限仍保留为历史。</p>}
      {status?.permission_semantics_confirmed && status.reason_codes.includes('ALLOW_CONTROL_REQUIRED') && <><p role="status">权限已确认，还需完整允许对照</p><p>缺少覆盖同一业务结果的允许对照；已确认的拒绝规则仍然保留。</p></>}
      {status?.reason_codes.includes('PERMISSION_SEMANTICS_REQUIRED') && <p role="status">当前权限尚未确认</p>}
      </section>
    </article>
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
