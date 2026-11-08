import {RepairTask} from '../../entities/check/ui/RepairTask'
import {ruleWorkspaceApi} from '../../entities/permission/api/ruleWorkspace'
import {Tabs} from '../../shared/ui/Tabs'
import '../permissions/styles/rules.css'
import {IndexSelection} from '../../shared/ui/IndexSelection'
import {useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {ExternalRecheck} from '../../entities/check/ui/ExternalRecheck'
import {workbenchApi} from '../../entities/application/api/workbench'
import {repairsApi,repairLabels} from '../../entities/check/api/repairs'
import {useRead} from '../../shared/lib/useRead'
import {go,returnDestination,returnDestinationLabel,scopedPath} from '../../shared/lib/navigation'
import {assertProject,type PageProps} from '../../shared/model/page'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Badge,Empty,ErrorNote,Loading,Notice,PageError} from '../../shared/ui/feedback'
import './workspace.css'
import {IssueHistory} from './IssueHistory'

export function Issues({projectId,route,onError,refresh}:PageProps) {
  const state=useRead('issues:'+projectId,async()=>{const value=await repairsApi.project(projectId);assertProject(value.project_id,projectId);return value})
  const environment=useRead('issue-environment:'+projectId,async signal=>{const value=await workbenchApi.environments(projectId,signal);assertProject(value.project_id,projectId);return value})
  const repairView=route.query.get('section')==='repair'
  const rules=useRead(repairView&&environment.data?.source_available?'issue-rules:'+projectId:null,async()=>{const value=await ruleWorkspaceApi.read(projectId);assertProject(value.project_id,projectId);return value})
  const [rechecking,setRechecking]=useState(false)
  const [showVerified,setShowVerified]=useState(false)
  if(state.loading&&!state.data)return <Loading page/>
  if(!state.data)return <PageError title="问题与证据" error={state.error}/>
  const requestedId=route.query.get('issue'),requested=state.data.tasks.find(item=>item.task_reference===requestedId)
  // 准确对象优先于目录筛选；显式引用失效时不借用另一项问题。
  const includeVerified=showVerified||route.query.get('show_verified')==='1'||requested?.status==='VERIFIED'
  const tasks=state.data.tasks.filter(item=>includeVerified||item.status!=='VERIFIED')
  const selected=requestedId?requested:tasks[0]
  const origin=returnDestination(route.query.get('return_to'))
  const issuePath=(reference?:string,section=repairView?'repair':'evidence')=>'/issues?'+new URLSearchParams({...(reference?{issue:reference}:{}),...(section==='repair'?{section:'repair'}:{}),...(includeVerified?{show_verified:'1'}:{}),...(origin?{return_to:origin}:{})})
  const problem=selected?.comparison?.find(row=>row.role==='DENY')
  const repairRule=rules.data?.rules.find(rule=>rule.issues.some(item=>item.contract.repair_fingerprint===selected?.contract.repair_fingerprint))
  return <>{origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}<Heading title="问题与证据" actions={tasks.length>0&&<ActionLink navigationScope="page" href={'#'+scopedPath('/reports')}  kind="quiet">全部检查记录</ActionLink>}>跟进已经确认的权限问题。修改应用后，按原问题再次验证，同时确认原来允许的操作仍能完成。每次结果都会保留。</Heading>
    {state.data.tasks.length>0&&<div className="jj-workspace-toolbar"><span className="jj-small jj-muted">{tasks.length} 项问题</span><label className="jj-checkbox"><input type="checkbox" checked={includeVerified} onChange={event=>{setShowVerified(event.target.checked);const query=new URLSearchParams(route.query);query.delete('show_verified');if(event.target.checked)query.set('show_verified','1');else if(selected?.status==='VERIFIED')query.delete('issue');go('/issues?'+query)}}/>包含已验证修复的问题</label></div>}
    {requestedId&&!requested?<Empty title="指定的问题已不在当前问题列表中" action={<ActionLink navigationScope="page" href={'#'+scopedPath('/issues')}  kind="quiet">查看当前问题</ActionLink>}>请从原检查报告核对这项问题，或选择当前仍可查阅的记录。</Empty>:tasks.length?<div className="jj-issue-workspace">
      <IndexSelection as="nav" className="jj-issue-index" label="问题列表" identity={selected?.task_reference??""}>{tasks.map(item=>{const row=item.comparison?.find(value=>value.role==='DENY');return <button className="jj-index-item" key={item.task_reference} aria-current={selected?.task_reference===item.task_reference?'true':undefined} onClick={()=>{setRechecking(false);go(issuePath(item.task_reference))}}><span className="jj-object-identity"><strong>{row?.action_label??'权限要求未满足'}</strong><small>{item.status==='VERIFIED'&&item.verification?.verification_scope==='EXTERNAL_OBSERVATION'?'原问题本次行为已验证':repairLabels[item.status]}</small></span><span className="jj-issue-context">{row?.subject_label??'操作主体'} · {item.contract.deny.identity.resource_id}</span></button>})}</IndexSelection>
      {selected&&<article className="jj-issue-reading">
        <header><p className="jj-eyebrow">已确认的权限问题</p><div className="jj-object-line"><h2>{problem?.action_label??'原问题与正常对照'}</h2><Badge tone={selected.status==='VERIFIED'?'positive':selected.status==='INCONCLUSIVE'||selected.status==='STALE'?'caution':'negative'}>{selected.status==='VERIFIED'&&selected.verification?.verification_scope==='EXTERNAL_OBSERVATION'?'原问题本次行为已验证':repairLabels[selected.status]}</Badge></div></header>
        <Tabs label="当前问题" value={repairView?'repair':'evidence'} onValueChange={value=>go(issuePath(selected.task_reference,value))} items={[{value:'evidence',label:'问题与证据'},{value:'repair',label:'处理与复验'}]} panelId="issue-work-panel" idPrefix="issue-work"/>
        <div id="issue-work-panel">{repairView?environment.loading?<Loading/>:environment.error?<ErrorNote error={environment.error}/>:environment.data?.source_available?rules.loading?<Loading/>:rules.error?<ErrorNote error={rules.error}/>:repairRule?<RepairTask key={selected.task_reference} embedded location={issuePath(selected.task_reference)} rule={repairRule} rules={rules.data!.rules} issue={selected} projectId={projectId} changeId={route.query.get('change_id')??undefined} onError={onError} onReload={()=>{state.reload();rules.reload();refresh()}}/>:<Notice tone="caution">原问题已不在当前规则中，请核对原报告与权限要求，不能用其他问题代替。</Notice>:<section className="jj-panel jj-issue-recheck"><header><h3>修改应用后，按原问题再次验证</h3><p>沿用原问题的账号、数据与正常访问对照，先核对这次应用连接，再明确开始检查。</p></header><footer className="jj-inline-actions"><Button kind="primary" disabled={!environment.data?.active_environment} onClick={()=>setRechecking(true)}>按原问题再次验证</Button></footer></section>:<>
        <div className="jj-issue-comparison"><section><h3 className="jj-title-caption">原检查范围</h3><p>{problem?.subject_label??'操作主体'} → {problem?.resource_owner_label??'资源所有者'}</p><small>资源 {selected.contract.deny.identity.resource_id}</small></section><section><h3 className="jj-title-caption">已确认的业务影响</h3><p>{problem?.effect_labels.join('、')??'查看原检查中记录的实际结果与判断依据。'}</p><ActionLink navigationScope="page" href={'#'+scopedPath('/reports?run_id='+selected.contract.source_run_id+'&case_id='+selected.contract.source_case_id+'&return_to='+encodeURIComponent(issuePath(selected.task_reference)))} kind="quiet">阅读原问题证据<ArrowRightOutlined aria-hidden="true"/></ActionLink></section></div>
        <section className="jj-issue-verification"><h3>原问题与正常访问</h3><div className="jj-table-scroll"><table className="jj-content-table jj-object-table"><thead><tr><th>验证对象</th><th>原检查</th><th>再次检查</th></tr></thead><tbody>{selected.comparison?.map(row=><tr key={row.source_case_id}><td><strong>{row.role==='DENY'?'禁止场景':row.role==='SELECTED_ALLOW'?'正常对照':'保留功能'}</strong><small>{row.subject_label??'实际主体'} · {row.effect_labels.join('、')}</small></td><td>{row.before_verdict==='VULNERABLE'?'不符合规则':row.before_verdict==='SAFE'?'符合规则':'证据不足'}</td><td>{row.after_verdict?(row.after_verdict==='SAFE'?'符合规则':row.after_verdict==='VULNERABLE'?'不符合规则':'证据不足'):'尚无关联结果'}</td></tr>)}</tbody></table></div></section>
        <IssueHistory events={selected.history??[]} origin={issuePath(selected.task_reference)}/>
        <footer><p>每次复验都会保留原检查，并根据新的检查结果更新问题状态。</p><div>
          <ActionLink navigationScope="page" href={'#'+scopedPath(issuePath(selected.task_reference,'repair'))} kind="primary">处理与复验<ArrowRightOutlined aria-hidden="true"/></ActionLink>
        </div></footer>
        </>}</div>
      </article>}
    </div>:<Empty title={includeVerified?'尚无已确认的问题':'当前没有待处理的问题'} action={<ActionLink navigationScope="page" href={'#'+scopedPath('/reports')}  kind="quiet">查看检查记录</ActionLink>}>这里汇总已确认并形成修复要求的权限问题。每轮检查是否通过、证据是否充分，请到检查记录查看；未检查的范围不计为通过。</Empty>}
    {rechecking&&selected&&environment.data?.active_environment&&<ExternalRecheck key={selected.task_reference} projectId={projectId} returnTo={issuePath(selected.task_reference)} contract={selected.contract} comparison={selected.comparison??[]} endpoint={environment.data.active_environment.target.base_url} onClose={()=>setRechecking(false)}/>}
    {environment.error&&<ErrorNote error={environment.error}/>}
    {state.error&&<ErrorNote error={state.error}/>}</>
}
