// 修改记录是界鉴的协作入口；不承载开发聊天和接单流程，只读精确变化、检查与原问题。
import { Button, Empty, Spin } from 'antd'
import { useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import { useLiveRead } from '../../app/useLiveRead'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { sourceChangesApi, type SourceChangeViewDto } from '../../api/sourceChanges'
import { developmentApi, type DeliveryDetails, type DevelopmentView } from '../../api/development'
import { repairsApi, repairLabels, type ProjectRepair } from '../../api/repairs'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { StatusBadge, type StatusTone } from '../../shared/ui/StatusBadge'
import { formatTimestamp } from '../../app/presentation'
import { DeliveryFacts } from './DeliveryFacts'
import { RepairDelivery } from './RepairDelivery'
import { SourceIdentityPanel } from './SourceIdentityPanel'
import { ChangeRegistration } from './ChangeRegistration'
import { ChangeRuntimeAction } from './ChangeRuntimeAction'
import './delivery.css'
import './changes.css'
import './collaboration.css'
import './lightweight.css'

type DetailTab='changes'|'verification'|'rules'|'source'
const sourceLabel=(value:string|undefined)=>value==='LOCAL_GUI'?'本机登记':value||'来源未提供'
const statusText=(details:DeliveryDetails|null|undefined)=>!details?'未关联精确检查':!details.verification.run_id?'尚未检查':details.verification.verdict==='PASS'?details.verification.runtime_status==='MATCHED'?'本轮已验证':'已验证，运行对应未确认':details.verification.verdict==='BLOCK'?'发现权限问题':details.verification.verdict==='INCONCLUSIVE'?'证据不足':'尚无已发布结论'
function ChangeStatus({details, failed=false}:{details?:DeliveryDetails|null;failed?:boolean}) {
 const tone:StatusTone=failed?'warning':details?.verification.verdict==='BLOCK'?'danger':details?.verification.verdict==='INCONCLUSIVE'?'warning':details?.verification.verdict==='PASS'?(details.verification.runtime_status==='MATCHED'?'success':'warning'):'neutral'
 return <StatusBadge kind={!failed&&details?.verification.verdict?'verdict':'lifecycle'} tone={tone}>{failed?'当前关联读取失败':statusText(details)}</StatusBadge>
}
export function ChangesPage({project,onError,onNavigate,onStateChanged,requestedRepair,requestedChange,requestedView,developmentJourney}:{project:ProjectDto;onError:(error:ApiError)=>void;onNavigate:(path:string)=>void;onStateChanged:()=>unknown;requestedRepair?:string|null;requestedChange?:string|null;requestedView?:string|null;developmentJourney?:ReactNode}){
 const [changes,setChanges]=useState<SourceChangeViewDto[]>([]),[details,setDetails]=useState<Record<string,DeliveryDetails|null>>({})
 const [current,setCurrent]=useState<DevelopmentView|null>(null),[repair,setRepair]=useState<ProjectRepair|null>(null)
 const [selected,setSelected]=useState<string|undefined>(requestedChange??undefined),[reference,setReference]=useState<string|undefined>(requestedRepair??undefined)
 const [tab,setTab]=useState<DetailTab>(requestedView==='acceptance'?'verification':'changes'),[registration,setRegistration]=useState(requestedView==='register'),[journey,setJourney]=useState(false)
 const [loading,setLoading]=useState(true),[failed,setFailed]=useState(false),[limit,setLimit]=useState(25)
 const visible=useContext(WorkPageVisible),epoch=useRef(0),requested=useRef(selected),root=useRef<HTMLDivElement>(null),returnId=useRef<string|undefined>(undefined)
 requested.current=selected
 useEffect(()=>{setSelected(requestedChange??undefined);setReference(requestedRepair??undefined);setTab(requestedView==='acceptance'?'verification':'changes');setRegistration(requestedView==='register')},[requestedChange,requestedRepair,requestedView])
 const read=async()=>{const stamp=++epoch.current
  try{const [items,repairs,active]=await Promise.all([sourceChangesApi.list(project.project_id,limit),repairsApi.project(project.project_id),developmentApi.current(project.project_id)])
   if(items.some(item=>item.manifest.project_id!==project.project_id)||repairs.project_id!==project.project_id||active&&(active.task.project_id!==project.project_id||active.context.project_id!==project.project_id||active.context.task_id!==active.task.task_id||active.deliveries.some(item=>item.project_id!==project.project_id||item.task_id!==active.task.task_id)))throw new ApiError('STATE_PRECONDITION','修改记录所属应用不一致。')
   const wanted=requested.current
   if(wanted&&!items.some(item=>item.manifest.change_id===wanted)){const exact=await sourceChangesApi.show(project.project_id,wanted);if(exact.manifest.change_id!==wanted||exact.manifest.project_id!==project.project_id)throw new ApiError('STATE_PRECONDITION','所选修改关联不一致。');items.push(exact)}
   const pairs=await Promise.all(items.map(async item=>{const value=await developmentApi.details(project.project_id,item.manifest.change_id)
    if(value&&(value.project_id!==project.project_id||value.delivery.change_id!==item.manifest.change_id||value.context.project_id!==project.project_id||value.context.task_id!==value.delivery.task_id||value.context.context_id!==value.delivery.context_id))throw new ApiError('STATE_PRECONDITION','修改与检查关联不一致。')
    return [item.manifest.change_id,value] as const}))
   if(epoch.current===stamp){setChanges(items);setDetails(Object.fromEntries(pairs));setRepair(repairs);setCurrent(active);setFailed(false)}
  }catch(error){if(epoch.current===stamp){setFailed(true);setDetails({});onError(error as ApiError)};throw error}finally{if(epoch.current===stamp)setLoading(false)}}
 const live=useLiveRead(visible?`${project.project_id}:${limit}:${selected??''}`:undefined,read,10000)
 useEffect(()=>()=>{epoch.current+=1},[project.project_id])
 useEffect(()=>{if(selected||!returnId.current)return;Array.from(root.current?.querySelectorAll<HTMLElement>('[data-change]')??[]).find(button=>button.dataset.change===returnId.current)?.focus({preventScroll:true})},[selected])
 const refresh=async()=>{setLoading(true);await read()}
 const open=(id:string)=>{returnId.current=id;setSelected(id);setReference(undefined);setTab('changes');onNavigate('/changes?change_id='+encodeURIComponent(id))}
 const back=()=>{setSelected(undefined);setReference(undefined);setRegistration(false);onNavigate('/changes')}
 const latest=changes[0],change=selected?changes.find(item=>item.manifest.change_id===selected):undefined,linked=selected?details[selected]:latest?details[latest.manifest.change_id]:undefined
 const issue=reference?repair?.tasks.find(item=>item.contract.repair_fingerprint===reference):undefined
 const latestIssue=latest?repair?.tasks.find(item=>item.contract.source_run_id===details[latest.manifest.change_id]?.verification.run_id&&item.status!=='VERIFIED'):undefined
 const primary=(item:SourceChangeViewDto,detail:DeliveryDetails|null|undefined)=>{
  if(failed)return <Button disabled>无法核对修改状态</Button>
  if(detail?.verification.run_id)return <Button type="primary" onClick={()=>onNavigate('/history?run_id='+encodeURIComponent(detail.verification.run_id!))}>查看这次检查结果</Button>
  if(current?.runtime_state==='NOT_LOADED'&&current.deliveries[0]?.change_id===item.manifest.change_id)return <ChangeRuntimeAction projectId={project.project_id} value={current} onChanged={refresh} onError={onError}/>
  return <Button type="primary" onClick={()=>onNavigate('/tests?change_id='+encodeURIComponent(item.manifest.change_id))}>检查这次修改</Button>
 }
 if(issue&&!failed)return <RepairDelivery task={issue} change={changes.find(item=>item.manifest.change_id===issue.change_id)} loadingChange={loading} onNavigate={onNavigate} onBack={back} onViewChange={()=>{if(issue.change_id)open(issue.change_id)}}/>
 return <div ref={root}><EditorialPage label="修改与验证"><div className="light-page-heading"><EditorialHeader eyebrow="协作空间 / 伴随验证" title="修改与验证"><p className="editorial-muted">继续在原客户端开发，在这里核对修改与权限结果。</p></EditorialHeader><Button onClick={()=>onNavigate('/tools')}>Agent 连接与授权</Button></div>
  {failed&&<p role="alert">无法完整读取修改与检查，已有说明不能替代当前结论。<Button onClick={()=>void refresh().catch(()=>{})}>重新读取</Button></p>}
  {loading&&!changes.length&&<Spin aria-label="正在读取修改记录"/>}
  {reference&&!issue&&!loading&&<p role="alert">未找到指定原问题，当前不会替换为另一条修复要求。</p>}
  {registration?<ChangeRegistration key={project.project_id} projectId={project.project_id} repair={repair} requestedRepair={reference} onError={onError} onCancel={back} onSaved={async id=>{setRegistration(false);open(id);await read();await onStateChanged()}}/>:selected?<>
    <Button type="link" className="light-back" onClick={back}>← 返回修改记录</Button>
    {change&&!failed?<article className="light-detail"><header className="light-detail-heading"><div><p className="editorial-eyebrow">本次修改 · {formatTimestamp(change.manifest.created_at_us)}</p><h2>{change.manifest.reason}</h2><p>登记来源：{sourceLabel(change.manifest.submitted_by)}</p></div><ChangeStatus details={linked}/></header>
      <nav className="light-detail-tabs" aria-label="修改详情">{([['changes','修改内容'],['verification','检查结果'],['rules','沿用要求'],['source','源码对应']] as const).map(([key,label])=><button key={key} aria-current={tab===key?'page':undefined} onClick={()=>setTab(key)}>{label}</button>)}</nav>
      <div className="light-detail-body">{tab==='changes'||tab==='verification'?<DeliveryFacts projectId={project.project_id} change={change} providedDetails={linked} acceptanceOnly={tab==='verification'} changesOnly={tab==='changes'} onNavigate={onNavigate} onError={onError}/>:tab==='source'?<SourceIdentityPanel projectId={project.project_id} recordId={change.manifest.change_id} kind="source-changes" onNavigate={onNavigate}/>:<><h3>这次修改沿用的权限</h3><p>保留 {linked?.context.permission_refs.length??change.assessment.payload.action_impacts.flatMap(item=>item.permission_refs).length} 条权限引用；实际检查仍覆盖完整当前计划。</p>{repair?.tasks.filter(item=>item.change_id===change.manifest.change_id).map(item=><Button key={item.task_reference} type="link" onClick={()=>{setReference(item.contract.repair_fingerprint);onNavigate('/changes?repair_reference='+encodeURIComponent(item.contract.repair_fingerprint))}}>查看修复依据 · {repairLabels[item.status]}</Button>)}<Button type="link" onClick={()=>onNavigate('/permissions')}>查看当前权限要求</Button><p className="light-meta">当前权限可能已更新；本次冻结引用与历史结论保持不变。</p></>}
      {tab==='changes'&&<div className="light-actions">{primary(change,linked)}</div>}</div></article>:!loading&&!failed?<Empty description="所选修改不可读取，请返回记录重新选择。"/>:null}
  </>:<>
    {!failed&&latest&&<section className="light-focus"><div><ChangeStatus details={linked}/><h2>{linked?.verification.verdict==='BLOCK'?'这次修改发现了权限问题':linked?.verification.verdict==='PASS'?'本轮结果已发布，后续修改需新的检查':linked?.verification.verdict==='INCONCLUSIVE'?'观察证据不足，先核对缺口':linked?.verification.run_id?'本次检查尚无已发布结论':'这次修改，还没有检查结果'}</h2><p>{latest.manifest.reason} · 登记与验证分别保留，开发继续在原客户端进行。</p></div><div>{latestIssue?<Button type="primary" onClick={()=>{setReference(latestIssue.contract.repair_fingerprint);onNavigate('/changes?repair_reference='+encodeURIComponent(latestIssue.contract.repair_fingerprint))}}>查看修复依据</Button>:primary(latest,linked)}</div><footer><span>{linked?`沿用 ${linked.context.permission_refs.length} 条已确认要求`:'保留原权限与源码记录'}</span><Button type="link" onClick={()=>onNavigate('/permissions')}>查看权限要求</Button></footer></section>}
    <div className="light-section-heading"><div><h2>最近修改</h2><p>每次修改，对应自己的检查</p></div><Button type="link" disabled={failed||loading} onClick={()=>setRegistration(true)}>登记本地修改</Button></div>
    {!!changes.length?<table className="light-table"><thead><tr><th>修改记录</th><th>实际变化</th><th>关联检查</th><th>查看</th></tr></thead><tbody>{changes.map(item=><tr key={item.manifest.change_id}><td><time>{formatTimestamp(item.manifest.created_at_us)}</time><strong>{item.manifest.reason}</strong><small>{sourceLabel(item.manifest.submitted_by)}</small></td><td data-label="实际变化">{item.change_set.status==='NO_BASELINE'?'缺少可比较基线':`${item.change_set.added_paths.length+item.change_set.modified_paths.length+item.change_set.removed_paths.length} 个文件变化`}<small>由源码快照比较</small></td><td data-label="关联检查"><ChangeStatus details={details[item.manifest.change_id]} failed={failed}/></td><td><Button type="link" data-change={item.manifest.change_id} onClick={()=>open(item.manifest.change_id)}>查看修改</Button></td></tr>)}</tbody></table>:!loading&&!failed?<Empty description="尚无修改记录。连接 Agent 后登记，或直接登记本地修改，无需先建开发任务。"/>:null}
    {changes.length>=limit&&limit<100&&<Button onClick={()=>setLimit(value=>Math.min(100,value+25))}>读取更多修改</Button>}
    {changes.length>=100&&<p className="light-meta">当前展示最近 100 条修改；更早记录仍可通过原检查和精确修改引用打开。</p>}
    {!!repair?.tasks.filter(item=>!['VERIFIED','STALE'].includes(item.status)).length&&<section className="light-open-issues"><h3>待处理的权限问题</h3>{repair!.tasks.filter(item=>!['VERIFIED','STALE'].includes(item.status)).map(item=><Button type="link" key={item.task_reference} onClick={()=>{setReference(item.contract.repair_fingerprint);onNavigate('/changes?repair_reference='+encodeURIComponent(item.contract.repair_fingerprint))}}>{item.comparison?.find(row=>row.role==='DENY')?.action_label??'原问题'} · {repairLabels[item.status]}</Button>)}</section>}
    {developmentJourney&&<section className="light-sample-entry"><Button type="link" aria-expanded={journey} onClick={()=>setJourney(value=>!value)}>{journey?'收起官方演练':'继续官方示例演练'}</Button>{journey&&developmentJourney}</section>}
    <p className="light-meta">登记不表示 Agent 正在编码，也不表示修改已通过检查。连接设置只管理工具权限。</p>
  </>}{live.retrying&&<p role="status">修改记录暂未同步，正在重试。</p>}
 </EditorialPage></div>
}
