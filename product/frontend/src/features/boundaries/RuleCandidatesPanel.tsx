// 规则候选按原文和具体情形审阅；未知写回执只查询，陈旧响应不得跨项目覆盖。
import { Alert, Button, Spin } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ruleCandidatesApi, type MeaningChoice, type BoundaryChoice, type ScopeChoice, type CoverageChoice, type RuleCandidateContext, type RuleCandidateView } from '../../api/boundaries/ruleCandidates'
import type { ApiError } from '../../api/http'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { AgentAssistEntry } from '../../shared/ui/AgentAssistEntry'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { RuleMeaningReview } from './RuleMeaningReview'
import { BoundaryReview } from './BoundaryReview'
import {RuleScopeReview} from './RuleScopeReview'
import { RequirementNotice } from '../../shared/ui/RequirementNotice'
import { RulePreparationProgress } from './RulePreparationProgress'
import { RulePreparationStages } from '../../shared/ui/RulePreparationStages'
import { RuleCandidateList } from './RuleCandidateList'
import { CandidateWorkPlan } from './CandidateWorkPlan'
import './rule-candidates.css'

export function RuleCandidatesPanel({ projectId, requestedId, requestedRevision, recoveryOperation, onProposal, onSelected, onRecoveryChange, onExit, onNavigate, onOverview }: {
  projectId: string; requestedId?: string | null; requestedRevision?: number
  onProposal: (proposalId: string) => Promise<void>
  recoveryOperation?: string | null
  onSelected: (id: string, revision: number) => void
  onExit?: () => void
  onOverview?: () => void
  onNavigate?: (path: string) => void
  onRecoveryChange?: (id: string, revision: number, operation: string | null) => void
}) {
  const [context, setContext] = useState<RuleCandidateContext>()
  const [selected, setSelected] = useState<RuleCandidateView>()
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [operation, setOperation] = useState<string>()
  const [epoch, setEpoch] = useState(0)
  const [archived, setArchived] = useState(false)
  const [listOpen, setListOpen] = useState(false)
  const [rulesOpen, setRulesOpen] = useState(false)
  const [scopeDirty, setScopeDirty] = useState(false)
  const [copiedRequest, setCopiedRequest] = useState(false)
  const [notice, setNotice] = useState<string>()
  const [visibilityUncertain, setVisibilityUncertain] = useState(false)
  const current = useRef(0)
  const inFlight = useRef(false)
  useTaskGuard(busy || Boolean(operation))
  useEffect(()=>{setRulesOpen(false)},[projectId,requestedId])
  useEffect(()=>{setCopiedRequest(false);setNotice(undefined);setArchived(false);setListOpen(false)},[projectId])

  useEffect(() => {
    const generation = ++current.current
    setLoading(true); setBusy(false); setSelected(undefined); setError(undefined); setNotice(undefined)
    // 仅恢复URL里的有限操作引用；刷新不丢失未知回执，也不保存候选正文到浏览器存储。
    setOperation(recoveryOperation ?? undefined)
    void ruleCandidatesApi.context(projectId, 0, archived).then(async value => {
      const item = requestedId ? await ruleCandidatesApi.show(projectId, requestedId, requestedRevision) : undefined
      if (generation !== current.current) return
      setContext(value); setSelected(item); setVisibilityUncertain(false)
    }).catch(() => { if (generation === current.current) setError('规则候选暂时无法读取；已有正式权限没有改变。') })
      .finally(() => { if (generation === current.current) setLoading(false) })
    return () => { current.current += 1 }
  }, [projectId, requestedId, requestedRevision, epoch, archived])

  const select = async (id: string, revision?: number) => {
    if (inFlight.current) return
    const generation = ++current.current
    setLoading(true); setError(undefined)
    try {
      const item = await ruleCandidatesApi.show(projectId, id, revision)
      if (generation === current.current) { setSelected(item); setNotice(undefined); onSelected(id, item.candidate.revision) }
    } catch { if (generation === current.current) setError('这条候选无法读取，请重新核对。') }
    finally { if (generation === current.current) setLoading(false) }
  }
  const nextPage = async () => {
    if (context?.next_offset == null || inFlight.current) return
    inFlight.current = true; setBusy(true)
    const generation = current.current
    try { const value = await ruleCandidatesApi.context(projectId, context.next_offset, archived); if (generation === current.current) {setContext(value); setError(undefined)} }
    catch { if (generation === current.current) setError('下一页候选暂时无法读取，当前列表已保留。') }
    finally { inFlight.current = false; if (generation === current.current) setBusy(false) }
  }

  const changeVisibility = async (nextArchived: boolean) => {
    if (!selected || inFlight.current || operation || visibilityUncertain) return
    const generation = current.current, item = selected.candidate
    inFlight.current = true; setBusy(true); setError(undefined)
    try {
      const visibility = await ruleCandidatesApi.visibility(projectId, item.candidate_id, item.revision, selected.visibility?.version ?? 0, nextArchived)
      if (generation !== current.current) return
      setSelected({...selected, visibility}); setNotice(nextArchived ? undefined : '候选已恢复，可以继续整理或审阅。')
    } catch (failure) {
      // 状态写入没有回执时只读取；不能以第二次归档/恢复试探第一次结果。
      try {
        const latest = await ruleCandidatesApi.show(projectId, item.candidate_id)
        if (generation === current.current) { setSelected(latest); setNotice(latest.visibility?.archived===nextArchived ? '已回读确认候选当前状态。' : (failure as ApiError).code==='STATE_PRECONDITION' ? (failure as Error).message : '本次操作结果未确认，已回读当前状态；未重复提交。') }
      } catch { if (generation === current.current) {setVisibilityUncertain(true); setError('归档状态尚未确认，请读取候选后继续；原记录没有被删除。')} }
    } finally { inFlight.current = false; if (generation === current.current) setBusy(false) }
  }

  const supplement = async () => {
    if (!selected || inFlight.current) return
    const generation = current.current
    inFlight.current = true; setBusy(true); setError(undefined)
    try {
      const latest = await ruleCandidatesApi.show(projectId, selected.candidate.candidate_id)
      if (generation !== current.current) return
      setSelected(latest)
      if (latest.candidate.revision !== selected.candidate.revision || latest.visibility?.archived) {setNotice('候选已有变化，请核对最新内容后继续。'); return}
      await navigator.clipboard.writeText([`请补充界鉴项目 ${projectId} 的规则候选 ${latest.candidate.candidate_id}，修订 ${latest.candidate.revision}。`,
        '先调用 jiejian_rule_context 和 jiejian_rule_candidate_show 读取最新内容，再读取 jiejian_application_understanding 沿用已确认的角色和动作。',
        '先修正明确的草稿错误。USER只表示最终业务决定需要我作出，不禁止你修订其他草稿、补充关联或提出纠正建议。不要因为存在USER事项而说无事可做。',
        ...(latest.next_tasks ?? latest.issues).map(item => `${'handler' in item ? {USER:'需用户确认，勿代办',AGENT:'请修改候选',CAPABILITY:'能力或覆盖问题，先说明可行路径'}[item.handler] : '需要处理'}${item.path ? `（${item.path}）` : ''}：${item.message}${item.permission_item_ids?.length?` 对应权限项：${item.permission_item_ids.join('、')}`:''}`),
        ...(latest.revision_guidance ?? []),
        ...(latest.scope_review ?? []).filter(item=>item.status==='CONFIRMED').map(item=>`已确认范围（沿用，不重复提问）：${item.source.title}；${item.decision?.disposition}；实际要求：${item.decision?.requirement}；时间：${item.decision?.time_scope}`),
        ...(latest.boundary_reviews ?? []).filter(item=>item.status==='RESOLVED').map(item=>`已解决，保留原文与决定，不重复处理：${item.text}；实际要求：${item.decision?.retained_requirement}`),
        ...(latest.coverage_review ?? []).map(item=>`检查关联${item.status}：${item.message}；读取coverage_review中的具体入口与权限，不把关联当成已取证。`),
        '只处理当前未解决事项。需要修正规则时用 jiejian_rule_candidate_save 更新原候选，可merge=true分批补充；保持来源、已确认要求和正常使用对照。',
        '没有范围清单时先补requirement_sources；不要把全部源码接口自动变成本轮权限，不凭空扩大历史范围。',
        '仅有真实权限歧义才提供情境；范围判断由我在本轮业务范围确认。材料缺口走准备流程，能力不足明确说明，不能说记录限制即可通过。返回准确review_url，不替我批准。'].join('\n'))
      if (generation === current.current) {setCopiedRequest(true);setNotice('补充请求已复制，请粘贴到原 Agent 对话中；保存后读取候选。')}
    } catch { if (generation === current.current) setError('暂时无法复制补充请求，请重新读取候选后重试。') }
    finally {inFlight.current=false; if(generation===current.current)setBusy(false)}
  }
  const openProposal = async (value: RuleCandidateView) => {
    if (!value.proposal_id) return
    await onProposal(value.proposal_id)
    setSelected(undefined)
  }
  const propose = async () => {
    if (!selected || inFlight.current || operation) return
    inFlight.current = true; setBusy(true); setError(undefined)
    const generation = current.current
    const key = crypto.randomUUID().replaceAll('-', '')
    setOperation(key)
    onRecoveryChange?.(selected.candidate.candidate_id, selected.candidate.revision, key)
    try {
      const value = await ruleCandidatesApi.propose(projectId, selected.candidate.candidate_id, selected.candidate.revision, key)
      if (generation !== current.current) return
      setOperation(undefined)
      onRecoveryChange?.(selected.candidate.candidate_id, selected.candidate.revision, null)
      setSelected(value)
      // 写入已确认；提案读取失败时只允许重新打开这个提案，不再创建。
      try { await openProposal(value) } catch { setError('提案已保存，暂时无法打开；请继续查看已保存提案。') }
    } catch (failure) {
      if (generation !== current.current) return
      const code = (failure as ApiError).code
      if (['STATE_PRECONDITION', 'BOUNDARY_PROPOSAL_PENDING', 'INPUT_INVALID', 'BOUNDARY_REVISION_CONFLICT'].includes(code)) {
        setOperation(undefined); onRecoveryChange?.(selected.candidate.candidate_id, selected.candidate.revision, null)
        setError((failure as Error).message)
      }
      else { setOperation(key); setError('尚未确认提案保存结果。请查询原操作，避免重复创建。') }
    } finally { inFlight.current = false; if (generation === current.current) setBusy(false) }
  }
  const recover = async () => {
    if (!operation || inFlight.current) return
    const generation = current.current
    inFlight.current = true; setBusy(true)
    try {
      const deciding = operation.startsWith('DECIDE:')
      const receipt = deciding ? await ruleCandidatesApi.receipt(projectId, operation.slice(7), 'DECIDE') : await ruleCandidatesApi.receipt(projectId, operation)
      if (generation !== current.current) return
      if (receipt.status === 'FOUND' && receipt.candidate) {
        setOperation(undefined); setSelected(receipt.candidate); setError(undefined)
        onRecoveryChange?.(receipt.candidate.candidate.candidate_id, receipt.candidate.candidate.revision, null)
        if (!deciding) try { await openProposal(receipt.candidate) } catch { setError('提案已保存，请继续查看已保存提案。') }
      } else setError('原操作尚无确定回执，请稍后继续查询。')
    } catch { if (generation === current.current) setError('回执暂时无法读取，请稍后查询同一操作。') }
    finally { inFlight.current = false; if (generation === current.current) setBusy(false) }
  }

  const saveMeaning = async (choice: MeaningChoice | BoundaryChoice | ScopeChoice | CoverageChoice | ScopeChoice[]): Promise<boolean> => {
    if (!selected || inFlight.current || operation) return false
    const generation = current.current, key = crypto.randomUUID().replaceAll('-', ''), recovery = `DECIDE:${key}`
    inFlight.current = true; setBusy(true); setError(undefined); setOperation(recovery)
    onRecoveryChange?.(selected.candidate.candidate_id, selected.candidate.revision, recovery)
    try {
      const value = Array.isArray(choice) || 'requirement_id' in choice
        ? await ruleCandidatesApi.scopeBatch(projectId,selected.candidate.candidate_id,selected.candidate.revision,selected.candidate.basis_id,key,Array.isArray(choice)?choice: [choice])
        : 'targets' in choice
        ? await ruleCandidatesApi.coverage(projectId,selected.candidate.candidate_id,selected.candidate.revision,selected.candidate.basis_id,key,choice)
        : 'issue_id' in choice
        ? await ruleCandidatesApi.reviewBoundary(projectId, selected.candidate.candidate_id, selected.candidate.revision, selected.candidate.basis_id, key, choice)
        : await ruleCandidatesApi.decide(projectId, selected.candidate.candidate_id, selected.candidate.revision, selected.candidate.basis_id, key, choice)
      if (generation !== current.current) return false
      setSelected(value); setOperation(undefined)
      onRecoveryChange?.(value.candidate.candidate_id, value.candidate.revision, null)
      return true
    } catch (failure) {
      if (generation !== current.current) return false
      if (['STATE_PRECONDITION','INPUT_INVALID'].includes((failure as ApiError).code)) {
        setOperation(undefined); onRecoveryChange?.(selected.candidate.candidate_id,selected.candidate.revision,null)
        setError((failure as Error).message)
      } else setError('尚未确认这次选择是否保存。请查询原操作，避免重复提交。')
      return false
    } finally { inFlight.current=false; if(generation===current.current)setBusy(false) }
  }

  // 整理和读取在同一候选区交接；已有读取按钮时，展开内容不再生成第二个读取入口。
  // 初次深链保留指定历史修订；用户显式读取时查询最新头，避免永远停在旧rev。
  const readLatest = () => {
    const id = selected?.candidate.candidate_id ?? requestedId
    if (id) void select(id)
    else {setListOpen(true);setEpoch(value => value + 1)}
  }
  const sourceOverview = context && !archived && <RulePreparationProgress context={context}/>
  const heading = (content: ReactNode) => {
    const refresh = <Button type={copiedRequest || !selected && Boolean(context?.formal_permission_count) ? 'primary' : 'default'} disabled={busy || Boolean(operation)} onClick={readLatest}>{selected ? '读取候选' : '读取 Agent 整理结果'}</Button>
    const maintaining=Boolean(context?.formal_permission_count)
    const intro = <div className="rule-intake-intro"><h2>{maintaining?'继续在原 Agent 对话中新增规则':'把本轮权限要求交给原来的 Agent'}</h2><p>{maintaining?'说明要新增或调整什么。Agent 保存后，点击右侧读取候选，核对并批准本次变化。':'说明谁能对谁的资源做什么。Agent 可以一次整理多条权限，你回来确认具体含义与检查范围。'}</p><ol><li><strong>你说明业务要求</strong><span>例如“负责人可以下载自己的内部包，评审不可以”。这是示例，请按实际业务说明。</span></li><li><strong>Agent 批量整理并保存</strong><span>沿用已有角色、动作和规则，保存本次权限候选及其来源。</span></li><li><strong>你核对后批准最终稿</strong><span>只处理待确认的含义和检查范围，最后审阅完整变更。</span></li></ol></div>
    if (!onNavigate || selected?.visibility?.archived) return <div className="rule-candidates-heading"><div>{selected ? content : intro}</div>{refresh}</div>
    return <AgentAssistEntry aside projectId={projectId} contextKey={`rules:${requestedId ?? ''}:${requestedRevision ?? ''}`}
      heading={selected ? content : intro} actions={refresh} primary={!maintaining && !selected && !archived && !context?.candidates.length && !copiedRequest} initialOpen={!maintaining && !selected && !archived && context?.candidates.length===0} buttonLabel={selected ? 'Agent 协助' : '交接给 Agent'} onCopied={() => setCopiedRequest(true)}
      title={selected ? '继续让 Agent 补充' : '把请求带回原对话'} description={selected ? '保留已确认的要求，补充后读取新修订。' : '复制下方请求，粘贴到 DSH、Codex 等原对话中，并补上你的业务要求。Agent 保存后，再读取整理结果。'}
      returnTo={requestedId ? `/permissions?candidate=${encodeURIComponent(requestedId)}&revision=${requestedRevision ?? 1}&project_id=${encodeURIComponent(projectId)}` : '/permissions?view=candidates'}
      onNavigate={onNavigate} loadContext={async () => {
        const value = await ruleCandidatesApi.context(projectId)
        return { projectId:value.project_id, revisionKey:JSON.stringify([value.basis_id,value.candidates.map(item => [item.candidate_id,item.revision])]),
          requestText:[`请协助整理界鉴项目 ${value.project_id} 的业务权限。`,
            '先调用 jiejian_rule_context 和 jiejian_application_understanding 读取当前约定与源码线索，区分用户期望、代码现状和推测。',
            requestedId ? `当前候选：${requestedId}，修订 ${requestedRevision ?? 1}；先回读，旧依据不能覆盖新内容。` : '读取我在原对话中提出的本轮业务目标；已有明确信息不重复提问。整理requirement_sources，区分用户原话、源码发现与Agent建议。',
            '用 jiejian_rule_candidate_save 批量保存权限候选及requirement_sources，可一次提交，不要求先保存空权限再返回生成。确实无法整理时才先保存范围。登录、造数据、恢复步骤不自动新增为业务权限。',
            '用permission_item_ids关联来源，提供必要合法对照；已有scope_review决定必须沿用。含义不清时提供具体情境，本轮是否检查由我在界鉴确认。可merge=true分批补充同一候选，不能替我确认或批准。',
            '新增规则先沿用当前稳定角色、动作和权限引用，不重复创建已有规则。修改或停用已有规则必须引用当前intent_id与expected_current_revision；停用使用effective_state=RETIRED，不靠漏传规则删除，保留其他规则和历史。',
            `复制时的业务依据：${value.basis_id}。保存前重新读取，不因这里的旧引用跳过核对。`,
            '应用未运行也可先整理。不要自行启动应用、执行请求、扩大读取授权或索取凭据。'].join('\n') }
      }}/>
  }

  if (loading && !listOpen) return <section className="rule-candidates-inbox" aria-label="读取规则候选"><Spin size="small" /> 正在读取规则候选</section>
  if (!selected) return <section className="rule-candidates-inbox" aria-label="对话规则候选">

    {!listOpen && <>{sourceOverview}{heading(null)}</>}
    {error && <Alert type="warning" message={error} />}
    <RequirementNotice gaps={context?.boundary_review_gaps ?? []} listedCandidateIds={listOpen&&!loading?(context?.candidates??[]).map(item=>item.candidate_id):[]} purpose="candidate" disabled={busy || Boolean(operation)} onOpen={gap=>void select(gap.candidate_id,gap.revision)}/>
    {!listOpen ? <section className="rule-results-entry" aria-label="整理结果入口"><div><h2>Agent 保存的整理结果</h2><p>{error ? '当前结果尚未读取，请进入后重新读取。' : context?.candidates.length ? `本页已读取 ${context.candidates.length} 条整理结果，进入后核对范围与规则。` : 'Agent 保存后，从这里查看并继续核对。'}</p></div><Button onClick={()=>setListOpen(true)}>查看整理结果 →</Button></section> : <>
    <Button type="link" disabled={loading||busy} onClick={()=>{setListOpen(false);setArchived(false)}}>← 返回权限整理</Button>
    <div className="rule-candidates-list-heading"><div className="rule-candidates-title"><h2>{archived ? '已归档的整理记录' : 'Agent 保存的整理结果'}{!error && !!context?.candidates.length && <span> · 本页 {context.candidates.length} 条</span>}</h2><p>{error ? '读取后核对尚未批准的约定。' : archived ? '原文、修订和决定保留，可在详情中恢复。' : context?.candidates.length ? '打开一条，先核对本轮范围，再核对具体允许与禁止。' : '尚未读到整理结果。把请求交给 Agent 后，在这里继续；保存候选不会自动批准权限。'}</p></div></div>
    <div className="rule-results-toolbar"><nav className="product-view-tabs" aria-label="整理结果分类">{[{label:'当前候选',value:false},{label:'已归档',value:true}].map(tab=><Button key={tab.label} type="text" aria-pressed={archived===tab.value} disabled={busy||loading} onClick={()=>{setArchived(tab.value);setNotice(undefined)}}>{tab.label}</Button>)}</nav><Button disabled={loading||busy || Boolean(operation)} onClick={readLatest}>重新读取整理结果</Button>
    </div>
    {loading ? <p><Spin size="small"/> 正在读取整理结果</p> : <>
    {!archived && !error && !context?.candidates.length && <p className="editorial-muted">当前还没有候选。请在原 Agent 保存后重新读取，或返回继续交接。</p>}
    {archived && !context?.candidates.length && <p>暂无已归档候选。归档只收起候选，原始记录会保留。</p>}
    <RuleCandidateList candidates={context?.candidates ?? []} archived={archived} onSelect={(id, revision) => void select(id, revision)}/>
    {context?.next_offset != null && <Button loading={busy} onClick={() => void nextPage()}>下一页候选</Button>}</>}</>}
    {!listOpen&&onOverview&&<details className="rule-other-entry"><summary>其他入口 · 查看现有规则或使用官方示例草稿</summary><p>这是独立的权限总览，不是本次 Agent 整理的上一步。</p><Button onClick={onOverview}>打开权限总览</Button></details>}
  </section>

  const content = selected.candidate.content
  const confirmed = selected.assessment === 'ALREADY_CONFIRMED'
  const isArchived = selected.visibility?.archived ?? false
  const leave = () => {setSelected(undefined);setListOpen(true); setNotice(undefined); setEpoch(value=>value+1); onExit?.()}
  const permissions = new Map(content.permissions.map(item => [item.item_id, item]))
  const pendingQuestions = content.unresolved_questions.filter(question => !content.scenarios?.some(scene => scene.question === question) && !selected.boundary_reviews?.some(item=>item.text===question))
  const needsBoundary = selected.boundary_reviews?.some(item=>item.blocking)
  const needsMeaning = content.scenarios?.some(scene => !['SELECT','DISMISS','CORRECT'].includes(selected.scenario_decisions?.find(state => state.scenario_id === scene.scenario_id)?.status ?? 'NEEDS_DECISION'))
  const needsScope = selected.scope_review?.some(item=>item.status!=='CONFIRMED')
  // 范围确认与规则审阅分开呈现；后续修订使范围失效时，仍回到人工确认而不跳过门禁。
  const scopeFirst=Boolean(selected.scope_review?.length)&&!selected.decision&&!isArchived&&(!rulesOpen||needsScope)
  const frozen=busy||Boolean(operation)||visibilityUncertain
  const userDecisionOnly=!isArchived&&!selected.decision&&!operation&&!visibilityUncertain&&selected.assessment==='NEEDS_CHANGES'&&Boolean(selected.next_tasks?.length)&&selected.next_tasks!.every(item=>item.handler==='USER')
  const agentFirst=!rulesOpen&&!selected.decision&&!isArchived&&!operation&&!visibilityUncertain&&selected.next_tasks?.some(item=>item.handler==='AGENT')
  if(agentFirst) return <section className="rule-candidates" aria-label="修正权限草稿">
    <CandidateWorkPlan value={selected} busy={frozen} copied={copiedRequest} onCopy={()=>void supplement()} onRead={readLatest} onReview={()=>{setRulesOpen(true);window.scrollTo({top:0,behavior:'instant'})}}/>
    {error&&<Alert type="warning" message={error}/>}
    <div className="scope-support-actions"><Button type="link" disabled={frozen} onClick={leave}>← 返回整理结果</Button></div>
  </section>
  if(scopeFirst) return <section className="rule-candidates" aria-label="核对本轮范围">
    {!context?.formal_permission_count&&<RulePreparationStages phase={1}/>}
    <div className="scope-candidate-meta"><span>Agent 整理 · 修订 {selected.candidate.revision} · 尚未批准权限</span></div>
    <RuleScopeReview value={selected} readOnly={false} busy={frozen} onSave={saveMeaning} onBatchSave={saveMeaning} onDirtyChange={setScopeDirty}
      continueLabel={selected.proposal_id?'审阅已保存的最终稿':selected.scope_only?'完成，返回整理结果':confirmed?'查看当前规则':selected.assessment==='REVIEWABLE'?'审阅最终稿':'查看仍需澄清的内容'}
      onContinue={()=>{if(selected.proposal_id)void openProposal(selected).catch(()=>setError('提案暂时无法读取'));else if(selected.scope_only)leave();else if(confirmed){if(onOverview)onOverview();else leave()}else if(selected.assessment==='REVIEWABLE')void propose();else{setRulesOpen(true);window.scrollTo({top:0,behavior:'instant'})}}}/>
    {error&&<Alert type="warning" message={error}/>}{notice&&<p role="status">{notice}</p>}
    {operation&&<div className="scope-actions"><Button type="primary" loading={busy} onClick={()=>void recover()}>查询原操作结果</Button></div>}
    <details className="scope-records"><summary>辅助 · 原始记录与候选管理</summary><p>{content.original_text}</p><div className="scope-support-actions"><Button disabled={frozen||scopeDirty} onClick={readLatest}>读取最新候选</Button><Button disabled={frozen||scopeDirty} onClick={leave}>返回整理结果</Button>{!selected.proposal_id&&<Button disabled={frozen||scopeDirty} onClick={()=>void changeVisibility(true)}>归档候选</Button>}{visibilityUncertain&&<Button disabled={busy||scopeDirty} onClick={()=>setEpoch(value=>value+1)}>读取归档状态</Button>}</div></details>
  </section>
  return <section className="rule-candidates" aria-label="审阅对话规则">
    {!context?.formal_permission_count&&<RulePreparationStages phase={1}/>}
    {heading(<div className="rule-candidates-title rule-candidate-detail-title"><div className="rule-candidate-title-line"><h2>{isArchived ? '查看已归档候选' : selected.decision ? '查看当时的业务约定' : selected.scope_only ? '本轮范围已记录' : confirmed ? '沿用已有业务约定' : '核对整理后的业务要求'}</h2><StatusBadge kind="rule">{isArchived ? '已归档' : selected.scope_only ? '无需新增权限' : confirmed ? '与当前规则一致' : selected.decision?.decision === 'APPROVED' ? '已有批准记录' : selected.decision ? '提案已放弃' : '尚未生效'}</StatusBadge></div><p>{selected.candidate.submitted_via === 'MCP' ? 'Agent 整理' : '本机整理'} · 修订 {selected.candidate.revision}</p></div>)}
    {isArchived && <Alert type="info" message="这条候选已归档，恢复后可以继续整理。原修订与决定记录保留。"/>}
    {notice && <p role="status" className="rule-candidate-notice">{notice}</p>}
    {!isArchived && !selected.decision && selected.assessment==='NEEDS_CHANGES' && !selected.next_tasks && <section className="rule-revision-next" aria-label="候选修订下一步">
      <h3>{needsBoundary ? '请先核对下方的业务边界与未覆盖要求' : pendingQuestions.length ? `还有 ${pendingQuestions.length} 条问题等待 Agent 整理` : needsMeaning ? '请在下方核对含义' : '请先补充候选'}</h3>
      <p>{needsBoundary ? '在下方逐条说明实际情况和仍保留的要求。确需补充规则或证据时，再将补充请求交给原 Agent；它保存后读取最新候选。' : pendingQuestions.length ? '这些问题还没有形成可供你核对的情境。点击“复制补充请求”交给原 Agent；它保存新修订后，点击“读取候选”。' : needsMeaning ? '逐处选择、说明实际要求或标记暂不确定，并保存。需要 Agent 修改时，点击“复制补充请求”；它保存后再读取候选。' : '点击“复制补充请求”，让原 Agent 按下方问题或你的纠正补充；保存新修订后，点击“读取候选”。已经保存的选择无需重复确认。'}</p>
      <p className="editorial-muted">不单独建模和 Agent 额外推断可在“业务边界核对”直接处理。真实缺口会继续阻塞；分类不会补齐证据或批准权限。</p>
    </section>}
    {!selected.decision && !!selected.next_tasks?.length && <div aria-label="当前待办数量">
      <div className="candidate-task-counts"><span><strong>{selected.next_tasks.filter(item=>item.handler==='USER').length}</strong> 项由你判断</span><span><strong>{selected.next_tasks.filter(item=>item.handler==='AGENT').length}</strong> 项交给 Agent</span><span><strong>{selected.next_tasks.filter(item=>item.handler==='CAPABILITY').length}</strong> 项检查限制</span></div>
    </div>}
    <RuleMeaningReview value={selected} readOnly={Boolean(selected.decision) || isArchived} busy={busy || Boolean(operation) || visibilityUncertain} onSave={choice=>void saveMeaning(choice)}/>
    <BoundaryReview value={selected} readOnly={Boolean(selected.decision) || isArchived} busy={busy || Boolean(operation) || visibilityUncertain} onSave={choice=>void saveMeaning(choice)} onCoverage={choice=>void saveMeaning(choice)}/>
    <details className="scope-records"><summary>辅助 · 原始要求与 Agent 说明</summary><p className="rule-candidate-original">{content.original_text}</p>{selected.candidate.supporting_notes?.map(note=><article key={note.note_id}><h4>{{SOURCE_CLUE:'源码线索',TECHNICAL_PRECONDITION:'技术前提',CAPABILITY_INFORMATION:'通用能力说明'}[note.kind]}{note.state==='WITHDRAWN'?' · 已撤回':''}</h4><p>{note.text}</p>{note.withdrawal_reason&&<p>撤回原因：{note.withdrawal_reason}</p>}</article>)}</details>
    {!!selected.scope_review?.length&&<details className="scope-records"><summary>辅助 · 回看已确认范围</summary><RuleScopeReview value={selected} readOnly busy={frozen} onSave={saveMeaning}/>{!selected.decision&&!isArchived&&<Button disabled={frozen} onClick={()=>{setRulesOpen(false);window.scrollTo({top:0,behavior:'instant'})}}>调整本轮范围</Button>}</details>}
    {!selected.decision && !!selected.next_tasks?.length &&
      <details className="scope-records"><summary>辅助 · 查看全部待办与分工</summary>
      {selected.next_tasks.map((task,index)=><div className="candidate-next-task" key={`${task.code}-${index}`}>
        <StatusBadge kind="rule" tone={task.handler==='CAPABILITY'?'warning':'neutral'}>{{USER:'由你确认',AGENT:'Agent 补充',CAPABILITY:'核对检查方式'}[task.handler]}</StatusBadge>
        <p>{task.message}</p><p className="candidate-task-next">{task.next_step}</p>
      </div>)}</details>}
    <details className="scope-records"><summary>回看整理后的允许与禁止</summary><div className="rule-example-table" role="table" aria-label="具体情形与要求">
      {content.examples.map((example, index) => <div className="rule-candidate-row" role="row" key={index}><p role="cell">{example.description}</p><span role="cell">{example.uncovered_reason ?? (permissions.get(example.permission_item_id ?? '')?.expectation === 'DENY' ? '应当拒绝' : permissions.has(example.permission_item_id ?? '') ? '应当允许' : '沿用已确认规则')}</span></div>)}
    </div></details>
    {!selected.next_tasks && selected.issues.some(item=>item.code!=='NEEDS_DECISION') && (isArchived ? <details><summary>归档时仍待核对的内容</summary><ul>{selected.issues.map((issue,index)=><li key={index}>{issue.message}</li>)}</ul></details> : <Alert type="warning" message="以下问题仍需核对" description={<ul>{selected.issues.filter(item=>item.code!=='NEEDS_DECISION').map((issue, index) => <li key={index}>{issue.message}</li>)}</ul>} />)}
    {!isArchived && !!selected.reuse.actions?.length && <p className="editorial-muted">{selected.reuse.message}</p>}
    {!!selected.reuse.actions?.length && <div aria-label="已有材料与准备缺口">{selected.reuse.actions.map(action => <div className="rule-candidate-row" key={action.item_id}>
      <div><h3>{action.display_name}</h3><p>{action.message}</p><p className="editorial-muted">{action.materials.map(kind=>({EXECUTION:'操作演示',RESOURCE:'测试资源',PROOF:'结果证明',RECOVERY:'恢复材料'}[kind] ?? kind)).join('、') || '还没有可沿用的材料'}</p></div>
      <StatusBadge kind="preparation" tone={action.status === 'MAY_REUSE' ? 'neutral' : 'warning'}>{action.status === 'MAY_REUSE' ? '可能沿用' : action.status === 'NEEDS_REVIEW' ? '需要核对' : '需要准备'}</StatusBadge>
    </div>)}</div>}
    {error && <Alert type="warning" message={error} />}
    <TaskActionBar back={{label:'返回整理结果', disabled:busy || Boolean(operation), onClick:leave}} refresh={!isArchived && !operation && !visibilityUncertain && (!selected.proposal_id || Boolean(selected.decision)) ? {label:'归档候选',disabled:busy,onClick:()=>void changeVisibility(true)} : undefined} primary={userDecisionOnly?undefined:{
      label:visibilityUncertain ? '读取归档状态' : operation ? '查询原操作结果' : isArchived ? '恢复候选' : selected.proposal_id ? '查看已保存提案' : selected.scope_only ? '返回整理结果' : confirmed ? '查看当前规则' : needsScope ? '核对本轮范围' : selected.assessment==='NEEDS_CHANGES' ? '复制补充请求' : '继续审阅完整变更',
      disabled:busy, loading:busy,
      onClick:()=>{ if(visibilityUncertain) setEpoch(value=>value+1); else if(operation) void recover(); else if(isArchived) void changeVisibility(false); else if(selected.proposal_id) void openProposal(selected).catch(()=>setError('提案暂时无法读取')); else if(confirmed) {if(onOverview)onOverview();else leave()} else if(selected.scope_only) leave(); else if(needsScope) document.querySelector('.rule-scope')?.scrollIntoView({block:'start',behavior:'smooth'}); else if(selected.assessment==='NEEDS_CHANGES') void supplement(); else void propose() },
    }}/>
  </section>
}
