// 业务边界页面：在现有产品壳内完成候选整理、不可变提案与 LOCAL_GUI 明确批准。
import { SearchField } from '../../shared/ui/SearchField'

import { StatusBadge } from '../../shared/ui/StatusBadge'
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
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import './boundary.css'
import '../changes/lightweight.css'
import { CurrentBoundaryObjects, type BoundaryEditFocus } from './definitions/CurrentBoundaryObjects'
import { PageTaskHeader } from '../../shared/ui/PageTaskHeader'
import { TaskReceipt, useTaskGuard } from '../../app/tasks/TaskContinuity'
import { BoundaryMaintenanceEditor } from './draft/BoundaryMaintenanceEditor'
import { BoundaryProposalEditor } from './proposals/BoundaryProposalEditor'
import { BoundaryProposalReview } from './proposals/BoundaryProposalReview'
import { RuleCandidatesPanel } from './RuleCandidatesPanel'
import { RuleDetailsPanel } from './RuleDetailsPanel'
import { effectKindLabels, expectationLabels, relationLabels } from './draft/boundaryLabels'

export function BusinessBoundaryPage({ project, requestedIntentId, requestedIntentRevision, onRuleRoute, onNavigate, requestedProposalId, requestedActionId, requestedCandidateId, requestedCandidateRevision, candidateRecoveryOperation, onCandidateRoute, onError, onStateChanged, onBack, onProvidedProposal, onFeedback }: {
  project: ProjectDto
  requestedIntentId?: string | null
  requestedIntentRevision?: number
  onRuleRoute?: (id: string | null, revision?: number) => void
  onNavigate?: (path: string) => void
  requestedActionId?: string | null
  requestedProposalId?: string | null
  requestedCandidateId?: string | null
  requestedCandidateRevision?: number
  candidateRecoveryOperation?: string | null
  onCandidateRoute?: (id: string | null, revision: number, operation: string | null) => void
  onProvidedProposal?: () => Promise<BoundaryProposalViewDto>
  onError: (error: ApiError) => void
  onStateChanged: () => Promise<unknown> | unknown
  onBack: () => void
  onFeedback?: (message: string) => void
}) {
  const [selectedRule,setSelectedRule] = useState<{id:string;revision?:number} | undefined>(requestedIntentId ? {id:requestedIntentId,revision:requestedIntentRevision} : undefined)
  useEffect(()=>{setSelectedRule(requestedIntentId ? {id:requestedIntentId,revision:requestedIntentRevision}:undefined)},[project.project_id,requestedIntentId,requestedIntentRevision])
  const providedInFlight = useRef(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [boundary, setBoundary] = useState<BusinessBoundaryViewDto>()
  const [preview, setPreview] = useState<Awaited<ReturnType<typeof businessBoundariesApi.preview>>>()
  const [maintenanceDraft, setMaintenanceDraft] = useState<BoundaryMaintenanceDraftDto>()
  const [proposalView, setProposalView] = useState<BoundaryProposalViewDto>()
  const [initialCommand, setInitialCommand] = useState<BoundaryProposalCommandDto>()
  const [initialMaintenanceCommand, setInitialMaintenanceCommand] = useState<BoundaryMaintenanceCommandDto>()
  const [editorKey, setEditorKey] = useState(0)
  const [editFocus, setEditFocus] = useState<BoundaryEditFocus>()
  const [editing, setEditing] = useState<'INITIAL' | 'MAINTENANCE' | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [success, setSuccess] = useState<string>()
  const [syncError, setSyncError] = useState<string>()
  const [approvalUncertain, setApprovalUncertain] = useState(false)
  const [loadError, setLoadError] = useState(false)
  const [loadEpoch, setLoadEpoch] = useState(0)
  const [pendingOptions, setPendingOptions] = useState<Array<{proposal_id:string;created_at_us:number}>>([])
  const approvalInFlight = useRef(false)
  useTaskGuard(busy || Boolean(syncError) || approvalUncertain)
  const syncApproved = async () => {
    setBusy(true)
    try {
      setMaintenanceDraft(await businessBoundariesApi.maintenanceDraft(project.project_id))
      const workspace = await onStateChanged()
      if (!workspace) throw new Error('工作区尚未完成同步')
      setSyncError(undefined)
    } catch { setSyncError('批准事实已保留，下一步暂时无法读取。请重试读取，不要重复批准。') }
    finally { setBusy(false) }
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError(false)
    void businessBoundariesApi.editor(project.project_id).then(async (editor) => {
      if (!active) return
      const proposalId = requestedCandidateId ? undefined : requestedProposalId ?? (editor.pending_proposals.length === 1 ? editor.pending_proposals[0].proposal_id : undefined)
      const selected = proposalId ? await businessBoundariesApi.proposal(project.project_id, proposalId) : undefined
      if (!active) return
      setBoundary(editor.boundary)
      setPreview(editor.preview)
      setMaintenanceDraft(editor.maintenance_draft ?? undefined)
      setPendingOptions(editor.pending_proposals)
      setProposalView(selected)
      setEditing(requestedCandidateId || editor.pending_proposals.length || selected ? null : editor.maintenance_draft ? null : 'INITIAL')
    }).catch((error) => { if (active) {setLoadError(true);onError(error as ApiError)} }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [onError, project.project_id, requestedProposalId, requestedCandidateId, loadEpoch])

  const loadProvidedProposal = async () => {
    if (!onProvidedProposal || providedInFlight.current || busy) return
    providedInFlight.current = true; setBusy(true)
    try { setProposalView(await onProvidedProposal()); setEditing(null) }
    catch (error) {
      onError(error as ApiError)
      // 生成回执不明时仅恢复已存在提案，不重复生成，也不批准。
      try { const editor = await businessBoundariesApi.editor(project.project_id); setPendingOptions(editor.pending_proposals); if (editor.pending_proposals.length === 1) { setProposalView(await businessBoundariesApi.proposal(project.project_id, editor.pending_proposals[0].proposal_id)); setEditing(null) } } catch { /* 原错误保留，不能用重复生成来探测。 */ }
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
    let current: BusinessBoundaryViewDto
    try { current = await businessBoundariesApi.approve(project.project_id, target, reason) }
    catch (error) {
      const code = (error as ApiError).code
      const rejected = ['INPUT_INVALID','BOUNDARY_REVISION_CONFLICT','BOUNDARY_PROPOSAL_FINGERPRINT_MISMATCH','BOUNDARY_PROPOSAL_SOURCE_STALE','BOUNDARY_PROPOSAL_UNRESOLVED','BOUNDARY_PROPOSAL_REFERENCE_INVALID'].includes(code)
      setApprovalUncertain(!rejected); throw error
    }
    setBoundary(current)
    setProposalView(undefined)
    setInitialCommand(undefined)
    setInitialMaintenanceCommand(undefined)
    setEditing(null)
    setSuccess('权限规则已确认。')
    setSyncError('正在读取下一步。')
    // 批准回执已经成立；后续维护草稿读取失败不能留下可以再次批准的旧提案。
    onFeedback?.('权限变更已批准，正在同步当前工作。')
    await syncApproved()
  }
  const approveCurrent = async (reason: string) => {
    if (!proposalView || approvalInFlight.current || approvalUncertain) return
    approvalInFlight.current = true
    setBusy(true)
    try { await approve(proposalView.proposal, reason) }
    catch (error) { onError(error as ApiError) }
    finally { approvalInFlight.current = false; setBusy(false) }
  }
  const readApproval = async () => {
    if (!proposalView || busy) return
    setBusy(true)
    try {
      // 回执不明只读同一不可变提案的决定，不能重新发送批准来探测。
      const saved = await businessBoundariesApi.proposal(project.project_id, proposalView.proposal.proposal_id)
      if (!saved?.decision) return
      setBoundary(await businessBoundariesApi.current(project.project_id))
      setApprovalUncertain(false); setProposalView(undefined); setEditing(null)
      setSuccess(saved.decision.decision === 'APPROVED' ? '权限规则已确认。' : '这组提案已放弃，正式权限未由本次提案改变。')
      setSyncError('正在读取下一步。')
      await syncApproved()
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const rejectCurrent = async (reason: string) => {
    setEditFocus(undefined)
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
    setEditFocus(undefined)
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
  if (selectedRule && !editing && !proposalView) return <RuleDetailsPanel projectId={project.project_id} intentId={selectedRule.id} revision={selectedRule.revision} onNavigate={onNavigate} onBack={()=>{setSelectedRule(undefined);onRuleRoute?.(null)}} onEdit={(actionId,intentId)=>{setSelectedRule(undefined);onRuleRoute?.(null);setEditFocus({actionId,intentId});setEditing('MAINTENANCE')}}/>
  if (loading) return <div className="boundary-page"><PageTaskHeader title="权限要求" description="用业务规则说明，谁可以对谁的资源做什么。" status="正在读取" /><div className="boundary-loading"><Spin /><Typography.Text type="secondary">正在读取当前业务边界和待审提案</Typography.Text></div></div>
  if (loadError || !boundary || !preview) return <Result status="warning" title="业务权限暂时无法读取" subTitle="重新读取当前项目与精确提案，不重复提交变更。" extra={<><Button type="primary" onClick={()=>setLoadEpoch(value=>value+1)}>重新读取</Button><Button onClick={onBack}>返回当前工作</Button></>} />

  const beginMaintenance = (focus: BoundaryEditFocus) => {
    setSuccess(''); setEditFocus(focus); setInitialMaintenanceCommand(undefined); setEditorKey(value => value + 1); setEditing(boundary.actors.length ? 'MAINTENANCE' : 'INITIAL')
  }
  const permissionsComplete = boundary.actions.length > 0
    && boundary.permission_statuses.every((item) => item.permission_semantics_confirmed)
  return <EditorialPage label="权限规则文档">
    {editing !== 'MAINTENANCE' && <div className="boundary-overview-heading"><EditorialHeader eyebrow="业务权限" title={proposalView ? '审阅权限变更' : editing ? '建立权限规则' : '权限要求'}><p className="editorial-muted">用业务规则说明，谁可以对谁的资源做什么。</p>{!proposalView && <span className="boundary-confirmation">{permissionsComplete ? '当前规则已确认' : '需要确认当前权限'}</span>}</EditorialHeader></div>}
    {success && <TaskReceipt message={success} pending={syncError} onRetry={syncError && !busy ? () => void syncApproved() : undefined}/>}
    {approvalUncertain && <Alert type="warning" message="批准回执尚未确认。请先核对同一提案的决定，不要重复批准。" action={<Button loading={busy} onClick={() => void readApproval()}>核对批准结果</Button>}/>}
    {!proposalView && editing !== 'MAINTENANCE' && <RuleCandidatesPanel key={project.project_id} projectId={project.project_id} requestedId={requestedCandidateId} requestedRevision={requestedCandidateRevision}
      recoveryOperation={candidateRecoveryOperation} onRecoveryChange={onCandidateRoute}
      onExit={() => onCandidateRoute?.(null,0,null)}
      onSelected={(id,revision) => {setEditing(null); onCandidateRoute?.(id,revision,null)}} onProposal={async id => { const value = await businessBoundariesApi.proposal(project.project_id, id); setProposalView(value); setEditing(null) }}/>}
    {!proposalView && pendingOptions.length > 1 && <section className="boundary-pending-choices"><h2>选择要审阅的提案</h2><p>存在多份待审记录，请明确选择，不自动采用最后一份。</p>{pendingOptions.map((item,index)=><Button key={item.proposal_id} onClick={async()=>{setBusy(true);try{setProposalView(await businessBoundariesApi.proposal(project.project_id,item.proposal_id));setEditing(null)}catch(error){onError(error as ApiError)}finally{setBusy(false)}}}>审阅提案 {index+1}</Button>)}</section>}
    {!proposalView && !editing && !requestedCandidateId && <CurrentBoundary requestedActionId={requestedActionId} boundary={boundary} onEdit={beginMaintenance} onRule={(id,revision)=>{setSelectedRule({id,revision});onRuleRoute?.(id,revision)}} />}

    {proposalView
      ? <BoundaryProposalReview key={proposalView.proposal.proposal_id} proposalView={proposalView} busy={busy || approvalUncertain} onApprove={(reason) => void approveCurrent(reason)} onReturnToEdit={() => { void returnToEdit() }} onReject={(reason) => void rejectCurrent(reason)} />
      : editing === 'INITIAL'
        ? onProvidedProposal && !initialCommand ? <section aria-label="提供的权限材料">
            <p>这个项目已提供一份业务权限提案。先核对操作人、资源所有者和真实结果，再决定是否批准。</p>
            <div className="boundary-entry-actions"><Button type="primary" loading={busy} onClick={() => void loadProvidedProposal()}>使用已提供的权限提案</Button>
            <Button aria-expanded={manualOpen} onClick={() => setManualOpen(!manualOpen)}>自行编写权限草稿</Button></div>{manualOpen && <BoundaryProposalEditor key={editorKey} preview={preview} busy={busy} onSubmit={(command) => void createProposal(command)} />}
          </section> : <BoundaryProposalEditor key={editorKey} preview={preview} initialCommand={initialCommand} busy={busy} onSubmit={(command) => void createProposal(command)} />
        : editing === 'MAINTENANCE' && maintenanceDraft
          ? <BoundaryMaintenanceEditor key={editorKey} focus={editFocus} draft={maintenanceDraft} initialCommand={initialMaintenanceCommand} busy={busy} onSubmit={(command) => void createMaintenanceProposal(command)} />
          : !requestedCandidateId && <div className="boundary-new-proposal"><Typography.Text type="secondary">修改先进入草稿，审阅并批准后才会生效。</Typography.Text></div>}
  </EditorialPage>
}

function CurrentBoundary({ boundary, onEdit, requestedActionId, onRule }: { onRule: (id:string,revision:number)=>void; requestedActionId?: string | null; boundary: BusinessBoundaryViewDto; onEdit: (focus: BoundaryEditFocus) => void }) {
  const [selectedId, setSelectedId] = useState<string>(requestedActionId ?? '')
  useEffect(()=>{if(requestedActionId)setSelectedId(requestedActionId)},[requestedActionId])
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'rules' | 'actions' | 'actors'>('rules')
  const tabs = <nav className="boundary-view-tabs" aria-label="权限要求视图">{([['rules','权限规则'],['actions','业务动作'],['actors','业务角色']] as const).map(([key,label]) => <button key={key} aria-current={mode === key ? 'page' : undefined} onClick={() => setMode(key)}>{label}</button>)}</nav>
  if (mode !== 'rules') return <>{tabs}<CurrentBoundaryObjects key={mode} boundary={boundary} kind={mode} onEdit={onEdit}/></>
  const action = boundary.actions.find((item) => item.action_id === selectedId) ?? boundary.actions[0]
  const actors = new Map(boundary.actors.map((item) => [item.actor_id, item]))
  if (!action) return <p>还没有正式业务边界。先整理一项动作和它必须保护的真实结果。</p>
  if (!selectedId) return <>{tabs}<div className="boundary-collection-toolbar"><SearchField aria-label="搜索业务动作" placeholder="搜索业务动作" allowClear value={query} onChange={event=>setQuery(event.target.value)}/><Button type="primary" onClick={()=>onEdit({actionId:action.action_id,mode:'new'})}>新增规则</Button></div>
    <section className="light-permission-list" aria-label="当前权限清单">{boundary.actions.filter(item=>item.display_name.includes(query.trim())).map(item=>{
      const rules=boundary.permission_intents.filter(rule=>rule.business_action_id===item.action_id&&rule.action_revision===item.revision&&rule.effective_state==='ACTIVE')
      const condition=boundary.permission_statuses.find(value=>value.action_id===item.action_id)
      return <section key={item.action_id}>
        {condition?.reason_codes.includes('PERMISSION_REVISION_REVIEW_REQUIRED')&&<p role="status">当前业务版本需要重新确认权限；原权限仍保留为历史。</p>}
        {condition?.permission_semantics_confirmed&&condition.reason_codes.includes('ALLOW_CONTROL_REQUIRED')&&<><p role="status">权限已确认，还需完整允许对照</p><p>缺少覆盖同一业务结果的允许对照；已确认的拒绝规则仍然保留。</p></>}
        {condition?.reason_codes.includes('PERMISSION_SEMANTICS_REQUIRED')&&<p role="status">当前权限尚未确认</p>}
        {rules.length?rules.map((rule,index)=><section className="permission-summary-row" key={rule.intent_id}><StatusBadge kind="rule" className="permission-badge" tone={rule.expectation === 'ALLOW' ? 'success' : 'danger'}>{rule.expectation==='ALLOW'?'允许':'禁止'}</StatusBadge><div><h3>{actors.get(rule.subject_actor_id)?.display_name??'业务主体'}对{rule.relation==='OWNS'?'自己':rule.relation==='SAME_ROLE_OTHER_ACCOUNT'?`另一个${actors.get(rule.resource_owner_actor_id)?.display_name??'同权限组'}账号`:actors.get(rule.resource_owner_actor_id)?.display_name??'资源主体'}拥有的资源，{rule.expectation==='ALLOW'?'可以':'不得'}{item.display_name}。</h3><p>保护结果：{rule.protected_effect_ids.map(id=>item.effect_catalog.find(effect=>effect.effect_id===id)?.business_label??'已确认的业务结果').join('、')}</p></div><div className="light-permission-actions"><Button type="link" disabled={!rule.intent_id || !rule.revision} onClick={()=>onRule(rule.intent_id!,rule.revision!)}>详情</Button><Button type="link" aria-label={`编辑${rule.expectation==='ALLOW'?'允许':'禁止'}规则 ${index+1}`} onClick={()=>onEdit({actionId:item.action_id,intentId:rule.intent_id??undefined})}>编辑</Button></div></section>):<div className="permission-summary-row"><div><h3>{item.display_name}</h3><p>这项动作尚无当前权限规则。</p></div><Button type="link" onClick={()=>setSelectedId(item.action_id)}>查看动作</Button></div>}
      </section>
    })}{!boundary.actions.some(item=>item.display_name.includes(query.trim()))&&<p>没有匹配的动作</p>}</section><p className="light-meta">这些是已确认的业务要求，不是安全结论。规则变化仍需独立审阅与批准。</p></>
  const status = boundary.permission_statuses.find((item) => item.action_id === action.action_id)
  const binding = boundary.action_bindings.find((item) => item.action_id === action.action_id)?.status
  const permissions = boundary.permission_intents.filter((item) => item.business_action_id === action.action_id && item.action_revision === action.revision && item.effective_state === 'ACTIVE')
  return <>{tabs}<Button type="link" onClick={()=>setSelectedId('')}>← 返回全部权限要求</Button><div className="boundary-collection-toolbar"><SearchField aria-label="搜索业务动作" placeholder="搜索业务动作" allowClear value={query} onChange={event=>setQuery(event.target.value)}/><Button type="primary" onClick={()=>onEdit({actionId:action.action_id,mode:'new'})}>新增规则</Button></div><section className="boundary-document" aria-label="当前业务动作与权限">
    <nav className="action-index" aria-label="业务动作索引"><h3>业务动作</h3>{boundary.actions.filter(item => item.display_name.includes(query.trim())).map((item) => <button key={item.action_id} aria-current={item.action_id === action.action_id ? 'true' : undefined} onClick={() => setSelectedId(item.action_id)}>{item.display_name}<small>{boundary.permission_intents.filter(rule => rule.business_action_id === item.action_id && rule.action_revision === item.revision && rule.effective_state === 'ACTIVE').length} 条规则</small></button>)}{!boundary.actions.some(item => item.display_name.includes(query.trim())) && <p>没有匹配的动作</p>}</nav>
    <article className="boundary-action-document"><div className="boundary-action-heading"><div><h2>{action.display_name}</h2><p className="editorial-muted">{action.description}</p></div></div>
      {status?.reason_codes.includes('PERMISSION_REVISION_REVIEW_REQUIRED') && <p role="status">当前业务版本需要重新确认权限；原权限仍保留为历史。</p>}
      {status?.permission_semantics_confirmed && status.reason_codes.includes('ALLOW_CONTROL_REQUIRED') && <><p role="status">权限已确认，还需完整允许对照</p><p>缺少覆盖同一业务结果的允许对照；已确认的拒绝规则仍然保留。</p></>}
      {status?.reason_codes.includes('PERMISSION_SEMANTICS_REQUIRED') && <p role="status">当前权限尚未确认</p>}
      {permissions.length ? permissions.map((permission,index) => <section className="permission-summary-row" key={permission.intent_id ?? index}><StatusBadge kind="rule" className="permission-badge" tone={permission.expectation === 'ALLOW' ? 'success' : 'danger'}>{permission.expectation === 'ALLOW' ? '允许' : '禁止'}</StatusBadge><div><h3>{actors.get(permission.subject_actor_id)?.display_name ?? '当前业务主体'}对{permission.relation === 'OWNS' ? '自己' : permission.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${actors.get(permission.resource_owner_actor_id)?.display_name ?? '同权限组'}账号` : actors.get(permission.resource_owner_actor_id)?.display_name ?? '当前资源主体'}拥有的资源，{permission.expectation === 'ALLOW' ? '可以' : '不得'}{action.display_name}。</h3><p>保护结果：{permission.protected_effect_ids.map(id => action.effect_catalog.find(effect => effect.effect_id === id)?.business_label ?? '已确认的业务结果').join('、')}</p></div><Button type="link" aria-label={`编辑${permission.expectation === 'ALLOW' ? '允许' : '禁止'}规则 ${index+1}`} onClick={() => onEdit({actionId:action.action_id,intentId:permission.intent_id ?? undefined})}>编辑</Button></section>) : <p className="boundary-empty-rules">这项动作还没有当前权限规则。</p>}
      <div className="boundary-supporting"><section className="boundary-effect-overview"><h3>受保护的业务结果</h3>{action.effect_catalog.map(effect => <p key={effect.effect_id}>{effect.business_label} · {effect.resource_concept}</p>)}</section><details className="boundary-secondary"><summary>当前代码定位 · {binding === 'CURRENT' ? '已关联' : '需要确认'}</summary><p>{binding === 'CURRENT' ? '当前代码定位与已确认动作相符。' : binding === 'MISSING' ? '当前代码中还没有可靠定位到这项动作。业务语义仍保留。' : '当前代码定位需要重新确认；它不会自动改写权限。'}</p><Button onClick={() => onEdit({actionId:action.action_id,mode:'objects'})}>管理业务对象与代码关联</Button></details></div>
    </article>
  </section></>
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
