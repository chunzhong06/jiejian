// 规则候选按原文和具体情形审阅；未知写回执只查询，陈旧响应不得跨项目覆盖。
import { Alert, Button, Spin } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { ruleCandidatesApi, type RuleCandidateContext, type RuleCandidateView } from '../../api/boundaries/ruleCandidates'
import type { ApiError } from '../../api/http'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { TaskActionBar } from '../../shared/ui/TaskActionBar'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import './rule-candidates.css'

export function RuleCandidatesPanel({ projectId, requestedId, requestedRevision, recoveryOperation, onProposal, onSelected, onRecoveryChange, onExit }: {
  projectId: string; requestedId?: string | null; requestedRevision?: number
  onProposal: (proposalId: string) => Promise<void>
  recoveryOperation?: string | null
  onSelected: (id: string, revision: number) => void
  onExit?: () => void
  onRecoveryChange?: (id: string, revision: number, operation: string | null) => void
}) {
  const [context, setContext] = useState<RuleCandidateContext>()
  const [selected, setSelected] = useState<RuleCandidateView>()
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [operation, setOperation] = useState<string>()
  const [epoch, setEpoch] = useState(0)
  const current = useRef(0)
  const inFlight = useRef(false)
  useTaskGuard(busy || Boolean(operation))

  useEffect(() => {
    const generation = ++current.current
    setLoading(true); setBusy(false); setSelected(undefined); setError(undefined)
    // 仅恢复URL里的有限操作引用；刷新不丢失未知回执，也不保存候选正文到浏览器存储。
    setOperation(recoveryOperation ?? undefined)
    void ruleCandidatesApi.context(projectId).then(async value => {
      const item = requestedId ? await ruleCandidatesApi.show(projectId, requestedId, requestedRevision) : undefined
      if (generation !== current.current) return
      setContext(value); setSelected(item)
    }).catch(() => { if (generation === current.current) setError('规则候选暂时无法读取；已有正式权限没有改变。') })
      .finally(() => { if (generation === current.current) setLoading(false) })
    return () => { current.current += 1 }
  }, [projectId, requestedId, requestedRevision, epoch])

  const select = async (id: string, revision: number) => {
    if (inFlight.current) return
    const generation = ++current.current
    setLoading(true); setError(undefined)
    try {
      const item = await ruleCandidatesApi.show(projectId, id, revision)
      if (generation === current.current) { setSelected(item); onSelected(id, revision) }
    } catch { if (generation === current.current) setError('这条候选无法读取，请重新核对。') }
    finally { if (generation === current.current) setLoading(false) }
  }
  const nextPage = async () => {
    if (context?.next_offset == null || inFlight.current) return
    inFlight.current = true; setBusy(true)
    const generation = current.current
    try { const value = await ruleCandidatesApi.context(projectId, context.next_offset); if (generation === current.current) {setContext(value); setError(undefined)} }
    catch { if (generation === current.current) setError('下一页候选暂时无法读取，当前列表已保留。') }
    finally { inFlight.current = false; if (generation === current.current) setBusy(false) }
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
      const receipt = await ruleCandidatesApi.receipt(projectId, operation)
      if (generation !== current.current) return
      if (receipt.status === 'FOUND' && receipt.candidate) {
        setOperation(undefined); setSelected(receipt.candidate); setError(undefined)
        onRecoveryChange?.(receipt.candidate.candidate.candidate_id, receipt.candidate.candidate.revision, null)
        try { await openProposal(receipt.candidate) } catch { setError('提案已保存，请继续查看已保存提案。') }
      } else setError('原操作尚无确定回执，请稍后继续查询。')
    } catch { if (generation === current.current) setError('回执暂时无法读取，请稍后查询同一操作。') }
    finally { inFlight.current = false; if (generation === current.current) setBusy(false) }
  }

  if (loading) return <section className="rule-candidates" aria-label="读取规则候选"><Spin size="small" /> 正在读取对话中的规则候选</section>
  if (!selected) return <section className="rule-candidates" aria-label="对话规则候选">
    <div className="rule-candidates-heading"><div><h2>对话中的规则</h2><p>在原 Agent 中确认约定后，让它保存到界鉴；正式生效前由你审阅。</p></div><Button onClick={() => setEpoch(value => value + 1)}>读取候选</Button></div>
    {error && <Alert type="warning" message={error} />}
    {!error && context?.candidates.length === 0 && <p className="editorial-muted">尚无待审候选，也可以继续使用下方的人工规则入口。</p>}
    {context?.candidates.map(item => <div className="rule-candidate-row" key={item.candidate_id}><p>{item.original_text}</p><Button type="link" onClick={() => void select(item.candidate_id, item.revision)}>审阅</Button></div>)}
    {context?.next_offset != null && <Button loading={busy} onClick={() => void nextPage()}>下一页候选</Button>}
  </section>

  const content = selected.candidate.content
  const confirmed = selected.assessment === 'ALREADY_CONFIRMED'
  const leave = () => {setSelected(undefined); onExit?.()}
  const permissions = new Map(content.permissions.map(item => [item.item_id, item]))
  return <section className="rule-candidates" aria-label="审阅对话规则">
    <div className="rule-candidates-heading"><h2>{selected.decision ? '查看当时的业务约定' : confirmed ? '沿用已有业务约定' : '确认这条业务约定'}</h2><StatusBadge kind="rule">{confirmed ? '与当前规则一致' : selected.decision?.decision === 'APPROVED' ? '已有批准记录' : selected.decision ? '提案已放弃' : '尚未生效'}</StatusBadge></div>
    <p className="rule-candidate-original">{content.original_text}</p>
    <p className="editorial-muted">{selected.candidate.submitted_via === 'MCP' ? 'Agent 整理' : '本机整理'} · 修订 {selected.candidate.revision}。保存和准备都不代表检查通过。</p>
    <div className="rule-example-table" role="table" aria-label="具体情形与要求">
      {content.examples.map((example, index) => <div className="rule-candidate-row" role="row" key={index}><p role="cell">{example.description}</p><span role="cell">{example.uncovered_reason ?? (permissions.get(example.permission_item_id ?? '')?.expectation === 'DENY' ? '应当拒绝' : permissions.has(example.permission_item_id ?? '') ? '应当允许' : '沿用已确认规则')}</span></div>)}
    </div>
    {!!selected.issues.length && <Alert type="warning" message="以下问题仍需核对" description={<ul>{selected.issues.map((issue, index) => <li key={index}>{issue.message}</li>)}</ul>} />}
    <p className="editorial-muted">{selected.reuse.message}</p>
    {!!selected.reuse.actions?.length && <div aria-label="已有材料与准备缺口">{selected.reuse.actions.map(action => <div className="rule-candidate-row" key={action.item_id}>
      <div><h3>{action.display_name}</h3><p>{action.message}</p><p className="editorial-muted">{action.materials.map(kind=>({EXECUTION:'操作演示',RESOURCE:'测试资源',PROOF:'结果证明',RECOVERY:'恢复材料'}[kind] ?? kind)).join('、') || '还没有可沿用的材料'}</p></div>
      <StatusBadge kind="preparation" tone={action.status === 'MAY_REUSE' ? 'neutral' : 'warning'}>{action.status === 'MAY_REUSE' ? '可能沿用' : action.status === 'NEEDS_REVIEW' ? '需要核对' : '需要准备'}</StatusBadge>
    </div>)}</div>}
    {error && <Alert type="warning" message={error} />}
    <TaskActionBar back={{label:'返回规则列表', disabled:busy || Boolean(operation), onClick:leave}} primary={{
      label:operation ? '查询原操作结果' : selected.proposal_id ? '查看已保存提案' : confirmed ? '查看当前规则' : '继续审阅完整变更',
      disabled:busy || (!operation && !selected.proposal_id && !confirmed && selected.assessment !== 'REVIEWABLE'), loading:busy,
      onClick:()=>{ if(operation) void recover(); else if(selected.proposal_id) void openProposal(selected).catch(()=>setError('提案暂时无法读取')); else if(confirmed) leave(); else void propose() },
    }}/>
  </section>
}
