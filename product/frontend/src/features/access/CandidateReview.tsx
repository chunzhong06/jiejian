// 候选选择先留在本地，经完整审阅后原子提交；未知回执只回读，不自动重发。
import { Alert, Button, Checkbox, Input, Popconfirm, Segmented } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { projectsApi, type ApplicationUnderstandingDto, type CandidateSelection } from '../../api/projects'
import { useTaskGuard, TaskReceipt } from '../../components/TaskContinuity'

export function CandidateReview({ value, onApplied, onEditingChange, manual, staleReview }: {
  value: ApplicationUnderstandingDto; onApplied: (value: ApplicationUnderstandingDto) => void
  onEditingChange?: (editing: boolean) => void
  manual: ReactNode; staleReview: ReactNode
}) {
  const [base, setBase] = useState(value)
  const [edits, setEdits] = useState<Record<string, CandidateSelection>>({})
  const [tab, setTab] = useState('ROLE')
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [issue, setIssue] = useState<string>()
  const [receipt, setReceipt] = useState<string>()
  const alive = useRef(true), sending = useRef(false)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const dirty = Object.keys(edits).length > 0 || review
  useTaskGuard(dirty || busy || uncertain)
  useEffect(() => { onEditingChange?.(dirty || busy || uncertain); return () => onEditingChange?.(false) }, [dirty, busy, uncertain, onEditingChange])
  useEffect(() => { if (!dirty && !uncertain) setBase(value) }, [value, dirty, uncertain])
  const changed = value.revision !== base.revision
  const candidates = [...base.role_candidates.map(item => ({ ...item, kind: 'ROLE' as const })), ...base.action_candidates.map(item => ({ ...item, kind: 'ACTION' as const }))]
  const choices = candidates.filter(item => !item.stale && item.decision !== 'REVIEW_REQUIRED').map(item => edits[item.candidate_id] ?? {
    kind: item.kind, candidate_id: item.candidate_id, display_name: item.display_name,
    decision: item.decision === 'CONFIRMED' || item.decision === 'REJECTED' ? item.decision : item.confidence === 'LOW' ? 'PROPOSED' : 'CONFIRMED',
  } as CandidateSelection)
  const changes = choices.filter(item => { const original = candidates.find(candidate => candidate.candidate_id === item.candidate_id)!; return original.decision !== item.decision || original.display_name !== item.display_name.trim() })
  const patch = (item: CandidateSelection, update: Partial<CandidateSelection>) => {
    setEdits(current => ({ ...current, [item.candidate_id]: { ...item, ...update } })); setReceipt(undefined); setReview(false)
  }
  const accepted = (next: ApplicationUnderstandingDto) => {
    setBase(next); setEdits({}); setReview(false); setUncertain(false); setIssue(undefined)
    setReceipt('本次业务信息已确认，权限规则尚未改变。'); onApplied(next)
  }
  const recover = async () => {
    if (sending.current) return
    sending.current = true; setBusy(true)
    try {
      const next = await projectsApi.understanding(base.project_id)
      if (!alive.current) return
      const actual = [...next.role_candidates, ...next.action_candidates]
      const matches = changes.every(item => actual.some(candidate => candidate.candidate_id === item.candidate_id && !candidate.stale && candidate.decision === item.decision && candidate.display_name === item.display_name.trim()))
      if (matches && next.revision > base.revision) accepted(next)
      else { setIssue(next.revision === base.revision ? '尚未读到本次选择的保存结果。输入仍保留；核对后可放弃本次编辑，重新审阅。' : '应用信息已经变化，本次输入仍保留。请放弃本次编辑后读取最新信息，再重新审阅。'); onApplied(next) }
    } catch { if (alive.current) setIssue('暂时无法核对保存结果。请重试读取，不要重复提交。') }
    finally { sending.current = false; if (alive.current) setBusy(false) }
  }
  const submit = async () => {
    if (sending.current || uncertain || changed || !changes.length) return
    sending.current = true; setBusy(true); setIssue(undefined)
    try {
      const next = await projectsApi.decideCandidates(base.project_id, base.revision, changes.map(item => ({ ...item, display_name: item.display_name.trim() })))
      if (alive.current) accepted(next)
    } catch {
      if (alive.current) { setUncertain(true); setIssue('提交结果需要核对。当前选择已保留，请先读取当前事实。') }
    } finally { sending.current = false; if (alive.current) setBusy(false) }
  }
  return <section className="application-step candidate-workspace" aria-label="审阅业务候选">
    <header><p className="editorial-eyebrow">审阅识别结果</p><h2>先确认应用里有哪些业务</h2><p className="editorial-muted">识别建议只帮助整理业务，不决定谁可以访问。</p></header>
    {receipt && <TaskReceipt message={receipt} />}
    {(issue || changed) && <Alert type="warning" showIcon message={issue ?? '应用信息已有更新。当前编辑保留，请读取最新信息后重新审阅。'} />}
    <Segmented aria-label="候选类别" options={[{label:`权限组 · ${base.role_candidates.length}`,value:'ROLE'}, {label:`业务动作 · ${base.action_candidates.length}`,value:'ACTION'}]} value={tab} onChange={setTab} />
    {choices.filter(item => item.kind === tab).map(item => {
      const source = candidates.find(candidate => candidate.candidate_id === item.candidate_id)!
      return <section className="candidate-selection-row" key={item.candidate_id}>
        <Checkbox aria-label={`纳入${source.display_name}`} checked={item.decision === 'CONFIRMED'} disabled={busy || uncertain || changed} onChange={event => patch(item,{decision:event.target.checked?'CONFIRMED':'REJECTED'})}/>
        <div><Input aria-label={`${item.kind === 'ROLE' ? '权限组' : '业务动作'}名称：${source.display_name}`} value={item.display_name} maxLength={item.kind === 'ROLE' ? 128 : 256} disabled={busy || uncertain || changed} onChange={event=>patch(item,{display_name:event.target.value})}/>
          <p>{item.decision === 'PROPOSED' ? '暂不决定，继续保留待审' : item.decision === 'REJECTED' ? source.decision === 'REJECTED' ? '已排除的候选' : '将在本次审阅中明确排除' : source.decision === 'CONFIRMED' && source.display_name === item.display_name ? '已确认的业务信息' : '建议纳入，尚未提交'}</p>
          <details><summary>查看识别依据</summary>{source.evidence.map((e,index)=><p key={index}>{e.relative_path}:{e.line_start}{e.symbol ? ` · ${e.symbol}`:''}</p>)}{!source.evidence.length && <p>由你手工补充。</p>}</details>
          {source.origin !== 'MANUAL' && <Button type="link" size="small" disabled={busy || uncertain || changed} onClick={()=>patch(item,{decision:'PROPOSED'})}>保留待审</Button>}
        </div>
      </section>
    })}
    {staleReview}
    {!review && <Button type="primary" disabled={busy || uncertain || changed || !changes.length || changes.length > 256 || changes.some(item=>!item.display_name.trim())} onClick={()=>setReview(true)}>审阅本次选择</Button>}
    {review && <section className="candidate-batch-review" aria-label="本次选择完整摘要"><h3>本次确认与排除</h3>{(['CONFIRMED','REJECTED','PROPOSED'] as const).map(decision=><div key={decision}><strong>{decision==='CONFIRMED'?'确认':decision==='REJECTED'?'排除':'保留待审'}</strong><ul>{changes.filter(item=>item.decision===decision).map(item=><li key={item.candidate_id}>{item.display_name}</li>)}</ul></div>)}<p>这里只更新应用业务信息，不会批准或停用任何正式权限规则。</p><Button type="primary" loading={busy} disabled={uncertain || changed} onClick={()=>void submit()}>确认这些业务信息</Button><Button disabled={busy} onClick={()=>setReview(false)}>返回修改</Button></section>}
    {uncertain && <Button loading={busy} onClick={()=>void recover()}>核对保存结果</Button>}
    {(dirty || uncertain || changed) && <Popconfirm title="放弃本次未确认的编辑并读取最新业务信息？" onConfirm={async()=>{ const next=await projectsApi.understanding(base.project_id).catch(()=>null);if (!alive.current)return;if(next){setBase(next);setEdits({});setReview(false);setUncertain(false);setIssue(undefined);onApplied(next)}else setIssue('最新信息读取失败，当前编辑继续保留。') }}><Button disabled={busy}>放弃本次编辑并刷新</Button></Popconfirm>}
    <details className="application-manual-section"><summary>没有找到？手工补充</summary><p>手工补充会立即保存；请先确认或放弃上方正在编辑的选择。</p><fieldset disabled={dirty || busy || uncertain}>{manual}</fieldset></details>
  </section>
}
