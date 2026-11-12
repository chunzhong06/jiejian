import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import {RepairTask} from '../../entities/check/ui/RepairTask'
import {ruleWorkspaceApi} from '../../entities/permission/api/ruleWorkspace'
import {Tabs} from '../../shared/ui/Tabs'
import '../permissions/styles/rules.css'
import {IndexSelection} from '../../shared/ui/IndexSelection'
import {useEffect,useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {ExternalRecheck} from '../../entities/check/ui/ExternalRecheck'
import {groupRepairComparisons} from '../../entities/check/model/repairComparisons'
import {workbenchApi} from '../../entities/application/api/workbench'
import {repairsApi,repairLabels,type RepairContract} from '../../entities/check/api/repairs'
import {issueDestination} from '../../entities/check/issueDestination'
import {useRead} from '../../shared/lib/useRead'
import {go,returnDestination,returnDestinationLabel,scopedPath} from '../../shared/lib/navigation'
import {assertProject,type PageProps} from '../../shared/model/page'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Badge,ContextNote,Empty,ErrorNote,InlineFeedback,Loading,Notice,PageError} from '../../shared/ui/feedback'
import './workspace.css'
import {IssueHistory} from './IssueHistory'

import {SearchField} from '../../shared/ui/SearchField'
import {readPending,savePending} from '../../shared/lib/operations'

export function Issues({projectId,route,onError,refresh,archive=false}:PageProps&{archive?:boolean}) {
  const fingerprint=route.query.get('repair_reference'),sourceRun=route.query.get('source_run_id'),sourceCase=route.query.get('source_case_id'),requestedId=route.query.get('issue')
  const state=useRead('issues:'+projectId,async()=>{const value=await repairsApi.project(projectId);assertProject(value.project_id,projectId);return value})
  const environment=useRead('issue-environment:'+projectId,async signal=>{const value=await workbenchApi.environments(projectId,signal);assertProject(value.project_id,projectId);return value})
  const repairView=route.query.get('section')==='repair'
  const [rechecking,setRechecking]=useState(false)
  const key='issue-index:'+projectId
  const [query,setQuery]=useState(()=>readPending<string>(key,(value):value is string=>typeof value==='string'&&value.length<=200)??'')
  useEffect(()=>savePending(key,query.slice(0,200)),[key,query])
  const [showVerified,setShowVerified]=useState(false)
  const exact=state.data?.tasks.find(item=>item.contract.repair_fingerprint===fingerprint&&(!sourceRun||item.contract.source_run_id===sourceRun)&&(!sourceCase||item.contract.source_case_id===sourceCase))
  const resolved=useRead(fingerprint&&state.data&&!exact?'issue-origin:'+projectId+':'+fingerprint+':'+sourceRun+':'+sourceCase:null,async()=>{
    const value=await repairsApi.origin(projectId,fingerprint!,sourceRun,sourceCase);assertProject(value.project_id,projectId)
    if(value.task.contract.repair_fingerprint!==fingerprint||sourceRun&&value.task.contract.source_run_id!==sourceRun||sourceCase&&value.task.contract.source_case_id!==sourceCase)throw new Error('原问题引用不一致')
    return value
  })
  const requested=fingerprint?exact??resolved.data?.task:state.data?.tasks.find(item=>item.task_reference===requestedId)
  // 准确对象优先于目录筛选；显式引用失效时不借用另一项问题。
  const includeVerified=showVerified||route.query.get('show_verified')==='1'||requested?.status==='VERIFIED'
  const tasks=state.data?.tasks.filter(item=>includeVerified||item.status!=='VERIFIED')??[]
  const selected=fingerprint||requestedId?requested:tasks[0]
  const historical=Boolean(fingerprint&&!exact&&resolved.data?.historical)
  // 原题处理方式来自当时运行；后来关联源码不把外部行为复验变成源码修复。
  const handling=selected?.handling??(selected?environment.data?.source_available?'SOURCE_CHANGE':'EXTERNAL_OBSERVATION':undefined)
  const canHandle=Boolean(selected)&&selected?.status!=='STALE'&&!archive&&!historical&&!state.error&&!resolved.error&&handling!=='UNAVAILABLE'
  const rules=useRead(repairView&&handling==='SOURCE_CHANGE'&&canHandle?'issue-rules:'+projectId:null,async()=>{const value=await ruleWorkspaceApi.read(projectId);assertProject(value.project_id,projectId);return value})
  useEffect(()=>setRechecking(false),[fingerprint,requestedId])
  if(state.loading&&!state.data||fingerprint&&!exact&&resolved.loading)return <PageSkeleton view="/issues" title="问题与证据"/>
  if(!state.data||fingerprint&&!exact&&resolved.error)return <PageError title="问题与证据" error={resolved.error??state.error}/>
  const origin=returnDestination(route.query.get('return_to'))
  const issuePath=(contract?:RepairContract,section=repairView?'repair':'evidence')=>contract?issueDestination(contract,origin,{section:section==='repair'?'repair':'evidence',change_id:route.query.get('change_id'),run_id:route.query.get('run_id')}):'/issues'
  const catalog=historical&&selected?[selected,...tasks.filter(item=>item.task_reference!==selected.task_reference)]:tasks
  const directoryTasks=catalog.filter(item=>!query.trim()||[item.comparison?.find(row=>row.role==='DENY')?.action_label,item.comparison?.find(row=>row.role==='DENY')?.subject_label,item.contract.deny.identity.resource_id,repairLabels[item.status],item.contract.deny.identity.action_id].some(value=>value?.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())))
  const hidden=Boolean(selected&&!directoryTasks.some(item=>item.task_reference===selected.task_reference))
  const unavailable=archive||historical?<ContextNote label="历史问题记录">{archive?'此应用已归档，可以阅读原问题和历史记录。':'正在查看历史问题记录。后续发现的问题单独记录。'}{historical&&resolved.data?.current_reference&&<ActionLink href={'#'+scopedPath(issueDestination(resolved.data.current_reference,selected?issuePath(selected.contract,'evidence'):origin,{section:archive?'evidence':'repair'}),projectId)}>查看当前原问题</ActionLink>}</ContextNote>:<Notice tone="caution">暂时无法确认原问题的检查条件，请核对原报告。</Notice>
  const problem=selected?.comparison?.find(row=>row.role==='DENY')
  const repairRule=rules.data?.rules.find(rule=>rule.issues.some(item=>item.contract.repair_fingerprint===selected?.contract.repair_fingerprint))
  return <>{origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}<Heading title="问题与证据" actions={tasks.length>0&&<ActionLink navigationScope="page" href={'#'+scopedPath('/reports')}  kind="quiet">全部检查记录</ActionLink>}/>
    {state.data.tasks.length>0&&<div className="jj-workspace-toolbar"><SearchField label="查找当前问题" placeholder="按操作、账号、资源或状态查找" value={query} onValueChange={setQuery}/><span className="jj-small jj-muted">{directoryTasks.length} / {catalog.length} 项已读取问题</span><label className="jj-checkbox"><input type="checkbox" checked={includeVerified} onChange={event=>{setShowVerified(event.target.checked);const query=new URLSearchParams(route.query);query.delete('show_verified');if(event.target.checked)query.set('show_verified','1');else if(selected?.status==='VERIFIED')for(const key of ['issue','repair_reference','source_run_id','source_case_id','change_id','run_id'])query.delete(key);go('/issues?'+query)}}/>包含已验证修复的问题</label></div>}
    {hidden&&<InlineFeedback>当前阅读的问题被筛选隐藏，仍保留原对象。<Button kind="quiet" onClick={()=>setQuery('')}>清除筛选</Button></InlineFeedback>}
    {(requestedId||fingerprint)&&!requested?<Empty title="指定的问题已不在当前问题列表中" action={<ActionLink navigationScope="page" href={'#'+scopedPath('/issues')}  kind="quiet">查看当前问题</ActionLink>}>请从原检查报告核对这项问题，或选择当前仍可查阅的记录。</Empty>:tasks.length?<div className="jj-issue-workspace">
      <IndexSelection as="nav" className="jj-issue-index" label="问题列表" identity={selected?.task_reference??""}>{!directoryTasks.length&&<p className="jj-small jj-muted">当前筛选没有匹配问题。</p>}{directoryTasks.map(item=>{const row=item.comparison?.find(value=>value.role==='DENY');return <button className="jj-index-item" key={item.task_reference} aria-current={selected?.task_reference===item.task_reference?'true':undefined} onClick={()=>{setRechecking(false);go(issuePath(item.contract))}}><span className="jj-object-identity"><strong>{row?.action_label??'权限要求未满足'}</strong><small>{item.status==='VERIFIED'&&item.verification?.verification_scope==='EXTERNAL_OBSERVATION'?'本次行为符合要求':repairLabels[item.status]}</small></span><span className="jj-issue-context">{row?.subject_label??'操作主体'} · {item.contract.deny.identity.resource_id}</span></button>})}</IndexSelection>
      {selected&&<article className="jj-issue-reading">
        <header><p className="jj-eyebrow">已确认的权限问题</p><div className="jj-object-line"><h2>{problem?.action_label??'原问题与正常对照'}</h2><Badge tone={selected.status==='VERIFIED'?'positive':selected.status==='INCONCLUSIVE'||selected.status==='STALE'?'caution':'negative'}>{selected.status==='VERIFIED'&&selected.verification?.verification_scope==='EXTERNAL_OBSERVATION'?'本次行为符合要求':repairLabels[selected.status]}</Badge></div></header>
        <Tabs label="当前问题" value={repairView?'repair':'evidence'} onValueChange={value=>go(issuePath(selected.contract,value))} items={[{value:'evidence',label:'问题与证据'},{value:'repair',label:'处理与复验'}]} panelId="issue-work-panel" idPrefix="issue-work"/>
        <div id="issue-work-panel">{repairView?!canHandle?unavailable:environment.loading?<Loading/>:environment.error?<ErrorNote error={environment.error}/>:handling==='SOURCE_CHANGE'?rules.loading?<Loading/>:rules.error?<ErrorNote error={rules.error}/>:repairRule?<RepairTask key={selected.task_reference} embedded location={issuePath(selected.contract)} rule={repairRule} rules={rules.data!.rules} issue={selected} projectId={projectId} changeId={route.query.get('change_id')??undefined} onError={onError} onReload={()=>{state.reload();rules.reload();refresh()}}/>:<Notice tone="caution">原问题已不在当前规则中，请核对原报告与权限要求，不能用其他问题代替。</Notice>:<section className="jj-panel jj-issue-recheck"><header><h3>修改应用后，按原问题再次验证</h3><p>使用原账号和数据复查这项问题，同时检查正常访问。</p></header><footer className="jj-inline-actions"><Button kind="primary" disabled={!environment.data?.active_environment} onClick={()=>setRechecking(true)}>按原问题再次验证</Button></footer></section>:<>
        <div className="jj-issue-comparison"><section><h3 className="jj-title-caption">原检查范围</h3><p>{problem?.subject_label??'操作主体'} → {problem?.resource_owner_label??'资源所有者'}</p><small>资源 {selected.contract.deny.identity.resource_id}</small></section><section><h3 className="jj-title-caption">已确认的业务影响</h3><p>{problem?.effect_labels.join('、')??'查看原检查中记录的实际结果与判断依据。'}</p><ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id='+selected.contract.source_run_id+'&case_id='+selected.contract.source_case_id+'&return_to='+encodeURIComponent(issuePath(selected.contract)))} kind="quiet">阅读原问题证据<ArrowRightOutlined aria-hidden="true"/></ActionLink></section></div>
        <section className="jj-issue-verification"><h3>原问题与正常访问</h3><div className="jj-scroll-table"><table className="jj-content-table jj-object-table"><thead><tr><th>验证对象</th><th scope="col" className="jj-table-state">原检查</th><th scope="col" className="jj-table-state">再次检查</th></tr></thead><tbody>{groupRepairComparisons(selected.comparison??[]).map(({key,row,roles})=><tr key={key}><td><strong>{row.action_label}</strong><small>{roles.map(role=>role==='DENY'?'禁止场景':role==='SELECTED_ALLOW'?'正常对照':'保留功能').join('、')} · {row.subject_label??'实际主体'} · {row.effect_labels.join('、')}</small></td><td className="jj-table-state">{row.before_verdict==='VULNERABLE'?'不符合规则':row.before_verdict==='SAFE'?'符合规则':'证据不足'}</td><td className="jj-table-state">{row.after_verdict?(row.after_verdict==='SAFE'?'符合规则':row.after_verdict==='VULNERABLE'?'不符合规则':'证据不足'):'尚无关联结果'}</td></tr>)}</tbody></table></div></section>
        <IssueHistory events={selected.history??[]} origin={issuePath(selected.contract)}/>
        <footer><div>
          <ActionLink navigationScope="page" href={'#'+scopedPath(issuePath(selected.contract,'repair'))} kind="primary">处理与复验<ArrowRightOutlined aria-hidden="true"/></ActionLink>
        </div></footer>
        </>}</div>
      </article>}
    </div>:<Empty layout="section" title={includeVerified?'尚无已确认的问题':'当前没有待处理的问题'} action={<ActionLink navigationScope="page" href={'#'+scopedPath('/reports')}  kind="quiet">查看检查记录</ActionLink>}>这里保留已确认问题及其复验记录。每轮检查的完整结果可在“检查记录”中查看。</Empty>}
    {rechecking&&canHandle&&selected&&environment.data?.active_environment&&<ExternalRecheck key={selected.task_reference} projectId={projectId} returnTo={issuePath(selected.contract)} contract={selected.contract} comparison={selected.comparison??[]} endpoint={environment.data.active_environment.target.base_url} onClose={()=>setRechecking(false)}/>}
    {environment.error&&<ErrorNote error={environment.error}/>}
    {state.error&&<ErrorNote error={state.error}/>}</>
}
