// 业务边界页面：在现有产品壳内完成候选整理、不可变提案与 LOCAL_GUI 明确批准。
import { LoadingState } from '../../shared/ui/LoadingState'
import { SearchField } from '../../shared/ui/SearchField'

import { PermissionRuleRows } from './PermissionRuleRows'
import { Alert, Button, Radio, Result, Segmented, Typography } from 'antd'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { ruleCandidatesApi } from '../../api/boundaries/ruleCandidates'
import {
  businessBoundariesApi,
  type BoundaryMaintenanceCommandDto,
  type BoundaryMaintenanceDraftDto,
  type BoundaryProposalCommandDto,
  type BoundaryProposalDto,
  type BoundaryProposalViewDto,
  type BusinessBoundaryViewDto,
} from '../../api/boundaries/businessBoundaries'
import type { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/applications/projects'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import './boundary.css'
import '../../shared/styles/collections.css'
import { CurrentBoundaryObjects, type BoundaryEditFocus } from './definitions/CurrentBoundaryObjects'
import { PageTaskHeader } from '../../shared/ui/PageTaskHeader'
import { TaskReceipt } from '../../shared/ui/TaskReceipt'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { BoundaryMaintenanceEditor } from './draft/BoundaryMaintenanceEditor'
import { BoundaryProposalEditor } from './proposals/BoundaryProposalEditor'
import { BoundaryProposalReview } from './proposals/BoundaryProposalReview'
import { RuleCandidatesPanel } from './RuleCandidatesPanel'
import { RuleDetailsPanel } from './RuleDetailsPanel'
import { RulePreparationStages } from '../../shared/ui/RulePreparationStages'

export function BusinessBoundaryPage({ project, requestedIntentId, requestedIntentRevision, onRuleRoute, onNavigate, requestedProposalId, requestedActionId, requestedCandidatesView, requestedCandidateId, requestedCandidateRevision, candidateRecoveryOperation, onCandidateRoute, onError, onStateChanged, onBack, onProvidedProposal, providedDownloadChoiceRequired=false, onFeedback }: {
  project: ProjectDto
  requestedIntentId?: string | null
  requestedIntentRevision?: number
  onRuleRoute?: (id: string | null, revision?: number) => void
  onNavigate?: (path: string) => void
  requestedActionId?: string | null
  requestedProposalId?: string | null
  requestedCandidateId?: string | null
  requestedCandidatesView?: boolean
  requestedCandidateRevision?: number
  candidateRecoveryOperation?: string | null
  onCandidateRoute?: (id: string | null, revision: number, operation: string | null) => void
  providedDownloadChoiceRequired?: boolean
  onProvidedProposal?: (exhibitionDownload?: boolean) => Promise<BoundaryProposalViewDto>
  onError: (error: ApiError) => void
  onStateChanged: () => Promise<unknown> | unknown
  onBack: () => void
  onFeedback?: (message: string) => void
}) {
  const [selectedRule,setSelectedRule] = useState<{id:string;revision?:number} | undefined>(requestedIntentId ? {id:requestedIntentId,revision:requestedIntentRevision} : undefined)
  useEffect(()=>{setSelectedRule(requestedIntentId ? {id:requestedIntentId,revision:requestedIntentRevision}:undefined)},[project.project_id,requestedIntentId,requestedIntentRevision])
  const [exhibitionDownload,setExhibitionDownload]=useState<boolean | 'OTHER' | 'DEFER'>()
  useEffect(()=>setExhibitionDownload(undefined),[project.project_id,providedDownloadChoiceRequired])
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
  const [localCandidatesOpen, setLocalCandidatesOpen] = useState(false)
  const candidatesOpen = Boolean(requestedCandidateId) || (requestedCandidatesView ?? localCandidatesOpen)
  const [candidateSummary, setCandidateSummary] = useState('正在读取候选状态')
  const listPosition = useRef(0)
  const previousCandidatesOpen = useRef(candidatesOpen)
  useEffect(() => {
    if (candidatesOpen) return
    const remember = () => { listPosition.current = window.scrollY }
    window.addEventListener('scroll', remember, {passive:true})
    return () => window.removeEventListener('scroll', remember)
  }, [candidatesOpen])
  useLayoutEffect(() => {
    if (previousCandidatesOpen.current === candidatesOpen) return
    previousCandidatesOpen.current = candidatesOpen
    window.scrollTo({top:candidatesOpen ? 0 : listPosition.current, behavior:'instant'})
  }, [candidatesOpen])
  useEffect(() => {
    if (candidatesOpen || loading) return
    let active = true
    setCandidateSummary('正在读取候选状态')
    void ruleCandidatesApi.context(project.project_id).then(value => {
      if (!active) return
      const pending = value.candidates.filter(item => !item.decision && item.assessment !== 'ALREADY_CONFIRMED').length
      // 只读取第一页，不将分页下限或失败伪装成全部候选的精确计数。
      setCandidateSummary(pending ? `${pending}${value.next_offset != null ? '+' : ''} 条待处理候选` : value.next_offset != null ? '还有候选待查看' : '暂无待处理候选')
    }).catch(() => { if (active) setCandidateSummary('候选状态暂未读取，可进入重试') })
    return () => { active = false }
  }, [project.project_id, candidatesOpen, boundary?.policy_epoch, loading])
  const showCandidates = (open: boolean) => {
    if (open) listPosition.current = window.scrollY
    setLocalCandidatesOpen(open)
    onNavigate?.(`/permissions?project_id=${encodeURIComponent(project.project_id)}${open ? '&view=candidates' : ''}`)
  }
  const approvalInFlight = useRef(false)
  const [readingProposal,setReadingProposal]=useState(false)
  const proposalReadEpoch=useRef(0)
  useEffect(()=>()=>{proposalReadEpoch.current++},[project.project_id])
  const openProposal=async(id:string)=>{
    const epoch=++proposalReadEpoch.current;setReadingProposal(true)
    try{const value=await businessBoundariesApi.proposal(project.project_id,id);if(epoch===proposalReadEpoch.current){setProposalView(value);setEditing(null)}}
    catch(error){if(epoch===proposalReadEpoch.current)onError(error as ApiError)}
    finally{if(epoch===proposalReadEpoch.current)setReadingProposal(false)}
  }
  useTaskGuard(busy || Boolean(syncError) || approvalUncertain)
  const syncApproved = async () => {
    try {
      // 批准已经保存，两份只读同步并行；不继续占用批准按钮的写入状态。
      const [draft, workspace] = await Promise.all([businessBoundariesApi.maintenanceDraft(project.project_id), onStateChanged()])
      setMaintenanceDraft(draft)
      if (!workspace) throw new Error('工作区尚未完成同步')
      setSyncError(undefined)
    } catch { setSyncError('批准事实已保留，权限记录暂时未完成同步。请重试读取，不要重复批准。') }
  }

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError(false)
    void businessBoundariesApi.editor(project.project_id).then(async (editor) => {
      if (!active) return
      // 已有权限时先阅读生效版本；只有显式深链或初次建立权限才直接进入待审提案。
      const proposalId = requestedCandidateId ? undefined : requestedProposalId ?? (!requestedCandidatesView && !editor.boundary.permission_intents.length && editor.pending_proposals.length === 1 ? editor.pending_proposals[0].proposal_id : undefined)
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
  // 候选深链只由候选工作面读取，切换候选不重新加载正式列表或丢弃筛选。
  }, [onError, project.project_id, requestedProposalId, loadEpoch])

  const loadProvidedProposal = async () => {
    // 纠正与待定不是“不允许下载”；只有明确的布尔选择才能进入官方提案。
    if (!onProvidedProposal || providedInFlight.current || busy || providedDownloadChoiceRequired && typeof exhibitionDownload !== 'boolean') return
    providedInFlight.current = true; setBusy(true)
    try { setProposalView(await onProvidedProposal(typeof exhibitionDownload === 'boolean' ? exhibitionDownload : undefined)); setEditing(null) }
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
    setPendingOptions(items => items.filter(item => item.proposal_id !== target.proposal_id))
    setProposalView(undefined)
    setInitialCommand(undefined)
    setInitialMaintenanceCommand(undefined)
    setEditing(null)
    setSuccess('权限规则已确认，当前规则列表已更新。')
    if(candidatesOpen)showCandidates(false)
    setSyncError('正在同步权限记录。')
    // 批准回执已经成立；后续维护草稿读取失败不能留下可以再次批准的旧提案。
    onFeedback?.('权限变更已批准，正在同步当前工作。')
    void syncApproved()
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
      setPendingOptions(items => items.filter(item => item.proposal_id !== saved.proposal.proposal_id))
      setApprovalUncertain(false); setProposalView(undefined); setEditing(null)
      if(candidatesOpen)showCandidates(false)
      setSuccess(saved.decision.decision === 'APPROVED' ? '权限规则已确认。' : '这组提案已放弃，正式权限未由本次提案改变。')
      setSyncError('正在同步权限记录。')
      void syncApproved()
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }
  const rejectCurrent = async (reason: string) => {
    setEditFocus(undefined)
    if (!proposalView) return
    setBusy(true)
    try {
      await businessBoundariesApi.reject(project.project_id, proposalView.proposal, reason)
      setPendingOptions(items => items.filter(item => item.proposal_id !== proposalView.proposal.proposal_id))
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
        setPendingOptions(items => items.filter(item => item.proposal_id !== proposalView.proposal.proposal_id))
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
  if(readingProposal)return <EditorialPage label="审阅权限提案" width="summary"><EditorialHeader title="正在打开权限提案"/><LoadingState>正在读取这份提案的具体变化</LoadingState><TaskActionBar back={{label:candidatesOpen?'返回候选核对':'返回规则列表',onClick:()=>{proposalReadEpoch.current++;setReadingProposal(false)}}}/></EditorialPage>
  if (selectedRule && !editing && !proposalView) return <RuleDetailsPanel projectId={project.project_id} intentId={selectedRule.id} revision={selectedRule.revision} onNavigate={onNavigate} onBack={()=>{setSelectedRule(undefined);onRuleRoute?.(null)}} onEdit={(actionId,intentId)=>{setSelectedRule(undefined);onRuleRoute?.(null);setEditFocus({actionId,intentId});setEditing('MAINTENANCE')}}/>
  if (loading) return <div className="boundary-page"><PageTaskHeader title="权限要求" description="用业务规则说明，谁可以对谁的资源做什么。" status="正在读取" /><LoadingState>正在读取当前业务边界和待审提案</LoadingState><TaskActionBar back={{label:'返回当前工作',onClick:onBack}}/></div>
  if (loadError || !boundary || !preview) return <Result status="warning" title="业务权限暂时无法读取" subTitle="重新读取当前项目与精确提案，不重复提交变更。" extra={<TaskActionBar back={{label:'返回当前工作',onClick:onBack}} primary={{label:'重新读取',onClick:()=>setLoadEpoch(value=>value+1)}}/>} />

  const beginMaintenance = (focus: BoundaryEditFocus) => {
    setSuccess(''); setEditFocus(focus); setInitialMaintenanceCommand(undefined); setEditorKey(value => value + 1); setEditing(boundary.actors.length ? 'MAINTENANCE' : 'INITIAL')
  }
  const permissionsComplete = boundary.actions.length > 0
    && boundary.permission_statuses.every((item) => item.permission_semantics_confirmed)
  const providedEntry = !candidatesOpen && !proposalView && editing === 'INITIAL' && Boolean(onProvidedProposal) && !initialCommand && !requestedCandidateId
  const candidates = candidatesOpen && !proposalView && editing !== 'MAINTENANCE' && <RuleCandidatesPanel key={project.project_id} projectId={project.project_id} requestedId={requestedCandidateId} requestedRevision={requestedCandidateRevision}
    recoveryOperation={candidateRecoveryOperation} onRecoveryChange={onCandidateRoute} onNavigate={onNavigate} onOverview={()=>showCandidates(false)}
    onExit={() => onCandidateRoute?.(null,0,null)}
    onSelected={(id,revision) => {setEditing(null); onCandidateRoute?.(id,revision,null)}} onProposal={openProposal}/>
  return <EditorialPage label="权限规则文档" width={proposalView || candidatesOpen ? undefined : 'summary'}>
    {editing !== 'MAINTENANCE' && <EditorialHeader eyebrow={project.name || '当前应用'} title={proposalView ? proposalView.decision ? '权限变更记录' : '审阅权限变更' : candidatesOpen ? '整理本轮权限要求' : editing ? '建立权限规则' : '权限要求'} status={!candidatesOpen && !proposalView && !editing && <span className="boundary-version">权限版本 {boundary.policy_epoch} · {boundary.permission_intents.length} 条生效规则</span>}><p className="editorial-muted">{candidatesOpen && !proposalView ? '沿用已保存的角色与动作，先确认本轮要求，再审阅并批准完整规则。' : !proposalView && !editing ? (!boundary.permission_intents.length && boundary.policy_epoch === 0 ? '尚未批准权限。已保存的业务信息和候选仍保留，可进入“整理权限候选”继续。' : permissionsComplete ? '查看各个角色在不同资源上的权限，后续检查以已确认的规则为依据。' : '部分业务动作仍需确认权限，详见下方清单。') : providedEntry ? '角色和动作已整理。现在需要明确：谁可以对谁的资源做什么。' : proposalView ? proposalView.decision ? '这份提案已有决定。下方保留当时审阅的变更；继续当前工作可查看最新任务。' : '下方是本次待审提案。核对具体变化后，再决定是否批准。' : '先由 Agent 整理业务约定，再核对候选并批准权限规则。'}</p></EditorialHeader>}
    {(proposalView || !candidatesOpen && editing === 'INITIAL') && <RulePreparationStages
      phase={proposalView ? proposalView.decision?.decision === 'APPROVED' ? 3 : 2 : 1}
      complete={proposalView?.decision?.decision === 'APPROVED'}
      note={proposalView?.decision?.decision === 'REJECTED' ? '本次提案已放弃' : providedEntry ? '核对草稿中的允许与禁止' : undefined}
    />}
    {success && <TaskReceipt message={success} pending={syncError} onRetry={syncError && !busy ? () => void syncApproved() : undefined}/>}
    {approvalUncertain && <Alert type="warning" message="批准回执尚未确认。请先核对同一提案的决定，不要重复批准。" action={<Button loading={busy} onClick={() => void readApproval()}>核对批准结果</Button>}/>}
    {!candidatesOpen && !proposalView && editing !== 'MAINTENANCE' && !initialCommand && <section className="boundary-candidate-entry" aria-label="权限候选入口"><div><strong>{boundary.policy_epoch>0 ? '通过 Agent 新增、修改或停用规则' : '从业务约定开始整理权限'}</strong><p>{candidateSummary}。{boundary.policy_epoch>0?'保留现有规则，读取本次候选后审阅变更；批准后才生效。':'把要求交给原 Agent，保存后在这里读取。'}</p></div><Button type="primary" onClick={() => showCandidates(true)}>{boundary.policy_epoch>0?'Agent 整理与读取候选':'整理权限候选'}</Button></section>}
    {!proposalView && !editing && <section className="boundary-browser" hidden={candidatesOpen}><CurrentBoundary requestedActionId={requestedActionId} boundary={boundary} onEdit={beginMaintenance} onRule={(id,revision)=>{setSelectedRule({id,revision});onRuleRoute?.(id,revision)}} /></section>}
    {!providedEntry && candidates}
    {!candidatesOpen && !proposalView && pendingOptions.length > 0 && <section className="boundary-pending-choices"><h2>待审权限提案</h2><p>批准后才会更新生效权限。</p>{pendingOptions.map((item,index)=><Button key={item.proposal_id} onClick={()=>void openProposal(item.proposal_id)}>审阅提案 {index+1}</Button>)}</section>}

    {proposalView
      ? <BoundaryProposalReview key={proposalView.proposal.proposal_id} proposalView={proposalView} onRules={()=>{setProposalView(undefined);setEditing(null);setLocalCandidatesOpen(false);onNavigate?.(`/permissions?project_id=${encodeURIComponent(project.project_id)}`)}} onContinue={onNavigate?()=>onNavigate(`/workspace?project_id=${encodeURIComponent(project.project_id)}`):undefined} busy={busy || approvalUncertain} onApprove={(reason) => void approveCurrent(reason)} onReturnToEdit={() => { void returnToEdit() }} onReject={(reason) => void rejectCurrent(reason)} />
      : !candidatesOpen && editing === 'INITIAL'
        ? onProvidedProposal && !initialCommand ? <section className="boundary-provided-proposal" aria-label="提供的权限材料">
            <header><h2>核对官方示例的权限草稿</h2><p className="editorial-muted">这份草稿随官方示例提供，不是本次源码分析或 Agent 自动生成的结论。先选择评审的下载权限，再审阅完整规则；经你批准后才会生效。</p></header>
            {providedDownloadChoiceRequired&&<fieldset className="provided-meaning-choice"><legend>评审能否下载只含公开内容的展示版？</legend>
              <Radio.Group className="product-choice-cards" aria-label="展示版下载要求" value={exhibitionDownload} disabled={busy} onChange={event=>setExhibitionDownload(event.target.value)}>
                <Radio aria-label="允许下载展示版" value={true}><strong>允许下载展示版</strong><span>可以离线查看已经公开的内容。</span></Radio>
                <Radio aria-label="仅允许在线预览" value={false}><strong>仅允许在线预览</strong><span>保留在线浏览，不提供展示版下载。</span></Radio>
                <Radio aria-label="这些都不是" value="OTHER"><strong>这些都不是</strong><span>现有选项不符合要求，改为整理自己的约定。</span></Radio>
                <Radio aria-label="暂不确定" value="DEFER"><strong>暂不确定</strong><span>先不作决定，明确需求后再继续。</span></Radio>
              </Radio.Group>
              <p className="editorial-muted" role="status">{exhibitionDownload === 'OTHER' ? '可以自行编写权限草稿，也可以进入“整理权限候选”，请 Agent 协助整理实际要求。' : exhibitionDownload === 'DEFER' ? '当前不生成权限提案。明确需求后，再选择符合要求的选项。' : '你的选择会写入待审权限提案；内部完整包仍受限制。'}</p>
            </fieldset>}
            <div className="boundary-entry-actions">
              {exhibitionDownload !== 'OTHER' && <Button type="link" aria-expanded={manualOpen} onClick={() => setManualOpen(!manualOpen)}>自行编写权限草稿</Button>}
              {exhibitionDownload === 'OTHER' ? <Button type={manualOpen ? 'default' : 'primary'} aria-expanded={manualOpen} onClick={() => setManualOpen(!manualOpen)}>{manualOpen ? '收起自定义草稿' : '编写我的权限要求'}</Button>
                : <Button type="primary" loading={busy} disabled={providedDownloadChoiceRequired&&typeof exhibitionDownload!=='boolean'} onClick={() => void loadProvidedProposal()}>使用已提供的权限提案</Button>}
            </div>{manualOpen && <BoundaryProposalEditor key={editorKey} preview={preview} busy={busy} onSubmit={(command) => void createProposal(command)} />}
          </section> : <>{initialCommand ? <BoundaryProposalEditor key={editorKey} preview={preview} initialCommand={initialCommand} busy={busy} onSubmit={(command) => void createProposal(command)} /> : <details className="boundary-manual-entry"><summary>自行编写权限草稿</summary><BoundaryProposalEditor key={editorKey} preview={preview} initialCommand={initialCommand} busy={busy} onSubmit={(command) => void createProposal(command)} /></details>}</>
        : editing === 'MAINTENANCE' && maintenanceDraft
          ? <BoundaryMaintenanceEditor key={editorKey} focus={editFocus} draft={maintenanceDraft} initialCommand={initialMaintenanceCommand} busy={busy} onAgent={()=>{setEditing(null);setEditFocus(undefined);setInitialMaintenanceCommand(undefined);showCandidates(true)}} onCancel={() => { setEditing(null); setEditFocus(undefined); setInitialMaintenanceCommand(undefined) }} onSubmit={(command) => void createMaintenanceProposal(command)} />
          : !candidatesOpen && <div className="boundary-new-proposal"><Typography.Text type="secondary">修改先进入草稿，审阅并批准后才会生效。</Typography.Text></div>}
    {providedEntry && candidates}
  </EditorialPage>
}

function CurrentBoundary({ boundary, onEdit, requestedActionId, onRule }: { onRule: (id:string,revision:number)=>void; requestedActionId?: string | null; boundary: BusinessBoundaryViewDto; onEdit: (focus: BoundaryEditFocus) => void }) {
  const [selectedId, setSelectedId] = useState<string>(requestedActionId ?? '')
  useEffect(()=>{if(requestedActionId)setSelectedId(requestedActionId)},[requestedActionId])
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<'rules' | 'actions' | 'actors'>('rules')
  const [expectation, setExpectation] = useState<'ALL' | 'ALLOW' | 'DENY'>('ALL')
  const tabs = <nav className="boundary-view-tabs" aria-label="权限要求视图">{([['rules','权限规则'],['actions','业务动作'],['actors','业务角色']] as const).map(([key,label]) => <button key={key} aria-current={mode === key ? 'page' : undefined} onClick={() => setMode(key)}>{label}</button>)}</nav>
  if (mode !== 'rules') return <>{tabs}<CurrentBoundaryObjects key={mode} boundary={boundary} kind={mode} onEdit={onEdit}/></>
  const action = boundary.actions.find((item) => item.action_id === selectedId) ?? boundary.actions[0]
  if (!action) return <p>还没有正式业务边界。先整理一项动作和它必须保护的真实结果。</p>
  const matchingActions = boundary.actions.filter(item=>item.display_name.includes(query.trim()))
  const visibleRules = boundary.permission_intents.filter(rule=>rule.effective_state==='ACTIVE' && (expectation==='ALL'||rule.expectation===expectation) && matchingActions.some(item=>item.action_id===rule.business_action_id&&item.revision===rule.action_revision))
  if (!selectedId) return <>{tabs}<div className="boundary-collection-toolbar"><SearchField aria-label="搜索业务动作" placeholder="搜索业务动作" allowClear value={query} onChange={event=>setQuery(event.target.value)}/><Segmented aria-label="筛选权限要求" options={[{label:"全部规则",value:"ALL"},{label:"允许",value:"ALLOW"},{label:"禁止",value:"DENY"}]} value={expectation} onChange={value=>setExpectation(value as typeof expectation)}/><Button type="primary" onClick={()=>onEdit({actionId:action.action_id,mode:'new'})}>新增规则</Button></div>
    <section className="light-permission-list" aria-label="当前权限清单">{matchingActions.map(item=>{
      const rules=boundary.permission_intents.filter(rule=>rule.business_action_id===item.action_id&&rule.action_revision===item.revision&&rule.effective_state==='ACTIVE')
      const visible=rules.filter(rule=>expectation==='ALL'||rule.expectation===expectation)
      if (expectation!=='ALL'&&!visible.length) return null
      const condition=boundary.permission_statuses.find(value=>value.action_id===item.action_id)
      return <section key={item.action_id}>
        {condition?.reason_codes.includes('PERMISSION_REVISION_REVIEW_REQUIRED')&&<p role="status">当前业务版本需要重新确认权限；原权限仍保留为历史。</p>}
        {condition?.permission_semantics_confirmed&&condition.reason_codes.includes('ALLOW_CONTROL_REQUIRED')&&<><p role="status">权限已确认，还需完整允许对照</p><p>缺少覆盖同一业务结果的允许对照；已确认的拒绝规则仍然保留。</p></>}
        {condition?.reason_codes.includes('PERMISSION_SEMANTICS_REQUIRED')&&<p role="status">当前权限尚未确认</p>}
        <PermissionRuleRows boundary={boundary} action={item} rules={visible} onRule={onRule} onEdit={intentId=>onEdit({actionId:item.action_id,intentId})}/>
        {!rules.length && <Button type="link" onClick={()=>setSelectedId(item.action_id)}>查看动作</Button>}
      </section>
    })}{(!matchingActions.length || (expectation!=='ALL'&&!visibleRules.length))&&<p>没有符合筛选条件的权限规则。</p>}</section></>
  const status = boundary.permission_statuses.find((item) => item.action_id === action.action_id)
  const binding = boundary.action_bindings.find((item) => item.action_id === action.action_id)?.status
  const permissions = boundary.permission_intents.filter((item) => item.business_action_id === action.action_id && item.action_revision === action.revision && item.effective_state === 'ACTIVE')
  return <>{tabs}<Button type="link" onClick={()=>setSelectedId('')}>← 返回全部权限要求</Button><div className="boundary-collection-toolbar"><SearchField aria-label="搜索业务动作" placeholder="搜索业务动作" allowClear value={query} onChange={event=>setQuery(event.target.value)}/><Button type="primary" onClick={()=>onEdit({actionId:action.action_id,mode:'new'})}>新增规则</Button></div><section className="boundary-document" aria-label="当前业务动作与权限">
    <nav className="action-index" aria-label="业务动作索引"><h3>业务动作</h3>{boundary.actions.filter(item => item.display_name.includes(query.trim())).map((item) => <button key={item.action_id} aria-current={item.action_id === action.action_id ? 'true' : undefined} onClick={() => setSelectedId(item.action_id)}>{item.display_name}<small>{boundary.permission_intents.filter(rule => rule.business_action_id === item.action_id && rule.action_revision === item.revision && rule.effective_state === 'ACTIVE').length} 条规则</small></button>)}{!boundary.actions.some(item => item.display_name.includes(query.trim())) && <p>没有匹配的动作</p>}</nav>
    <article className="boundary-action-document"><div className="boundary-action-heading"><div><h2>{action.display_name}</h2><p className="editorial-muted">{action.description}</p></div></div>
      {status?.reason_codes.includes('PERMISSION_REVISION_REVIEW_REQUIRED') && <p role="status">当前业务版本需要重新确认权限；原权限仍保留为历史。</p>}
      {status?.permission_semantics_confirmed && status.reason_codes.includes('ALLOW_CONTROL_REQUIRED') && <><p role="status">权限已确认，还需完整允许对照</p><p>缺少覆盖同一业务结果的允许对照；已确认的拒绝规则仍然保留。</p></>}
      {status?.reason_codes.includes('PERMISSION_SEMANTICS_REQUIRED') && <p role="status">当前权限尚未确认</p>}
      <PermissionRuleRows boundary={boundary} action={action} rules={permissions} onRule={onRule} onEdit={intentId=>onEdit({actionId:action.action_id,intentId})}/>
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
