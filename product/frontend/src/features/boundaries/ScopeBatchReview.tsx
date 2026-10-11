// 一张清单承接多项明确要求的人工确认；来源标签只用于分组，不作为自动同意依据。
import {useEffect,useState} from 'react'
import {Button,Checkbox,Input,Select} from 'antd'
import type {ScopeChoice,ScopeReview} from '../../api/boundaries/ruleCandidates'
import {useTaskGuard} from '../../shared/runtime/editGuard'

export function ScopeBatchReview({rows,busy,onSave,onEdit,onDirtyChange}:{rows:ScopeReview[];busy:boolean;onSave:(choices:ScopeChoice[])=>Promise<boolean>;onEdit:(id:string)=>void;onDirtyChange:(dirty:boolean)=>void}) {
  const [selected,setSelected]=useState<string[]>([])
  const [time,setTime]=useState<ScopeChoice['time_scope']>()
  const [checked,setChecked]=useState(false)
  const [reason,setReason]=useState('已核对下列原文与解释，按所选时间范围纳入本轮检查。')
  const dirty=selected.length>0||Boolean(time)||checked
  useTaskGuard(dirty)
  useEffect(()=>{onDirtyChange(dirty);return()=>onDirtyChange(false)},[dirty,onDirtyChange])
  const pending=rows.filter(row=>row.status!=='CONFIRMED')
  const business=pending.filter(row=>row.source.origin==='USER')
  const other=pending.filter(row=>row.source.origin!=='USER')
  const chosen=business.filter(row=>selected.includes(row.source.requirement_id))
  return <div className="scope-batch">
    {business.length>0&&<section aria-label="集中核对业务要求"><header className="scope-item-title"><div><h3>这些业务要求是否符合你的本意？</h3><p className="editorial-muted">来源由 Agent 标注，请对照原话。含义一致的可以一起确认，有疑问的单独核对。</p></div><Button type="link" disabled={busy} onClick={()=>{setSelected(selected.length===business.length?[]:business.map(row=>row.source.requirement_id));setChecked(false)}}>{selected.length===business.length?'取消全选':'选中以下全部要求'}</Button></header>
      {business.map(row=><article className="scope-batch-row" key={row.source.requirement_id}><Checkbox aria-label={`选择要求：${row.source.title}`} disabled={busy} checked={selected.includes(row.source.requirement_id)} onChange={e=>{setSelected(ids=>e.target.checked?[...ids,row.source.requirement_id]:ids.filter(id=>id!==row.source.requirement_id));setChecked(false)}}/><div><h3>{row.source.title}</h3><p>{row.source.interpretation}</p><details><summary>对照原话{row.status==='STALE'?' · 依据已变化，需重核':''}</summary><p>{row.source.source_excerpt}</p>{row.decision&&<p>此前保存：{row.decision.requirement}</p>}</details></div><Button type="link" disabled={busy||dirty} onClick={()=>onEdit(row.source.requirement_id)}>单独核对</Button></article>)}
      {chosen.length>0&&<div className="scope-editor"><label htmlFor="scope-batch-time">这 {chosen.length} 项要求覆盖哪个时间范围？</label><Select id="scope-batch-time" value={time} placeholder="请选择，不默认扩大或缩小时间范围" disabled={busy} onChange={v=>{setTime(v);setChecked(false)}} options={[{value:'CHECK_WINDOW',label:'本次检查过程（包含中间发生后又撤回的变化）'},{value:'HISTORY',label:'还需要覆盖此前历史（当前检查仍会阻塞）'},{value:'NOT_APPLICABLE',label:'不涉及时间范围'}]}/><label htmlFor="scope-batch-reason">确认说明</label><Input id="scope-batch-reason" value={reason} maxLength={512} disabled={busy} onChange={e=>{setReason(e.target.value);setChecked(false)}}/><div className="scope-batch-ack"><Checkbox disabled={busy} checked={checked} onChange={e=>setChecked(e.target.checked)}>我已核对选中的 {chosen.length} 项要求，同意按上述含义和时间纳入本轮检查</Checkbox></div><div className="scope-save-row"><p>本次只保存选中项；其余要求继续待定，不批准正式权限。</p><Button type="primary" disabled={busy||!time||!checked||!reason.trim()} onClick={()=>time&&void onSave(chosen.map(row=>({requirement_id:row.source.requirement_id,requirement_fingerprint:row.fingerprint,disposition:'IN_SCOPE',requirement:row.source.interpretation,time_scope:time,reason})))}>确认这 {chosen.length} 项要求</Button></div></div>}
      {dirty&&<Button type="link" disabled={busy} onClick={()=>{setSelected([]);setTime(undefined);setChecked(false)}}>撤销本次选择，再单独核对</Button>}
    </section>}
    {other.length>0&&<section className="scope-other-sources"><h3>补充说明与源码线索 · {other.length} 项待分类</h3><p className="editorial-muted">它们不自动成为业务要求。可以归入准备步骤，或关联到上面的要求作为补充依据；确有独立要求时再纳入。</p>{other.map(row=><div className="scope-summary-row" key={row.source.requirement_id}><div><h3>{row.source.title}</h3><p>{row.source.interpretation}</p><small>{row.source.origin==='SOURCE'?'源码线索':'Agent 建议'}{row.status==='STALE'?' · 依据已变化':''}</small></div><Button type="link" disabled={busy||dirty} onClick={()=>onEdit(row.source.requirement_id)}>核对用途</Button></div>)}</section>}
  </div>
}
