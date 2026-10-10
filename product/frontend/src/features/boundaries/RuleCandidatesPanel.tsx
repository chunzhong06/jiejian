// 规则候选按原文和具体情形审阅；未知写回执只查询，陈旧响应不得跨项目覆盖。
import { Alert, Button, Segmented, Spin } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { ruleCandidatesApi, type MeaningChoice, type RuleCandidateContext, type RuleCandidateView } from '../../api/boundaries/ruleCandidates'
import type { ApiError } from '../../api/http'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { AgentAssistEntry } from '../../shared/ui/AgentAssistEntry'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { RuleMeaningReview } from './RuleMeaningReview'
import { RulePreparationProgress } from './RulePreparationProgress'
import { RuleCandidateList } from './RuleCandidateList'
import './rule-candidates.css'

export function RuleCandidatesPanel({ projectId, requestedId, requestedRevision, recoveryOperation, onProposal, onSelected, onRecoveryChange, onExit, onNavigate }: {
  projectId: string; requestedId?: string | null; requestedRevision?: number
  onProposal: (proposalId: string) => Promise<void>
  recoveryOperation?: string | null
  onSelected: (id: string, revision: number) => void
  onExit?: () => void
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
  const [copiedRequest, setCopiedRequest] = useState(false)
  const [notice, setNotice] = useState<string>()
  const [visibilityUncertain, setVisibilityUncertain] = useState(false)
  const current = useRef(0)
  const inFlight = useRef(false)
  useTaskGuard(busy || Boolean(operation))
  useEffect(()=>{setCopiedRequest(false);setNotice(undefined);setArchived(false)},[projectId])

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
        ...latest.issues.map(item => `需要处理${item.path ? `（${item.path}）` : ''}：${item.message}`),
        ...(latest.revision_guidance ?? []),
        ...latest.candidate.content.unresolved_questions.map((question,index) => `旧问题 ${index+1}（candidate.content.unresolved_questions[${index}]，转换情境时question逐字保留）：${question}`),
        ...latest.candidate.content.unsupported_constraints.map((constraint,index) => `能力限制 ${index+1}（独立核对，不能靠情境选择消除）：${constraint}`),
        '用 jiejian_rule_candidate_save 更新原候选，保留完整业务要求和受保护结果。缺失的业务约定请向我提问，不要猜测或删减。',
        '保存带情境的新修订后，给出返回的review_url；我会点击“读取候选”，在“含义核对”处理，再审阅完整变更。不要让我在尚未生成情境时寻找确认按钮。不能替我批准。'].join('\n'))
      if (generation === current.current) setNotice('补充请求已复制，请粘贴到原 Agent 对话中；保存后点击“读取候选”。')
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

  const saveMeaning = async (choice: MeaningChoice) => {
    if (!selected || inFlight.current || operation) return
    const generation = current.current, key = crypto.randomUUID().replaceAll('-', ''), recovery = `DECIDE:${key}`
    inFlight.current = true; setBusy(true); setError(undefined); setOperation(recovery)
    onRecoveryChange?.(selected.candidate.candidate_id, selected.candidate.revision, recovery)
    try {
      const value = await ruleCandidatesApi.decide(projectId, selected.candidate.candidate_id, selected.candidate.revision, selected.candidate.basis_id, key, choice)
      if (generation !== current.current) return
      setSelected(value); setOperation(undefined)
      onRecoveryChange?.(value.candidate.candidate_id, value.candidate.revision, null)
    } catch (failure) {
      if (generation !== current.current) return
      if (['STATE_PRECONDITION','INPUT_INVALID'].includes((failure as ApiError).code)) {
        setOperation(undefined); onRecoveryChange?.(selected.candidate.candidate_id,selected.candidate.revision,null)
        setError((failure as Error).message)
      } else setError('尚未确认这次选择是否保存。请查询原操作，避免重复提交。')
    } finally { inFlight.current=false; if(generation===current.current)setBusy(false) }
  }

  // 整理和读取在同一候选区交接；已有读取按钮时，展开内容不再生成第二个读取入口。
  // 初次深链保留指定历史修订；用户显式读取时查询最新头，避免永远停在旧rev。
  const readLatest = () => {
    const id = selected?.candidate.candidate_id ?? requestedId
    if (id) void select(id)
    else setEpoch(value => value + 1)
  }
  const sourceOverview = context && !archived && <RulePreparationProgress context={context}/>
  const heading = (content: ReactNode) => {
    const refresh = <Button type={copiedRequest ? 'primary' : 'default'} disabled={busy || Boolean(operation)} onClick={readLatest}>读取候选</Button>
    if (!onNavigate || selected?.visibility?.archived) return <div className="rule-candidates-heading"><div>{selected ? content : sourceOverview}</div>{refresh}</div>
    return <AgentAssistEntry aside projectId={projectId} contextKey={`rules:${requestedId ?? ''}:${requestedRevision ?? ''}`}
      heading={selected ? content : sourceOverview || <div><h2>当前权限约定</h2><p>整理候选、核对具体要求，再由你决定是否批准。</p></div>} actions={refresh} primary={!selected && !archived && !context?.candidates.length && !copiedRequest} onCopied={() => setCopiedRequest(true)}
      title="整理这项应用的权限要求" description="把当前约定和需要澄清的问题交给原来的 Agent。整理完成后，点击“读取候选”继续审阅。"
      returnTo={requestedId ? `/permissions?candidate=${encodeURIComponent(requestedId)}&revision=${requestedRevision ?? 1}&project_id=${encodeURIComponent(projectId)}` : '/permissions?view=candidates'}
      onNavigate={onNavigate} loadContext={async () => {
        const value = await ruleCandidatesApi.context(projectId)
        return { projectId:value.project_id, revisionKey:JSON.stringify([value.basis_id,value.candidates.map(item => [item.candidate_id,item.revision])]),
          requestText:[`请协助整理界鉴项目 ${value.project_id} 的业务权限。`,
            '先调用 jiejian_rule_context 和 jiejian_application_understanding 读取当前约定与源码线索，区分用户期望、代码现状和推测。',
            requestedId ? `当前候选：${requestedId}，修订 ${requestedRevision ?? 1}；先回读，旧依据不能覆盖新内容。` : '没有正式规则时，先整理角色、资源关系、动作和应当出现或禁止的结果。',
            '用 jiejian_rule_candidate_save 保存有界候选，列出关键歧义，返回界鉴审阅入口。不能替用户批准规则。',
            `复制时的业务依据：${value.basis_id}。保存前重新读取，不因这里的旧引用跳过核对。`,
            '应用未运行也可先整理。不要自行启动应用、执行请求、扩大读取授权或索取凭据。'].join('\n') }
      }}/>
  }

  if (loading) return <section className="rule-candidates-inbox" aria-label="读取规则候选"><Spin size="small" /> 正在读取规则候选</section>
  if (!selected) return <section className="rule-candidates-inbox" aria-label="对话规则候选">

    {heading(null)}
    <div className="rule-candidates-list-heading"><div className="rule-candidates-title"><h2>规则候选{!error && !!context?.candidates.length && <span> · 本页 {context.candidates.length} 条</span>}</h2><p>{error ? '读取后核对尚未批准的约定。' : archived ? '已归档候选保留原文、修订和决定，可在详情中恢复。' : context?.candidates.length ? '各条候选分别显示审阅状态；批准后才会更新正式权限。' : '先点击“Agent 协助”，将业务要求交给原开发 Agent；它保存候选后，再点击“读取候选”。最后由你核对并批准，规则才会生效。'}</p></div></div>
    {error && <Alert type="warning" message={error} />}
    <Segmented aria-label="候选归档范围" value={archived ? 'ARCHIVED' : 'ACTIVE'} options={[{label:'当前候选',value:'ACTIVE'},{label:'已归档',value:'ARCHIVED'}]} onChange={value => {setArchived(value==='ARCHIVED'); setNotice(undefined)}}/>
    {archived && !context?.candidates.length && <p>暂无已归档候选。归档只收起候选，原始记录会保留。</p>}
    <RuleCandidateList candidates={context?.candidates ?? []} archived={archived} onSelect={(id, revision) => void select(id, revision)}/>
    {context?.next_offset != null && <Button loading={busy} onClick={() => void nextPage()}>下一页候选</Button>}
  </section>

  const content = selected.candidate.content
  const confirmed = selected.assessment === 'ALREADY_CONFIRMED'
  const isArchived = selected.visibility?.archived ?? false
  const leave = () => {setSelected(undefined); setNotice(undefined); setEpoch(value=>value+1); onExit?.()}
  const permissions = new Map(content.permissions.map(item => [item.item_id, item]))
  const pendingQuestions = content.unresolved_questions.filter(question => !content.scenarios?.some(scene => scene.question === question))
  const needsMeaning = content.scenarios?.some(scene => !['SELECT','DISMISS','CORRECT'].includes(selected.scenario_decisions?.find(state => state.scenario_id === scene.scenario_id)?.status ?? 'NEEDS_DECISION'))
  return <section className="rule-candidates work-surface" aria-label="审阅对话规则">
    {heading(<div className="rule-candidates-title"><h2>{isArchived ? '查看已归档候选' : selected.decision ? '查看当时的业务约定' : confirmed ? '沿用已有业务约定' : '确认这条业务约定'}</h2><StatusBadge kind="rule">{isArchived ? '已归档' : confirmed ? '与当前规则一致' : selected.decision?.decision === 'APPROVED' ? '已有批准记录' : selected.decision ? '提案已放弃' : '尚未生效'}</StatusBadge></div>)}
    <p className="rule-candidate-original">{content.original_text}</p>
    <p className="editorial-muted">{selected.candidate.submitted_via === 'MCP' ? 'Agent 整理' : '本机整理'} · 修订 {selected.candidate.revision}。保存和准备都不代表检查通过。</p>
    {isArchived && <Alert type="info" message="这条候选已归档，恢复后可以继续整理。原修订与决定记录保留。"/>}
    {notice && <p role="status" className="rule-candidate-notice">{notice}</p>}
    {!isArchived && !selected.decision && selected.assessment==='NEEDS_CHANGES' && <section className="rule-revision-next" aria-label="候选修订下一步">
      <h3>{pendingQuestions.length ? `还有 ${pendingQuestions.length} 条问题等待 Agent 整理` : needsMeaning ? '请在下方核对含义' : '请先补充候选'}</h3>
      <p>{pendingQuestions.length ? '这些问题还没有形成可供你核对的情境。点击“复制补充请求”交给原 Agent；它保存新修订后，点击“读取候选”。' : needsMeaning ? '逐处选择、说明实际要求或标记暂不确定，并保存。需要 Agent 修改时，点击“复制补充请求”；它保存后再读取候选。' : '点击“复制补充请求”，让原 Agent 按下方问题或你的纠正补充；保存新修订后，点击“读取候选”。已经保存的选择无需重复确认。'}</p>
      <p className="editorial-muted">情境保存后会出现“含义核对”；问题处理完成后，才能继续审阅完整变更。已有明确要求与取证缺口分别保留，保存选择不会自动补齐证据或批准权限。</p>
    </section>}
    <RuleMeaningReview value={selected} readOnly={Boolean(selected.decision) || isArchived} busy={busy || Boolean(operation) || visibilityUncertain} onSave={choice=>void saveMeaning(choice)}/>
    <div className="rule-example-table" role="table" aria-label="具体情形与要求">
      {content.examples.map((example, index) => <div className="rule-candidate-row" role="row" key={index}><p role="cell">{example.description}</p><span role="cell">{example.uncovered_reason ?? (permissions.get(example.permission_item_id ?? '')?.expectation === 'DENY' ? '应当拒绝' : permissions.has(example.permission_item_id ?? '') ? '应当允许' : '沿用已确认规则')}</span></div>)}
    </div>
    {selected.issues.some(item=>item.code!=='NEEDS_DECISION') && (isArchived ? <details><summary>归档时仍待核对的内容</summary><ul>{selected.issues.map((issue,index)=><li key={index}>{issue.message}</li>)}</ul></details> : <Alert type="warning" message="以下问题仍需核对" description={<ul>{selected.issues.filter(item=>item.code!=='NEEDS_DECISION').map((issue, index) => <li key={index}>{issue.message}</li>)}</ul>} />)}
    {!isArchived && !!selected.reuse.actions?.length && <p className="editorial-muted">{selected.reuse.message}</p>}
    {!!selected.reuse.actions?.length && <div aria-label="已有材料与准备缺口">{selected.reuse.actions.map(action => <div className="rule-candidate-row" key={action.item_id}>
      <div><h3>{action.display_name}</h3><p>{action.message}</p><p className="editorial-muted">{action.materials.map(kind=>({EXECUTION:'操作演示',RESOURCE:'测试资源',PROOF:'结果证明',RECOVERY:'恢复材料'}[kind] ?? kind)).join('、') || '还没有可沿用的材料'}</p></div>
      <StatusBadge kind="preparation" tone={action.status === 'MAY_REUSE' ? 'neutral' : 'warning'}>{action.status === 'MAY_REUSE' ? '可能沿用' : action.status === 'NEEDS_REVIEW' ? '需要核对' : '需要准备'}</StatusBadge>
    </div>)}</div>}
    {error && <Alert type="warning" message={error} />}
    <TaskActionBar back={{label:'返回规则列表', disabled:busy || Boolean(operation), onClick:leave}} refresh={!isArchived && !operation && !visibilityUncertain && (!selected.proposal_id || Boolean(selected.decision)) ? {label:'归档候选',disabled:busy,onClick:()=>void changeVisibility(true)} : undefined} primary={{
      label:visibilityUncertain ? '读取归档状态' : operation ? '查询原操作结果' : isArchived ? '恢复候选' : selected.proposal_id ? '查看已保存提案' : confirmed ? '查看当前规则' : selected.assessment==='NEEDS_CHANGES' ? '复制补充请求' : '继续审阅完整变更',
      disabled:busy, loading:busy,
      onClick:()=>{ if(visibilityUncertain) setEpoch(value=>value+1); else if(operation) void recover(); else if(isArchived) void changeVisibility(false); else if(selected.proposal_id) void openProposal(selected).catch(()=>setError('提案暂时无法读取')); else if(confirmed) leave(); else if(selected.assessment==='NEEDS_CHANGES') void supplement(); else void propose() },
    }}/>
  </section>
}
