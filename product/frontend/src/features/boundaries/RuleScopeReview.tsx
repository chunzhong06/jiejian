// 明确要求集中人工确认，歧义逐项澄清；只有服务端保存的有效决定才能进入最终稿。
import {useEffect,useState} from 'react'
import {Button,Input,Radio,Select} from 'antd'
import type {ScopeReview,ScopeChoice,RuleCandidateView} from '../../api/boundaries/ruleCandidates'
import {useTaskGuard} from '../../shared/runtime/editGuard'
import {StatusBadge} from '../../shared/ui/StatusBadge'
import {ScopeBatchReview} from './ScopeBatchReview'
import './rule-scope.css'

const dispositions = {IN_SCOPE:'纳入本轮检查',PREPARATION:'仅用于准备与恢复',OUT_OF_SCOPE:'不属于本轮要求',DEFER:'暂不能确定',SUPPORTING:'作为已有要求的补充依据'}
const timeLabels = {CHECK_WINDOW:'本次检查过程',HISTORY:'包含此前历史',NOT_APPLICABLE:'不涉及时间范围'}
const statusText=(item:ScopeReview)=>item.status==='CONFIRMED'&&item.decision ? dispositions[item.decision.disposition] : item.status==='STALE'?'依据变化，需重核':item.status==='DEFER'?'暂不能确定':'待确认'

function ScopeItem({item,rows,disabled,onSave,onDirtyChange}:{item:ScopeReview;rows:ScopeReview[];disabled:boolean;onSave:(choice:ScopeChoice)=>Promise<boolean>;onDirtyChange:(dirty:boolean)=>void}) {
  const [choice,setChoice]=useState<ScopeChoice['disposition']>()
  const initialRequirement=item.decision?.requirement??item.source.interpretation
  const [requirement,setRequirement]=useState(initialRequirement)
  const [reason,setReason]=useState('')
  const [time,setTime]=useState<ScopeChoice['time_scope']>()
  const [related,setRelated]=useState<string[]>([])
  const dirty=Boolean(choice||reason||time||requirement!==initialRequirement)
  useTaskGuard(dirty)
  useEffect(()=>{onDirtyChange(dirty);return()=>onDirtyChange(false)},[dirty,onDirtyChange])
  const id=item.source.requirement_id
  const missing=[!choice&&'选择本轮用途',!requirement.trim()&&'填写实际要求',!time&&'明确时间范围',!reason.trim()&&'说明判断依据',choice==='SUPPORTING'&&!related.length&&'选择关联的业务要求'].filter(Boolean)
  return <article className="scope-item">
    <header className="scope-item-title"><div><span className="scope-origin">{{USER:'标注为用户原话',SOURCE:'来自源码发现',AGENT:'来自 Agent 建议'}[item.source.origin]}</span><h3>{item.source.title}</h3></div><StatusBadge kind="rule" tone={item.status==='CONFIRMED'?'success':'warning'}>{statusText(item)}</StatusBadge></header>
    <div className="scope-comparison"><div><h4>依据原文</h4><p>{item.source.source_excerpt}</p></div><div><h4>Agent 的解释 · 请核对</h4><p>{item.source.interpretation}</p></div></div>
    {item.decision && <details className="scope-previous"><summary>查看此前保存的决定</summary><p>{item.decision.requirement}</p><p>{item.decision.disposition==='SUPPORTING'?'沿用关联要求的时间范围':timeLabels[item.decision.time_scope]} · {item.decision.reason}</p></details>}
    <div className="scope-editor">
      <label id={`${id}-choice`} className="scope-choice-label">你现在只需确定：这项内容在本轮用于什么？</label>
      <Radio.Group aria-labelledby={`${id}-choice`} value={choice} onChange={e=>{setChoice(e.target.value);setTime(e.target.value==='SUPPORTING'?'NOT_APPLICABLE':undefined);setRelated([])}} disabled={disabled} className="scope-options">{Object.entries(dispositions).map(([value,label])=><Radio key={value} value={value}>{label}</Radio>)}</Radio.Group>
      {!choice ? <p className="editorial-muted">选择用途后，再核对具体要求与时间范围。</p> : <>
        <label htmlFor={`${id}-actual`}>{choice==='SUPPORTING'?'保留的补充说明':'你要保留的实际要求'}</label><Input.TextArea id={`${id}-actual`} value={requirement} onChange={e=>setRequirement(e.target.value)} maxLength={1024} autoSize={{minRows:2,maxRows:5}} disabled={disabled}/>
        {choice==='SUPPORTING'&&<><label htmlFor={`${id}-related`}>这条说明补充了哪些已确认的业务要求？</label><Select id={`${id}-related`} mode="multiple" value={related} onChange={setRelated} disabled={disabled} options={rows.filter(row=>row.status==='CONFIRMED'&&row.decision?.disposition==='IN_SCOPE'&&row.source.requirement_id!==id).map(row=>({value:row.source.requirement_id,label:row.source.title}))}/><p className="editorial-muted">先确认对应业务要求。关联后保留本条原文与判断，沿用对应要求的范围；不独立新增权限，也不取消原要求。</p></>}
        <div className="scope-editor-fields"><div><label htmlFor={`${id}-time`}>需要覆盖的时间</label><Select id={`${id}-time`} placeholder="明确时间范围" value={time} onChange={setTime} disabled={disabled||choice==='SUPPORTING'} options={Object.entries(timeLabels).map(([value,label])=>({value,label:choice==='SUPPORTING'&&value==='NOT_APPLICABLE'?'沿用关联要求的时间范围':label}))}/></div><div><label htmlFor={`${id}-why`}>判断依据</label><Input id={`${id}-why`} placeholder="说明采用、纠正或排除的原因" maxLength={512} value={reason} onChange={e=>setReason(e.target.value)} disabled={disabled}/></div></div>
        <p className="editorial-muted">{choice==='DEFER'?'保存后仍标记为待解决；你可以先核对其他条目，全部明确后才能继续。':'这里只确认检查范围。准备步骤仍须正常授权，正式权限稍后单独审阅批准。'}</p>
      </>}
      <div className="scope-save-row"><p role="status">{missing.length ? `还需：${missing.join('、')}。` : '保存后继续核对下一项；已确认的内容可以回看。'}</p><Button type="primary" disabled={disabled||missing.length>0} onClick={()=>choice&&time&&void onSave({requirement_id:id,requirement_fingerprint:item.fingerprint,disposition:choice,time_scope:time,requirement,reason,...(choice==='SUPPORTING'?{related_requirement_ids:related}:{})})}>{choice==='DEFER'?'保存为待解决':'保存并继续'}</Button></div>
      {dirty&&<Button type="link" disabled={disabled} onClick={()=>{setChoice(undefined);setReason('');setTime(undefined);setRequirement(initialRequirement);setRelated([])}}>撤销未保存编辑</Button>}
    </div>
  </article>
}

export function RuleScopeReview({value,busy,readOnly,onSave,onBatchSave,onContinue,onDirtyChange,continueLabel='继续核对权限规则'}:{value:RuleCandidateView;busy:boolean;readOnly:boolean;onSave:(choice:ScopeChoice)=>Promise<boolean>;onBatchSave?:(choices:ScopeChoice[])=>Promise<boolean>;onContinue?:()=>void;onDirtyChange?:(dirty:boolean)=>void;continueLabel?:string}) {
  const [focused,setFocused]=useState<string>()
  const [dirty,setDirty]=useState(false)
  useEffect(()=>{onDirtyChange?.(dirty);return()=>onDirtyChange?.(false)},[dirty,onDirtyChange])
  const rows=value.scope_review??[]
  if (!rows.length) return null
  const count=rows.filter(item=>item.status==='CONFIRMED').length
  const item=readOnly?undefined:rows.find(row=>row.source.requirement_id===focused)
  const summaries=<div className="scope-summary-list">{rows.map(row=><div className="scope-summary-row" key={row.source.requirement_id}><div><h3>{row.source.title}</h3><p>{row.decision?.requirement??row.source.interpretation}</p><small>{statusText(row)}{row.decision?` · ${row.decision.disposition==='SUPPORTING'?'范围沿用关联要求':timeLabels[row.decision.time_scope]}`:''}</small></div>{!readOnly&&<Button type="link" disabled={busy||dirty} onClick={()=>setFocused(row.source.requirement_id)}>{row.status==='CONFIRMED'?'查看或调整':'核对这一项'}</Button>}{readOnly&&<details><summary>查看依据与决定</summary><p>原文：{row.source.source_excerpt}</p><p>Agent 解释：{row.source.interpretation}</p>{row.decision&&<p>判断依据：{row.decision.reason}</p>}</details>}</div>)}</div>
  return <section className="rule-scope" aria-label="本轮业务范围">
    <header className="scope-heading"><div><p className="scope-eyebrow">当前任务 · 确认本轮查什么</p><h2>{item?`核对第 ${rows.indexOf(item)+1} 项要求`:readOnly?'已保存的范围记录':count<rows.length?'集中核对本轮要求':'本轮范围已确认'}</h2><p>{item?'只有这一项需要单独说明；保存后返回清单，其他有效决定继续保留。':readOnly?'保留当时的原话与决定，实际检查结论请查看检查记录。':count<rows.length?'明确的要求可以一起确认，歧义和补充线索单独处理。来源标记不代表已经得到你的同意。':'下面是你保存的决定。没有未决问题时直接审阅最终稿。'}</p></div><strong>{count} / {rows.length}<small>范围已确认</small></strong></header>
    {item ? <>
      <ScopeItem key={`${item.source.requirement_id}:${item.fingerprint}:${item.decision?.output_revision??0}`} item={item} rows={rows} disabled={busy} onDirtyChange={setDirty} onSave={async choice=>{const saved=await onSave(choice);if(saved){setFocused(undefined);setDirty(false)}return saved}}/>
      {focused&&<Button type="link" disabled={busy||dirty} onClick={()=>setFocused(undefined)}>返回核对清单</Button>}
      <details className="scope-records"><summary>辅助 · 查看全部要求与已保存决定（{rows.length} 项）</summary>{dirty&&<p className="editorial-muted">先保存当前编辑，再切换条目。</p>}{summaries}</details>
    </> : !readOnly&&count<rows.length&&onBatchSave ? <><ScopeBatchReview key={value.candidate.revision} rows={rows} busy={busy} onSave={onBatchSave} onEdit={setFocused} onDirtyChange={setDirty}/>{count>0&&<details className="scope-records"><summary>辅助 · 查看已保存决定（{count} 项）</summary>{summaries}</details>}</> : <>{summaries}{!readOnly&&count===rows.length&&onContinue&&<div className="scope-save-row"><p>范围确认不会批准权限，也不代表检查通过。</p><Button type="primary" disabled={busy} onClick={onContinue}>{continueLabel}</Button></div>}</>}
  </section>
}
