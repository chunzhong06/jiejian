// 修改记录是界鉴的协作入口；不承载开发聊天和接单流程，只读精确变化、检查与原问题。
import { LoadingState } from '../../shared/ui/LoadingState'
import { Button, Drawer, Empty } from 'antd'
import { useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { WorkPageVisible } from '../../shared/runtime/visibility'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/applications/projects'
import { sourceChangesApi, type SourceChangeViewDto } from '../../api/changes/sourceChanges'
import { developmentApi, type DeliveryDetails, type DevelopmentView } from '../../api/changes/development'
import { repairsApi, repairLabels, type ProjectRepair } from '../../api/checks/repairs'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { StatusBadge, type StatusTone } from '../../shared/ui/StatusBadge'
import { formatTimestamp } from '../../shared/format/time'
import { DeliveryFacts } from './delivery/DeliveryFacts'
import { RepairDelivery } from './repair/RepairDelivery'
import { SourceIdentityPanel } from './delivery/SourceIdentityPanel'
import { ChangeRegistration } from './registration/ChangeRegistration'
import { ChangeRuntimeAction } from './runtime/ChangeRuntimeAction'
import { SourceChangeImpact } from './SourceChangeImpact'
import './styles/delivery.css'
import './changes.css'
import './styles/collaboration.css'
import '../../shared/styles/collections.css'

type DetailTab='changes'|'verification'|'source'
const presetNames: Record<string,string> = { VULNERABLE:'错误交付改动', EXPOSE_REVOKE:'先开放后撤回改动', FIXED:'权限修复', PREVIEW_CHANGED:'公开预览改动' }
const changeReason=(reason:string)=>reason.replace(/预设演示：\s*([A-Z_]+)/,(_all,key)=>`示例改动：${presetNames[key]??key}`)
const sourceLabel=(value:string|undefined)=>value==='LOCAL_GUI'?'本机登记':value||'来源未提供'
const statusText=(details:DeliveryDetails|null|undefined)=>!details?'未关联精确检查':!details.verification.run_id?details.verification.same_source_run_id?'同版源码已检查，未绑定本批':'本批尚未关联检查':details.verification.verdict==='PASS'?details.verification.runtime_status==='MATCHED'?'本轮已验证':'已验证，尚未确认实际运行的代码版本':details.verification.verdict==='BLOCK'?'发现权限问题':details.verification.verdict==='INCONCLUSIVE'?'证据不足':'尚无已发布结论'
function ChangeStatus({details, failed=false}:{details?:DeliveryDetails|null;failed?:boolean}) {
 const tone:StatusTone=failed?'warning':details?.verification.verdict==='BLOCK'?'danger':details?.verification.verdict==='INCONCLUSIVE'?'warning':details?.verification.verdict==='PASS'?(details.verification.runtime_status==='MATCHED'?'success':'warning'):'neutral'
 return <StatusBadge kind={!failed&&details?.verification.verdict?'verdict':'lifecycle'} tone={tone}>{failed?'当前关联读取失败':statusText(details)}</StatusBadge>
}
export function ChangesPage({project,onError,onNavigate,onStateChanged,requestedRepair,requestedChange,requestedView,developmentJourney}:{project:ProjectDto;onError:(error:ApiError)=>void;onNavigate:(path:string)=>void;onStateChanged:()=>unknown;requestedRepair?:string|null;requestedChange?:string|null;requestedView?:string|null;developmentJourney?:ReactNode}){
 const [changes,setChanges]=useState<SourceChangeViewDto[]>([]),[details,setDetails]=useState<Record<string,DeliveryDetails|null>>({})
 const [current,setCurrent]=useState<DevelopmentView|null>(null),[repair,setRepair]=useState<ProjectRepair|null>(null)
 const [selected,setSelected]=useState<string|undefined>(requestedChange??undefined)
 const reference=requestedRepair??undefined
 const [tab,setTab]=useState<DetailTab|null>(requestedView==='acceptance'?'verification':null),[registration,setRegistration]=useState(requestedView==='register'),[journey,setJourney]=useState(false)
 const [historyOpen,setHistoryOpen]=useState(false)
 const [loading,setLoading]=useState(true),[failed,setFailed]=useState(false),[limit,setLimit]=useState(25)
 const [associatedLoading,setAssociatedLoading]=useState(true),[associationFailed,setAssociationFailed]=useState(false)
 const visible=useContext(WorkPageVisible),epoch=useRef(0),requested=useRef(selected),root=useRef<HTMLDivElement>(null),returnId=useRef<string|undefined>(undefined)
 requested.current=selected
 useEffect(()=>{if(!visible){setTab(null);setHistoryOpen(false)}},[visible])
 useEffect(()=>{setSelected(requestedChange??undefined);setTab(requestedView==='acceptance'?'verification':null);setRegistration(requestedView==='register')},[requestedChange,requestedRepair,requestedView])
 const read=async()=>{const stamp=++epoch.current;let listed=false
  setAssociatedLoading(true);setAssociationFailed(false)
  // 主列表先展示；检查与修复关联尚未核对时，不借旧详情放行下一步。
  const list=sourceChangesApi.list(project.project_id,limit).then(async items=>{
   if(items.some(item=>item.manifest.project_id!==project.project_id))throw new ApiError('STATE_PRECONDITION','修改记录所属应用不一致。')
   const wanted=requested.current
   if(wanted&&!items.some(item=>item.manifest.change_id===wanted)){const exact=await sourceChangesApi.show(project.project_id,wanted);if(exact.manifest.change_id!==wanted||exact.manifest.project_id!==project.project_id)throw new ApiError('STATE_PRECONDITION','所选修改关联不一致。');items.push(exact)}
   if(epoch.current===stamp){listed=true;setChanges(items);setLoading(false);setFailed(false)}
   return items
  })
  try{const [listedResult,repairResult,activeResult]=await Promise.allSettled([list,repairsApi.project(project.project_id),developmentApi.current(project.project_id)])
   if(listedResult.status==='rejected')throw listedResult.reason
   if(repairResult.status==='rejected')throw repairResult.reason
   if(activeResult.status==='rejected')throw activeResult.reason
   const items=listedResult.value,repairs=repairResult.value,active=activeResult.value
   if(repairs.project_id!==project.project_id||active&&(active.task.project_id!==project.project_id||active.context.project_id!==project.project_id||active.context.task_id!==active.task.task_id||active.deliveries.some(item=>item.project_id!==project.project_id||item.task_id!==active.task.task_id)))throw new ApiError('STATE_PRECONDITION','修改记录所属应用不一致。')
   const wanted=requested.current??items[0]?.manifest.change_id
   const pairs=await Promise.all(items.filter(item=>item.manifest.change_id===wanted).map(async item=>{const value=await developmentApi.details(project.project_id,item.manifest.change_id)
    if(value&&(value.project_id!==project.project_id||value.delivery.change_id!==item.manifest.change_id||value.context.project_id!==project.project_id||value.context.task_id!==value.delivery.task_id||value.context.context_id!==value.delivery.context_id))throw new ApiError('STATE_PRECONDITION','修改与检查关联不一致。')
    return [item.manifest.change_id,value] as const}))
   if(epoch.current===stamp){setDetails(Object.fromEntries(pairs));setRepair(repairs);setCurrent(active)}
  }catch(error){if(epoch.current===stamp){if(listed)setAssociationFailed(true);else setFailed(true);setDetails({});setRepair(null);setCurrent(null);onError(error as ApiError)};throw error}finally{if(epoch.current===stamp){setLoading(false);setAssociatedLoading(false)}}}

 const live=useLiveRead(visible?`${project.project_id}:${limit}:${selected??''}`:undefined,read,10000)
 useEffect(()=>{setChanges([]);setDetails({});setCurrent(null);setRepair(null);setLoading(true);setFailed(false);return()=>{epoch.current+=1}},[project.project_id])
 useEffect(()=>{if(selected||!returnId.current)return;Array.from(root.current?.querySelectorAll<HTMLElement>('[data-change]')??[]).find(button=>button.dataset.change===returnId.current)?.focus({preventScroll:true})},[selected])
 const refresh=async()=>{setLoading(true);await read()}
 const open=(id:string)=>{returnId.current=id;setSelected(id);setTab(null);setHistoryOpen(false);onNavigate('/changes?change_id='+encodeURIComponent(id))}
 const back=()=>{setSelected(undefined);setRegistration(false);setTab(null);onNavigate('/changes')}
 const latest=changes[0],change=selected?changes.find(item=>item.manifest.change_id===selected):latest,linked=change?details[change.manifest.change_id]:undefined
 const historical=Boolean(selected&&change&&change.manifest.change_id!==latest?.manifest.change_id)
 const issue=reference?repair?.tasks.find(item=>item.contract.repair_fingerprint===reference):undefined
 const currentIssue=change?repair?.tasks.find(item=>item.contract.source_run_id===linked?.verification.run_id&&item.status!=='VERIFIED'):undefined
 const primary=(item:SourceChangeViewDto,detail:DeliveryDetails|null|undefined)=>{
  if(failed)return <Button disabled>无法核对修改状态</Button>
  if(detail?.verification.run_id)return <Button type={item.revalidation.status==='READY'?'primary':'default'} onClick={()=>onNavigate('/history?run_id='+encodeURIComponent(detail.verification.run_id!))}>查看这次检查结果</Button>
  if(historical)return null
  if(item.revalidation.status!=='READY')return null
  if(current?.runtime_state==='NOT_LOADED'&&current.deliveries[0]?.change_id===item.manifest.change_id)return <ChangeRuntimeAction projectId={project.project_id} value={current} onChanged={refresh} onError={onError}/>
  return <Button type="primary" onClick={()=>onNavigate('/tests?materials=1&change_id='+encodeURIComponent(item.manifest.change_id))}>核对本批材料</Button>
 }
 if(issue&&!failed&&!associationFailed&&!associatedLoading)return <RepairDelivery task={issue} change={changes.find(item=>item.manifest.change_id===issue.change_id)} loadingChange={loading} onNavigate={onNavigate} onBack={back} onViewChange={()=>{if(issue.change_id)open(issue.change_id)}}/>
 return <div ref={root} className="source-changes-page"><EditorialPage label="源码改动">
  <div className="change-page-heading"><EditorialHeader eyebrow={project.name || '当前应用'} title={historical&&!registration?'源码改动历史详情':'源码改动'}>{historical&&!registration&&<p className="change-history-context">正在查看已保存的历史批次。权限与变化依据对应登记时的记录；关联检查结论只对应原检查，当前源码可能已经变化。</p>}</EditorialHeader>{!registration&&(historical?<nav className="change-history-navigation" aria-label="修改记录导航"><Button onClick={()=>setHistoryOpen(true)}>返回修改记录</Button><Button onClick={back}>查看最新批次</Button></nav>:<div className="change-page-tools"><Button onClick={()=>setHistoryOpen(true)}>修改记录</Button><Button type={changes.length?'default':'primary'} disabled={failed||loading} onClick={()=>setRegistration(true)}>登记本地修改</Button></div>)}</div>
  {(failed||associationFailed)&&<p role="alert">无法完整读取修改与检查，已有说明不能替代当前结论。<Button onClick={()=>void refresh().catch(()=>{})}>重新读取</Button></p>}
  {loading&&!changes.length&&<LoadingState>正在读取修改记录</LoadingState>}
  {reference&&!issue&&!loading&&!associatedLoading&&!associationFailed&&<p role="alert">未找到指定原问题，当前不会替换为另一条修复要求。</p>}
  {registration?<ChangeRegistration key={project.project_id} projectId={project.project_id} repair={repair} requestedRepair={reference} onError={onError} onCancel={back} onSaved={async id=>{setRegistration(false);open(id);await read();await onStateChanged()}}/>:change&&!failed?<>
    <section className="change-batch" aria-label={change===latest?'最新一批修改':'所选修改批次'}><div>
      <p className="change-batch-meta"><span>{change===latest?'最新一批':'历史批次'}</span><time>{formatTimestamp(change.manifest.created_at_us)}</time><span>{sourceLabel(change.manifest.submitted_by)}</span></p>
      <h2>{changeReason(change.manifest.reason)}</h2>
    </div><div className="change-batch-scope"><p>登记时的权限版本 {change.assessment.payload.policy_epoch}</p><div><span><strong>{change.assessment.payload.action_impacts.length}</strong> 项业务动作</span><span><strong>{change.assessment.payload.permission_refs.length}</strong> 条权限要求</span></div></div><div className="change-batch-actions">{historical&&<span className="change-history-check-label">该历史批次关联检查</span>}{associatedLoading?<StatusBadge kind="lifecycle" tone="neutral">正在核对关联</StatusBadge>:<ChangeStatus details={linked} failed={associationFailed}/>}<div className="change-batch-buttons"><Button onClick={()=>setTab('source')}>查看源码对应</Button><Button onClick={()=>setTab('changes')}>查看文件变化</Button></div></div></section>
    {linked?.verification.same_source_run_id&&!linked.verification.run_id&&<p className="editorial-muted">同一源码和权限版本已有完成记录，但原提交未携带本批标识。<Button type="link" onClick={()=>onNavigate('/history?run_id='+encodeURIComponent(linked.verification.same_source_run_id!))}>查看同版检查</Button></p>}
    <SourceChangeImpact key={project.project_id+':'+change.manifest.change_id} projectId={project.project_id} change={change} historical={historical} onNavigate={onNavigate} onSource={()=>setTab('source')}
      action={associatedLoading||associationFailed?<Button disabled>{associatedLoading?'正在核对检查准备':'关联尚未确认'}</Button>:currentIssue?<Button type={change.revalidation.status==='READY'?'primary':'default'} onClick={()=>{onNavigate('/changes?repair_reference='+encodeURIComponent(currentIssue.contract.repair_fingerprint))}}>查看修复依据</Button>:primary(change,linked)}/>
  </>:selected&&!loading&&!failed?<Empty description="所选修改不可读取，请返回记录重新选择。"/>:!loading&&!failed?<section className="changes-empty" aria-label="尚无修改记录"><h2>从一次源码改动开始</h2><p>在开发工具中完成一批修改后登记，或通过上方入口登记本地修改。</p><p>界鉴会核对实际变化，并显示可能涉及的权限。</p></section>:null}
  {!registration&&!historical&&!!repair?.tasks.filter(item=>!['VERIFIED','STALE'].includes(item.status)).length&&<section className="light-open-issues"><h3>待处理的权限问题</h3>{repair!.tasks.filter(item=>!['VERIFIED','STALE'].includes(item.status)).map(item=><Button type="link" key={item.task_reference} onClick={()=>{onNavigate('/changes?repair_reference='+encodeURIComponent(item.contract.repair_fingerprint))}}>{item.comparison?.find(row=>row.role==='DENY')?.action_label??'原问题'} · {repairLabels[item.status]}</Button>)}</section>}
  {developmentJourney&&!registration&&!historical&&<section className="changes-sample"><div className="changes-sample-heading"><div><h2>官方示例演练</h2><p>跟随示例完成修改、登记与复验。</p></div><Button aria-expanded={journey} onClick={()=>setJourney(value=>!value)}>{journey?'收起官方演练':'继续官方示例演练'}</Button></div>{journey&&developmentJourney}</section>}
  {live.retrying&&<p role="status">修改记录暂未同步，正在重试。</p>}
  <Drawer title="修改记录" open={historyOpen} onClose={()=>setHistoryOpen(false)} width={760}>
    {changes.length?<table className="light-table"><thead><tr><th>修改记录</th><th>关联检查</th><th>查看</th></tr></thead><tbody>{changes.map(item=><tr key={item.manifest.change_id}><td><time>{formatTimestamp(item.manifest.created_at_us)}</time><strong>{item.manifest.reason}</strong><small>{sourceLabel(item.manifest.submitted_by)}</small></td><td data-label="关联检查">{details[item.manifest.change_id]===undefined?<span className="editorial-muted">打开后核对</span>:<ChangeStatus details={details[item.manifest.change_id]} failed={failed||associationFailed}/>}</td><td><Button type="link" data-change={item.manifest.change_id} onClick={()=>open(item.manifest.change_id)}>查看修改</Button></td></tr>)}</tbody></table>:<Empty description="尚无修改记录"/>}
    {changes.length>=limit&&limit<100&&<Button onClick={()=>setLimit(value=>Math.min(100,value+25))}>读取更多修改</Button>}
    {changes.length>=100&&<p className="light-meta">当前展示最近 100 条修改；更早记录可从原检查打开。</p>}
  </Drawer>
  <Drawer title={tab==='source'?'源码对应':tab==='verification'?'本批检查结果':'本批文件变化'} open={tab!==null} onClose={()=>setTab(null)} width={1000}>
    {change&&!failed&&(tab==='source'?<SourceIdentityPanel projectId={project.project_id} recordId={change.manifest.change_id} kind="source-changes"/>:tab&&<DeliveryFacts projectId={project.project_id} change={change} providedDetails={linked} acceptanceOnly={tab==='verification'} changesOnly={tab==='changes'} onNavigate={onNavigate} onError={onError}/>)}
  </Drawer>
 </EditorialPage></div>
}
