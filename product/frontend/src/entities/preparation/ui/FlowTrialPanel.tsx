import {IndexSelection} from '../../../shared/ui/IndexSelection'
import {useEffect,useId,useRef,useState} from 'react'
import {flowTrialsApi as api,type FlowTrial,type TrialPreview,type TrialSelection} from '../api/flowTrials'
import type {OperationFlow} from '../api/operationFlows'
import {ApiError} from '../../../shared/api/http'
import {useRead} from '../../../shared/lib/useRead'
import {operationId,readPending,savePending} from '../../../shared/lib/operations'
import {Button} from '../../../shared/ui/actions'
import {Field} from '../../../shared/ui/layout'
import {Choice} from '../../../shared/ui/Choice'
import {Badge,ErrorNote,Notice} from '../../../shared/ui/feedback'
import {Tabs} from '../../../shared/ui/Tabs'

const active=(item:FlowTrial)=>['PENDING','RUNNING','RETRY_WAIT'].includes(item.state)
const states={PENDING:'等待执行',RUNNING:'正在执行',RETRY_WAIT:'等待处理',SUCCEEDED:'执行已结束',FAILED:'执行中断',CANCELLED:'已取消'}
const classifications={ACCEPTED:'请求被接受',DENIED:'请求被拒绝',UNKNOWN:'结果不明'}
const recoveryLabels={NOT_REQUIRED:'本场景无需恢复',NOT_ATTEMPTED:'尚未执行恢复请求',REQUEST_ACCEPTED:'恢复请求被接受，业务状态仍由正式检查核对',REQUEST_DENIED:'恢复请求被拒绝',UNCONFIRMED:'恢复请求结果不明'}

export function FlowTrialPanel({projectId,flow,accounts,onResume,initialTrialId,onInteractionChange}:{projectId:string;flow:OperationFlow;accounts:Array<{identity_id:string;label:string}>;onResume:(flow:OperationFlow)=>void;initialTrialId?:string;onInteractionChange?:(active:boolean)=>void}){
  const key='jiejian.flow-trial:'+projectId+':'+flow.id
  const [pending,setPending]=useState(()=>readPending<string>(key))
  const [subject,setSubject]=useState(flow.subject_test_identity_id),[owner,setOwner]=useState(flow.resource_owner_test_identity_id),[resource,setResource]=useState(flow.actual_resource_id)
  const [adjusting,setAdjusting]=useState(false),[preview,setPreview]=useState<TrialPreview>(),[restore,setRestore]=useState<FlowTrial>(),[selected,setSelected]=useState<string|undefined>(initialTrialId)
  const [view,setView]=useState(initialTrialId?'history':'current'),panelId=useId(),tabsId=useId()
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),lock=useRef(false)
  const history=useRead('flow-trials:'+projectId,signal=>api.history(projectId,signal),data=>pending||data?.some(active)?1500:0)
  const items=(history.data??[]).filter(item=>item.request.plan.flow.id===flow.id)
  const initialHistory=useRef(false)
  // 首次恢复已有记录；之后的后台刷新不改变使用者正在阅读的页签。
  useEffect(()=>{if(!history.loading&&!initialHistory.current){initialHistory.current=true;if(items.length)setView('history')}},[history.loading,history.data])
  const current=items.find(item=>item.request.trial_id===selected)??items[0]
  const unresolved=Boolean(pending&&!items.some(item=>item.request.operation_id===pending))
  useEffect(()=>{
    const found=items.find(item=>item.request.operation_id===pending)
    if(found){savePending(key,undefined);setPending(undefined);setSelected(found.request.trial_id);setView('history');setPreview(undefined);setRestore(undefined);setError(undefined)}
  },[history.data,pending,key])
  const interacting=Boolean(preview||pending||busy||items.some(active))
  useEffect(()=>{onInteractionChange?.(interacting)},[interacting,onInteractionChange])
  useEffect(()=>()=>onInteractionChange?.(false),[onInteractionChange])
  const act=async(work:()=>Promise<void>)=>{
    if(lock.current)return
    lock.current=true;setBusy(true);setError(undefined)
    try{await work()}catch(error){setError(error)}finally{lock.current=false;setBusy(false)}
  }
  const selection:TrialSelection=restore?{flow_id:flow.id,revision:restore.request.plan.flow.revision,
    subject_identity_id:restore.request.plan.case.subject_test_identity_id,resource_owner_identity_id:restore.request.plan.case.resource_owner_test_identity_id,
    resource_id:restore.request.plan.case.resource_id,restore_trial_id:restore.request.trial_id}:
    {flow_id:flow.id,revision:flow.revision,subject_identity_id:subject,resource_owner_identity_id:owner,resource_id:resource}
  const label=(id:string)=>accounts.find(item=>item.identity_id===id)?.label??'原测试账号'
  return <section className="jj-flow-trial" aria-labelledby="flow-trial-heading">
    <header><div className="jj-flow-trial-heading"><h2 id="flow-trial-heading">试运行场景</h2><Badge>第 {flow.revision} 修订</Badge></div><p>观察实际请求与执行反馈。权限结论由正式检查给出。</p></header>
    {(error||history.error)&&<ErrorNote error={error??history.error}/>}
    {unresolved&&<Notice tone="caution">这次提交的回执尚未明确，正在查询原操作；不会再次发送场景。<Button kind="quiet" onClick={history.reload}>查询原操作</Button></Notice>}
    {!preview&&<Tabs density="compact" label="试运行工作区" value={view} items={[{value:'current',label:'本次试运行'},{value:'history',label:`试运行记录${items.length?' '+items.length:''}`}]} onValueChange={setView} panelId={panelId} idPrefix={tabsId}/>}
    <div id={panelId} role="tabpanel" aria-label={preview?'试运行执行范围':undefined} aria-labelledby={preview?undefined:tabsId+'-'+view} key={preview?'preview':view} className="jj-flow-trial-content">
    {view==='current'&&!preview&&!unresolved&&<div className="jj-flow-trial-selection">
      {!restore&&<ol className="jj-flow-trial-outline" aria-label="保存的执行步骤">{flow.workflow.steps.map((step,index)=><li key={step.id}><span>{index+1}</span><div><header><strong>{step.purpose==='TARGET'?'受检操作':'准备步骤'}</strong><Badge>{step.request_template.method}</Badge></header><code>{step.request_template.path}</code><p>{[step.request_template.query?.length?`${step.request_template.query.length} 项查询参数`:null,step.request_template.headers?.length?`${step.request_template.headers.length} 项请求头`:null,step.request_template.body.kind==='JSON'?'JSON 正文':null].filter(Boolean).join(' · ')||'无附加请求参数'}</p></div></li>)}</ol>}
      {restore?<Notice tone="caution">仅执行原记录的恢复请求，资源为 {restore.request.plan.case.resource_id}。<Button kind="quiet" onClick={()=>setRestore(undefined)}>取消恢复准备</Button></Notice>:adjusting&&<div className="jj-form-grid">
        <Field label="本次操作账号"><Choice disabled={busy} value={subject} onValueChange={setSubject}>{accounts.map(item=><option key={item.identity_id} value={item.identity_id}>{item.label}</option>)}</Choice></Field>
        <Field label="资源所有者账号"><Choice disabled={busy} value={owner} onValueChange={setOwner}>{accounts.map(item=><option key={item.identity_id} value={item.identity_id}>{item.label}</option>)}</Choice></Field>
        <Field label="本次资源编号"><input value={resource} disabled={busy} onChange={event=>setResource(event.target.value)}/></Field>
      </div>}
      {!adjusting&&!restore&&(subject!==flow.subject_test_identity_id||owner!==flow.resource_owner_test_identity_id||resource!==flow.actual_resource_id)&&<p className="jj-small jj-muted">本次选择：{label(subject)} → {label(owner)} · {resource}</p>}
      <div className="jj-inline-actions">{!restore&&<Button kind="quiet" disabled={busy} onClick={()=>setAdjusting(value=>!value)}>{adjusting?'收起本次选择':'更换账号或资源'}</Button>}<Button busy={busy} disabled={!resource||items.some(active)} onClick={()=>void act(async()=>setPreview(await api.preview(projectId,selection)))}>{restore?'预览恢复请求':'预览试运行'}</Button></div>
    </div>}
    {preview&&!unresolved&&<section className="jj-flow-trial-preview" aria-label="试运行执行范围">
      <h3>{preview.plan.mode==='RESTORE'?'仅执行恢复请求':'确认本次执行范围'}</h3>
      <dl className="jj-flow-trial-scope"><div><dt>目标地址</dt><dd>{preview.plan.runtime.target.base_url}</dd></div><div><dt>操作账号</dt><dd>{label(preview.plan.case.subject_test_identity_id)}</dd></div><div><dt>资源</dt><dd>{preview.plan.case.resource_id}<small>所有者：{label(preview.plan.case.resource_owner_test_identity_id)}</small></dd></div><div><dt>请求预算</dt><dd>最多 {preview.plan.runtime.budget.max_requests} 次，{Math.ceil(preview.plan.runtime.budget.max_duration_us/1e6)} 秒</dd></div></dl>
      <ol className="jj-flow-trial-requests">{preview.plan.mode==='TRIAL'&&preview.plan.flow.workflow.steps.map(step=><li key={step.id}><Badge>{step.purpose==='TARGET'?'受检操作':'准备'}</Badge><code>{step.request_template.method} {step.request_template.path}</code></li>)}{preview.plan.state_changing&&preview.plan.flow.recovery&&<li><Badge>恢复</Badge><code>{preview.plan.flow.recovery.method} {preview.plan.flow.recovery.relative_path}</code></li>}</ol>
      <p className="jj-small jj-muted">执行前会核对真实主体。恢复反馈只说明请求结果；本次不会采用场景或改变权限规则。</p>
      <div className="jj-inline-actions"><Button disabled={busy} onClick={()=>setPreview(undefined)}>返回调整</Button><Button kind="primary" busy={busy} disabled={Boolean(pending)} onClick={()=>void act(async()=>{
        const operation=operationId();savePending(key,operation);setPending(operation)
        let result:FlowTrial
        try{result=await api.start(projectId,selection,preview,operation)}catch(error){
          // 明确的输入/前置条件拒绝可重新预览；传输未知时只查询原operation。
          if(error instanceof ApiError&&['INPUT_INVALID','STATE_PRECONDITION','TEST_IDENTITY_NOT_READY','JOB_REQUEST_CONFLICT'].includes(error.code)){
            savePending(key,undefined);setPending(undefined);setPreview(undefined)
          }
          history.reload();throw error
        }
        savePending(key,undefined);setPending(undefined);setSelected(result.request.trial_id);setView('history');setPreview(undefined);setRestore(undefined);history.reload()
      })}>{preview.plan.mode==='RESTORE'?'确认执行恢复请求':'确认执行一次'}</Button></div>
    </section>}
    {!preview&&view==='history'&&(items.length>0?<section className="jj-flow-trial-history"><IndexSelection as="nav" className="jj-flow-trial-records" label="试运行记录" identity={current?.request.trial_id??""}>{items.map(item=><button className="jj-index-item" key={item.request.trial_id} aria-pressed={current===item} onClick={()=>setSelected(item.request.trial_id)}><span>第 {item.request.plan.flow.revision} 修订 · {item.request.plan.mode==='RESTORE'?'恢复':'试运行'}</span><Badge tone={active(item)?'accent':'neutral'}>{states[item.state]}</Badge><time>{new Date(item.request.created_at_us/1000).toLocaleString('zh-CN',{hour12:false})}</time></button>)}</IndexSelection>
      {current&&<div className="jj-flow-trial-result" aria-live="polite"><header><h3>{label(current.request.plan.case.subject_test_identity_id)} · {current.request.plan.case.resource_id}</h3><Badge tone={active(current)?'accent':'neutral'}>{states[current.state]}</Badge></header>
        <details><summary>查看冻结的执行步骤</summary><ol className="jj-flow-trial-requests">{current.request.plan.flow.workflow.steps.map(step=><li key={step.id}><Badge>{step.purpose==='TARGET'?'受检操作':'准备'}</Badge><code>{step.request_template.method} {step.request_template.path}</code></li>)}</ol></details>
        {current.report?<><p className="jj-small jj-muted">主体核验：{{MATCH:'一致',MISMATCH:'不一致',UNKNOWN:'未确认'}[current.report.identity_status]}。{recoveryLabels[current.report.recovery]}</p><div className="jj-flow-trial-step-list">{current.report.steps.map((step,index)=><div key={step.step_id+index}><strong>{step.purpose==='RESTORE'?'恢复请求':`第 ${index+1} 步`}</strong><span>{classifications[step.classification]}</span><span>HTTP {step.status_code??'—'}</span><span>{step.response_bytes??'—'} 字节</span>{step.error_code&&<code>{step.error_code}</code>}</div>)}</div>{current.report.error_code&&<p className="jj-small jj-muted">执行提示：{current.report.error_code}。保留当前记录，调整后请保存新的场景修订。</p>}</>:<p className="jj-small jj-muted">{active(current)?'正在等待本次有限步骤反馈。':current.operation_may_have_run?'执行可能已经发出请求，尚未形成完整反馈。请核对原记录及恢复情况。':'本任务尚未执行场景。'}</p>}
        <div className="jj-flow-trial-result-actions">{active(current)?<Button busy={busy} onClick={()=>void act(async()=>{await api.cancel(projectId,current.request.trial_id);history.reload()})}>取消原任务</Button>:<Button kind="quiet" disabled={busy||unresolved||items.some(active)} onClick={()=>onResume(current.request.plan.flow)}>从此修订继续编辑</Button>}{current.recovery_pending&&!active(current)&&current.request.plan.mode==='TRIAL'&&<Button disabled={busy||unresolved} onClick={()=>{setRestore(current);setView('current');setPreview(undefined)}}>处理恢复请求</Button>}</div>
      </div>}
    </section>:<p className="jj-flow-trial-empty jj-muted">还没有试运行记录。可先预览本次账号、资源和请求，再明确执行。</p>)}
    </div>
  </section>
}
