// 候选选择先留在本地，经完整审阅后原子提交；未知回执只回读，不自动重发。
import { Alert, Button, Checkbox, Input, Popconfirm } from 'antd'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { projectsApi, type ApplicationUnderstandingDto, type CandidateSelection } from '../../api/applications/projects'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { TaskReceipt } from '../../shared/ui/TaskReceipt'
import { AgentAssistEntry } from '../../shared/ui/AgentAssistEntry'

export function CandidateReview({ value, onApplied, onEditingChange, manual, staleReview }: {
  value: ApplicationUnderstandingDto; onApplied: (value: ApplicationUnderstandingDto, confirmed?: boolean) => void
  onEditingChange?: (editing: boolean) => void
  manual: ReactNode; staleReview: ReactNode
}) {
  const [base, setBase] = useState(value)
  const [edits, setEdits] = useState<Record<string, CandidateSelection>>({})
  const [review, setReview] = useState(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [issue, setIssue] = useState<string>()
  const [receipt, setReceipt] = useState<string>()
  const alive = useRef(true), sending = useRef(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const nextButton = useRef<HTMLButtonElement | HTMLAnchorElement>(null)
  const lastReview = useRef(false)
  useEffect(() => {
    if (review) { heading.current?.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }) }
    else if (lastReview.current) { nextButton.current?.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: 'instant' }) }
    lastReview.current = review
  }, [review])
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const dirty = Object.keys(edits).length > 0 || review
  useTaskGuard(dirty || busy || uncertain)
  useEffect(() => { onEditingChange?.(dirty || busy || uncertain); return () => onEditingChange?.(false) }, [dirty, busy, uncertain, onEditingChange])
  useEffect(() => { if (!dirty && !uncertain) setBase(value) }, [value, dirty, uncertain])
  const changed = value.revision !== base.revision
  const candidates = [...base.role_candidates.map(item => ({ ...item, kind: 'ROLE' as const })), ...base.action_candidates.map(item => ({ ...item, kind: 'ACTION' as const }))]
  const choices = candidates.filter(item => !item.stale && item.decision !== 'REVIEW_REQUIRED').map(item => edits[item.candidate_id] ?? {
    kind: item.kind, candidate_id: item.candidate_id, display_name: item.display_name,
    // 新权限组先勾入本次审阅；既有排除决定保留，保存仍须用户核对完整摘要。
    decision: item.decision === 'CONFIRMED' || item.decision === 'REJECTED' ? item.decision : item.kind === 'ACTION' && item.confidence === 'LOW' ? 'PROPOSED' : 'CONFIRMED',
  } as CandidateSelection)
  const changes = choices.filter(item => { const original = candidates.find(candidate => candidate.candidate_id === item.candidate_id)!; return original.decision !== item.decision || original.display_name !== item.display_name.trim() })
  const patch = (item: CandidateSelection, update: Partial<CandidateSelection>) => {
    setEdits(current => ({ ...current, [item.candidate_id]: { ...item, ...update } })); setReceipt(undefined); setReview(false)
  }
  const accepted = (next: ApplicationUnderstandingDto) => {
    setBase(next); setEdits({}); setReview(false); setUncertain(false); setIssue(undefined)
    const roles = next.role_candidates.filter(item=>!item.stale && item.decision==='CONFIRMED').length
    const actions = next.action_candidates.filter(item=>!item.stale && item.decision==='CONFIRMED').length
    const pending = [...next.role_candidates,...next.action_candidates].filter(item=>item.stale || ['PROPOSED','REVIEW_REQUIRED'].includes(item.decision)).length
    setReceipt(`已保存 ${roles} 个角色、${actions} 项业务动作，另有 ${pending} 项待核对。下一步沿用这些信息整理允许与禁止要求；正式权限尚未改变。`); onApplied(next, true)
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
  // 草稿回读与放弃紧邻本步确认；页面级刷新和重新分析仍由父页面承担。
  const editingActions = <>
    {uncertain && <Button loading={busy} onClick={()=>void recover()}>核对保存结果</Button>}
    {(dirty || uncertain || changed) && <Popconfirm title="放弃本次未确认的编辑并读取最新业务信息？" onConfirm={async()=>{ const next=await projectsApi.understanding(base.project_id).catch(()=>null);if (!alive.current)return;if(next){setBase(next);setEdits({});setReview(false);setUncertain(false);setIssue(undefined);onApplied(next)}else setIssue('最新信息读取失败，当前编辑继续保留。') }}><Button disabled={busy}>放弃本次编辑并刷新</Button></Popconfirm>}
  </>
  return <section className="application-step candidate-workspace" aria-label="审阅业务候选">
    <header><h2 ref={heading} tabIndex={-1}>{review ? '保存前，核对这份业务清单' : '哪些识别结果符合你的应用？'}</h2><p className="editorial-muted">{review ? '这次只保存角色与动作。接下来整理谁能操作谁的资源，并由你批准权限规则。' : '勾选并修正名称；不确定的可保留待审。纳入业务清单不等于必须检查，也不代表允许执行。'}</p></header>
    {receipt && <TaskReceipt message={receipt} />}
    {(issue || changed) && <Alert className="flow-feedback" type="warning" showIcon message={issue ?? '应用信息已有更新。当前编辑保留，请读取最新信息后重新审阅。'} />}
    {!review && <><div className="candidate-business-columns">{(['ROLE','ACTION'] as const).map(kind=><section className="candidate-business-group" key={kind}><header><h3>{kind==='ROLE'?'谁在使用应用':'应用里有哪些操作'}</h3><p>{kind==='ROLE'?'角色或权限组，例如负责人、评审。':'业务动作，例如下载文件、查看预览。'}</p></header>
    <div className="candidate-selection-list">{choices.filter(item => item.kind === kind).map(item => {
      const source = candidates.find(candidate => candidate.candidate_id === item.candidate_id)!
      return <section className="candidate-selection-row" data-selected={item.decision === 'CONFIRMED'} key={item.candidate_id}>
        <Checkbox aria-label={`纳入${source.display_name}`} checked={item.decision === 'CONFIRMED'} disabled={busy || uncertain || changed} onChange={event => patch(item,{decision:event.target.checked?'CONFIRMED':'REJECTED'})}/>
        <div><Input aria-label={`${item.kind === 'ROLE' ? '权限组' : '业务动作'}名称：${source.display_name}`} value={item.display_name} maxLength={item.kind === 'ROLE' ? 128 : 256} disabled={busy || uncertain || changed} onChange={event=>patch(item,{display_name:event.target.value})}/>
          <p>{item.decision === 'PROPOSED' ? '暂不决定，继续保留待审' : item.decision === 'REJECTED' ? source.decision === 'REJECTED' ? '已排除的候选' : '将在本次审阅中明确排除' : source.decision === 'CONFIRMED' && source.display_name === item.display_name ? '已确认的业务信息' : '已选入本次审阅，确认后保存'}</p>
          <details><summary>为什么识别出这一项？</summary>{source.origin !== 'MANUAL' && <p className="candidate-source-clue">识别线索：{[...new Set(source.evidence.map(e=>e.symbol).filter(Boolean))].join('、') || source.canonical_key}{source.confidence==='LOW' && ' · 名称仍需核对，可先保留待审'}</p>}{source.evidence.map((e,index)=><p key={index}>{e.relative_path}:{e.line_start}{e.line_end!==e.line_start ? `–${e.line_end}` : ''}{e.symbol ? ` · ${e.symbol}`:''}</p>)}{!source.evidence.length && <p>{source.origin==='MANUAL' ? '由你手工补充。' : '尚无可展示的源码位置，请核对业务含义后决定是否纳入。'}</p>}{source.origin!=='MANUAL'&&<p>这些是识别到的代码线索，不能单独证明允许或禁止要求。</p>}</details>
          {source.origin !== 'MANUAL' && <Button type="link" size="small" disabled={busy || uncertain || changed} onClick={()=>patch(item,{decision:'PROPOSED'})}>保留待审</Button>}
        </div>
      </section>
    })}</div></section>)}</div>
    {staleReview}
    <details className="application-manual-section"><summary>有遗漏？让 Agent 协助查找或手工补充</summary>
      <AgentAssistEntry projectId={base.project_id} contextKey={`source-discovery:${base.revision}`} title="让原 Agent 帮忙核对角色与动作" buttonLabel="Agent 辅助查找" requiredLevel="READ"
        description="在原对话中核对已授权源码，列出遗漏与位置。确认后在下方补充，或由 Agent 随权限候选提交新增业务对象，最后统一审阅。"
        returnTo={window.location.hash.slice(1)||'/access'} onNavigate={path=>{window.location.hash=path}}
        loadContext={async()=>{const latest=await projectsApi.understanding(base.project_id);return {projectId:base.project_id,revisionKey:String(latest.revision),requestText:[
          `请协助核对界鉴项目 ${base.project_id} 的角色（权限组）和业务动作。`,
          '先调用 jiejian_application_understanding 读取当前发现和已确认清单。在你已获授权的源码范围内查找遗漏，给出角色/动作名称、用途、文件位置和判断依据；区分代码事实与业务推测。',
          '不要把每个接口或登录、造数据、恢复步骤自动当成需要检查的权限。不要替我确认业务或扩大源码访问授权。',
          '我会在界鉴补充并确认清单；也可在后续获准整理权限时，通过 jiejian_rule_context 和 jiejian_rule_candidate_save 将新增角色、动作随权限候选提交，最终由我审阅批准。当前只请查找与解释。'
        ].join('\n')}}}/>
      <p className="application-manual-note">手工补充会立即保存；请先确认或放弃上方正在编辑的选择。</p><fieldset className="application-manual-fields" disabled={dirty || busy || uncertain}>{manual}</fieldset></details>
    {(changes.length > 0 || dirty || uncertain || changed) && <div className="candidate-step-footer">{changes.length > 0 && <div><strong>核对本次整理</strong><p>已纳入 {choices.filter(item=>item.kind==='ROLE' && item.decision==='CONFIRMED').length} 个权限组、{choices.filter(item=>item.kind==='ACTION' && item.decision==='CONFIRMED').length} 项业务动作</p></div>}<div className="candidate-step-actions">{editingActions}{changes.length > 0 && <Button ref={nextButton} type="primary" disabled={busy || uncertain || changed || changes.length > 256 || changes.some(item=>!item.display_name.trim())} onClick={()=>setReview(true)}>核对业务总览</Button>}</div></div>}</>}
    {review && <section className="candidate-batch-review" aria-label="本次选择完整摘要"><div className="candidate-review-columns">{(['ROLE','ACTION'] as const).map(kind=><section key={kind}><h3>{kind==='ROLE'?'权限组':'业务动作'}</h3>{(['CONFIRMED','REJECTED','PROPOSED'] as const).map(decision=>{const items=choices.filter(item=>item.kind===kind&&item.decision===decision);return items.length>0 ? <div key={decision}><h4>{decision==='CONFIRMED'?'纳入':decision==='REJECTED'?'排除':'保留待审'} · {items.length}</h4>{items.length ? <ul>{items.map(item=><li key={item.candidate_id}>{item.display_name}</li>)}</ul> : <p className="editorial-muted">无</p>}</div> : null})}</section>)}</div><div className="candidate-step-footer"><Button disabled={busy} onClick={()=>setReview(false)}>返回修改</Button><div className="candidate-step-actions">{editingActions}<Button type="primary" loading={busy} disabled={uncertain || changed} onClick={()=>void submit()}>保存业务信息，继续整理权限</Button></div></div></section>}

  </section>
}
