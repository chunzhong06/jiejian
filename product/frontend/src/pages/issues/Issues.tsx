import {IndexSelection} from '../../shared/ui/IndexSelection'
import {useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {ExternalRecheck} from '../../entities/check/ui/ExternalRecheck'
import {workbenchApi} from '../../entities/application/api/workbench'
import {repairsApi,repairLabels} from '../../entities/check/api/repairs'
import {useRead} from '../../shared/lib/useRead'
import {go} from '../../shared/lib/navigation'
import type {PageProps} from '../../shared/model/page'
import {Heading} from '../../shared/ui/layout'
import {Button} from '../../shared/ui/actions'
import {Badge,Empty,ErrorNote,Loading,PageError} from '../../shared/ui/feedback'
import './workspace.css'

export function Issues({projectId,route}:PageProps) {
  const state=useRead('issues:'+projectId,()=>repairsApi.project(projectId))
  const environment=useRead('issue-environment:'+projectId,signal=>workbenchApi.environments(projectId,signal))
  const [rechecking,setRechecking]=useState(false)
  const [showVerified,setShowVerified]=useState(false)
  if(state.loading&&!state.data)return <Loading page/>
  if(!state.data)return <PageError title="问题与证据" error={state.error}/>
  const tasks=state.data.tasks.filter(item=>showVerified||item.status!=='VERIFIED')
  const selected=tasks.find(item=>item.task_reference===route.query.get('issue'))??tasks[0]
  const problem=selected?.comparison?.find(row=>row.role==='DENY')
  return <><Heading title="问题与证据" actions={<Button onClick={()=>go('/reports')}>全部检查记录</Button>}>从已发布的事实跟进权限问题，保留原题、正常对照与每次复验。</Heading>
    <div className="jj-workspace-toolbar"><span className="jj-small jj-muted">{tasks.length} 项问题</span><label className="jj-checkbox"><input type="checkbox" checked={showVerified} onChange={event=>setShowVerified(event.target.checked)}/>包含已验证修复的问题</label></div>
    {tasks.length?<div className="jj-issue-workspace">
      <IndexSelection as="nav" className="jj-issue-index" label="问题列表" identity={selected?.task_reference??""}>{tasks.map(item=>{const row=item.comparison?.find(value=>value.role==='DENY');return <button className="jj-index-item" key={item.task_reference} aria-current={selected?.task_reference===item.task_reference?'true':undefined} onClick={()=>go('/issues?issue='+encodeURIComponent(item.task_reference))}><strong>{row?.action_label??'权限要求未满足'}</strong><span>{row?.subject_label??'操作主体'} · {item.contract.deny.identity.resource_id}</span><small>{item.status==='VERIFIED'&&item.verification?.verification_scope==='EXTERNAL_OBSERVATION'?'原问题本次行为已验证':repairLabels[item.status]}</small></button>})}</IndexSelection>
      {selected&&<article className="jj-issue-reading">
        <header><div><p className="jj-eyebrow">已确认的权限问题</p><h2>{problem?.action_label??'原问题与正常对照'}</h2></div><Badge tone={selected.status==='VERIFIED'?'positive':selected.status==='INCONCLUSIVE'||selected.status==='STALE'?'caution':'negative'}>{selected.status==='VERIFIED'&&selected.verification?.verification_scope==='EXTERNAL_OBSERVATION'?'原问题本次行为已验证':repairLabels[selected.status]}</Badge></header>
        <div className="jj-issue-comparison"><section><h3>原检查范围</h3><p>{problem?.subject_label??'操作主体'} → {problem?.resource_owner_label??'资源所有者'}</p><small>资源 {selected.contract.deny.identity.resource_id}</small></section><section><h3>已确认的业务影响</h3><p>{problem?.effect_labels.join('、')??'请查阅本项问题的发布证据。'}</p><Button kind="quiet" onClick={()=>go('/reports?run_id='+selected.contract.source_run_id+'&case_id='+selected.contract.source_case_id)}>阅读原问题证据<ArrowRightOutlined aria-hidden="true"/></Button></section></div>
        <section className="jj-issue-verification"><h3>原题与正常对照</h3><div className="jj-table-scroll"><table className="jj-object-table"><thead><tr><th>验证对象</th><th>原检查</th><th>再次检查</th></tr></thead><tbody>{selected.comparison?.map(row=><tr key={row.source_case_id}><td><strong>{row.role==='DENY'?'禁止场景':row.role==='SELECTED_ALLOW'?'正常对照':'保留功能'}</strong><small>{row.subject_label??'实际主体'} · {row.effect_labels.join('、')}</small></td><td>{row.before_verdict==='VULNERABLE'?'已确认违规':row.before_verdict==='SAFE'?'符合要求':'证据不足'}</td><td>{row.after_verdict?(row.after_verdict==='SAFE'?'符合要求':row.after_verdict==='VULNERABLE'?'仍存在问题':'证据不足'):'尚无关联结果'}</td></tr>)}</tbody></table></div></section>
        <footer><p>复验保留原检查，依据关联的新事实更新修复状态。</p><div>{selected.change_id&&<Button kind="primary" onClick={()=>go('/reports?view=plan&change_id='+selected.change_id)}>预览关联修改的复验</Button>}{environment.data?.active_environment&&!environment.data.source_available&&<Button kind={selected.change_id?'default':'primary'} onClick={()=>setRechecking(true)}>按原问题再次验证</Button>}<Button kind="quiet" onClick={()=>go('/reports?view=plan')}>检查当前全部要求</Button></div></footer>
      </article>}
    </div>:<Empty title={showVerified?'尚无已确认的问题':'当前没有待处理的问题'} action={<Button onClick={()=>go('/testing')}>打开测试场景</Button>}>证据不足的检查仍需补充依据，未检查的范围不计为通过。</Empty>}
    {rechecking&&selected&&environment.data?.active_environment&&<ExternalRecheck key={selected.task_reference} projectId={projectId} contract={selected.contract} comparison={selected.comparison??[]} endpoint={environment.data.active_environment.target.base_url} onClose={()=>setRechecking(false)}/>}
    {environment.error&&<ErrorNote error={environment.error}/>}
    {state.error&&<ErrorNote error={state.error}/>}</>
}
