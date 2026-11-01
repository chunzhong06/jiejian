import {useRef,useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import DownOutlined from '@ant-design/icons/DownOutlined'
import {Dropdown} from 'antd'
import {collaborationApi,collaborationLabels,type CollaborationOperation} from '../../entities/runtime/api/collaboration'
import {useRead} from '../../shared/lib/useRead'
import {go,scopedPath} from '../../shared/lib/navigation'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Heading,Field} from '../../shared/ui/layout'
import {Badge,ErrorNote,Loading,Notice} from '../../shared/ui/feedback'
import {Dialog} from '../../shared/ui/Dialog'
import './collaboration.css'

const ended=(state:string)=>['COMPLETED','CANCELLED'].includes(state)
const jobEnded=(state:string)=>['SUCCEEDED','FAILED','CANCELLED'].includes(state)
const tone=(state:string):'neutral'|'positive'|'negative'|'caution'=>['SUCCEEDED','COMPLETED','PASS'].includes(state)?'positive':['FAILED','BLOCKED','BLOCK'].includes(state)?'negative':['WAITING_USER','UNKNOWN','INCONCLUSIVE'].includes(state)?'caution':'neutral'
const executionLabels:Record<string,string>={PENDING:'等待执行',RUNNING:'正在执行',RETRY_WAIT:'等待重试',CANCELLING:'正在停止并清理',SUCCEEDED:'执行已完成',FAILED:'执行未完成',CANCELLED:'执行已停止'}
const checkLabels:Record<string,string>={PASS:'本次范围符合规则',BLOCK:'发现权限问题',INCONCLUSIVE:'还缺少判断依据'}

const artifactLinks=(operations:CollaborationOperation[],references:Record<string,string>)=>{
  // 当前产物与原问题分开保留；同名旧回执不成为第二条修复导航。
  const links=new Map<string,{label:string;path:string}>()
  if(references.run_id)links.set('source-report',{label:'原问题报告',path:'/reports?run_id='+encodeURIComponent(references.run_id)})
  for(const operation of operations){
    if(operation.state!=='SUCCEEDED'||!operation.result||typeof operation.result!=='object')continue
    const result=operation.result as Record<string,unknown>
    if(operation.capability==='checks.start'&&typeof result.run_id==='string'){
      if(result.run_id===references.run_id)links.delete('source-report')
      links.set('report',{label:'最新检查报告',path:'/reports?run_id='+encodeURIComponent(result.run_id)})
    }
    if(operation.capability==='changes.register'&&typeof result.change_id==='string')links.set('change',{label:'本次修改与复验',path:'/changes?change_id='+encodeURIComponent(result.change_id)})
    if(operation.capability==='rules.save'&&result.candidate&&typeof result.candidate==='object'&&'candidate_id' in result.candidate)links.set('rules',{label:'本次权限要求',path:'/permissions?candidate_id='+encodeURIComponent(String(result.candidate.candidate_id))})
    if(operation.capability==='proofs.save'&&typeof result.source_id==='string')links.set('proof',{label:'结果判断方式',path:'/preparation?source_id='+encodeURIComponent(result.source_id)})
    if(operation.capability==='flows.save'&&typeof result.business_action_id==='string')links.set('flow',{label:'执行与恢复步骤',path:'/preparation?action_id='+encodeURIComponent(result.business_action_id)+'&material_kind=execution'})
  }
  return [...links.values()]
}

export function Collaboration({projectId,taskId}:{projectId:string;taskId:string}){
  const state=useRead('collaboration-task:'+taskId,()=>collaborationApi.show(projectId,taskId),value=>value&&!ended(value.state)&&value.state!=='PAUSED'?2000:0)
  const executor=useRead('collaboration-executor:'+projectId,()=>collaborationApi.executor(projectId))
  const activity=useRead('collaboration-activity:'+taskId+':'+state.data?.revision,()=>collaborationApi.activity(projectId,taskId),value=>value?.some(item=>!jobEnded(item.phase))?2000:0)
  // 请求标识跨网络失败保留；页面 busy 或离开页面均不意味着执行已结束。
  const executionRequest=useRef(crypto.randomUUID().replaceAll('-',''))
  const [launch,setLaunch]=useState(false),[allowChanges,setAllowChanges]=useState(false),[menuOpen,setMenuOpen]=useState(false)
  const menuTrigger=useRef<HTMLButtonElement>(null)
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[copied,setCopied]=useState(false),[answers,setAnswers]=useState<Record<string,string>>({})
  const act=async(work:()=>Promise<unknown>)=>{
    setBusy(true);setError(undefined)
    try{await work();state.reload();window.dispatchEvent(new Event('jiejian:collaboration-changed'))}
    catch(value){setError(value)}finally{setBusy(false)}
  }
  if(state.error)return <ErrorNote error={state.error} onRetry={state.reload}/>
  const task=state.data
  if(!task)return <Loading page/>
  const pending=task.operations.filter(item=>item.state==='WAITING_USER')
  const uncertain=task.operations.filter(item=>['UNKNOWN','RUNNING'].includes(item.state))
  const questions=task.questions.filter(item=>item.answer===null),reviews=task.reviews??[]
  const finished=ended(task.state),stopped=finished||task.state==='PAUSED'
  const activeJobs=activity.data?.filter(item=>!jobEnded(item.phase))??[]
  const completedJobs=activity.data?.filter(item=>jobEnded(item.phase))??[]
  const decisions=pending.length+questions.length+reviews.length+uncertain.length
  const artifacts=artifactLinks(task.operations,task.references),check=task.latest_check
  const readyForAgent=task.state==='WAITING_AGENT'&&!decisions&&!activeJobs.length
  const reportPath=check?'/reports?run_id='+encodeURIComponent(check.run_id):null
  const related=artifacts.filter(item=>item.path!==reportPath)
  const recent=task.operations.slice(-4).reverse()
  const href=(path:string)=>'#'+scopedPath(path,projectId)
  const copy=()=>act(async()=>{
    await navigator.clipboard.writeText(`请继续界鉴协作任务。project_id=${projectId}\ntask_id=${taskId}\n先调用 jiejian_collaboration_context，按需读取 jiejian_collaboration_capability，再通过 jiejian_collaboration_action 处理当前目标。复用现有有效配置；业务不明确时用 jiejian_collaboration_question 提问。需要人的决定时等待同一任务回复。不能批准正式规则、读取秘密或决定检查结论。未知操作只查询原回执，不换键重发。`)
    setCopied(true)
  })
  return <>
    <div className="jj-back-link"><Button kind="quiet" onClick={()=>go('/workspace')}><ArrowLeftOutlined aria-hidden="true"/>应用概览</Button></div>
    <Heading title="协作任务" actions={!finished&&<Dropdown open={menuOpen} onOpenChange={setMenuOpen} trigger={['click']} placement="bottomRight" autoFocus overlayClassName="jj-example-menu" menu={{selectable:false,items:[
      {key:task.state==='PAUSED'?'resume':'pause',label:task.state==='PAUSED'?'继续任务':'暂停任务'},
      ...(!decisions&&!activeJobs.length&&task.execution?.state!=='RUNNING'?[{key:'finish',label:'结束本次协作'}]:[]),
      {type:'divider' as const},{key:'cancel',label:'停止任务',danger:true},
    ],onClick:({key})=>{setMenuOpen(false);menuTrigger.current?.focus({preventScroll:true});void act(()=>collaborationApi.control(projectId,taskId,key))}}}><Button ref={menuTrigger} disabled={busy} aria-haspopup="menu" aria-expanded={menuOpen} className="jj-menu-trigger">任务操作<DownOutlined className="jj-menu-chevron" aria-hidden="true"/></Button></Dropdown>}/>
    {Boolean(error)&&<ErrorNote error={error}/>}
    {launch&&<Dialog title="在界鉴中继续这项任务" onClose={()=>setLaunch(false)} actions={<><Button onClick={()=>setLaunch(false)}>取消</Button><Button kind="primary" busy={busy} onClick={()=>void act(async()=>{await collaborationApi.execute(projectId,taskId,allowChanges,executionRequest.current);executionRequest.current=crypto.randomUUID().replaceAll('-','');setLaunch(false)})}>启动本地 Agent<ArrowRightOutlined aria-hidden="true"/></Button></>}>
      <p>使用本机 Codex 已配置的账号处理当前任务，会使用该账号的模型额度或计费。执行进展和必要决定保留在本任务中。</p>
      {executor.data?.read_only?<p>当前为只读协作，可查看已有规则、任务与结果。</p>:<label className="jj-checkbox"><input type="checkbox" checked={allowChanges} onChange={event=>setAllowChanges(event.target.checked)}/>允许修改当前应用的源码</label>}
      <p className="jj-small jj-muted">应用运行、测试请求和账号登录由界鉴处理。文件读取范围和其他工具沿用本机 Codex 配置，正式权限仍由你批准。</p>
    </Dialog>}
    <div className="jj-collaboration-layout"><section className="jj-collaboration-work" aria-label="当前任务"><section className="jj-collaboration-goal"><header><p className="jj-eyebrow">本次目标</p><Badge tone={tone(task.state)}>{collaborationLabels[task.state]??task.state}</Badge></header><h2>{task.goal}</h2>{!check&&!finished&&<div className="jj-collaboration-dispatch">{task.state==='PAUSED'?<Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.control(projectId,taskId,'resume'))}>继续任务<ArrowRightOutlined aria-hidden="true"/></Button>:readyForAgent&&(executor.data?.available?(executor.data.ready===false?<ActionLink kind="primary" href={href(executor.data.setup_path)}>{executor.data.setup_label}<ArrowRightOutlined aria-hidden="true"/></ActionLink>:<Button kind="primary" busy={busy} onClick={()=>setLaunch(true)}>继续本地 Agent<ArrowRightOutlined aria-hidden="true"/></Button>):<Button kind="primary" busy={busy} onClick={()=>void copy()}>复制任务到开发工具<ArrowRightOutlined aria-hidden="true"/></Button>)}</div>}</section>
    {task.execution&&<Notice tone={task.execution.state==='FAILED'||task.execution.restricted||task.execution.failed_tools?'caution':'neutral'}>{task.execution.message??'正在核对本地 Agent 的执行进展'}</Notice>}

        {decisions>0&&<header><h2>需要你处理</h2><Badge tone="caution">{decisions} 项</Badge></header>}
        {uncertain.map((operation,index)=><section className="jj-collaboration-decision" key={operation.operation_id}><div><h3>{operation.title}</h3><Badge tone="caution">结果待核对</Badge></div><p>保留原操作，先查明是否已执行。</p><footer><Button kind={index===0?'primary':'default'} busy={busy} onClick={()=>void act(()=>collaborationApi.reconcile(projectId,taskId,operation.operation_id))}>核对原操作</Button></footer></section>)}
        {activeJobs.map(item=><div key={item.id} className="jj-collaboration-live"><div><strong>{item.label}</strong><Badge tone={tone(item.phase)}>{executionLabels[item.phase]}</Badge></div><ActionLink href={href(item.destination)}>查看执行进度<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}
        {reviews.map((item,index)=><section className="jj-collaboration-decision" key={item.id}><div><h3>{item.title}</h3><Badge tone="caution">等待审阅</Badge></div><footer><ActionLink kind={!uncertain.length&&index===0?'primary':'default'} href={href(item.destination)}>{item.action_label}<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer></section>)}
        {pending.map((operation,index)=><section className="jj-collaboration-decision" key={operation.operation_id}><div><h3>{operation.title}</h3><Badge tone="caution">等待确认</Badge></div><OperationSummary operation={operation}/><footer><Button disabled={busy||stopped} onClick={()=>void act(()=>collaborationApi.decide(projectId,taskId,operation.operation_id,false))}>暂不执行</Button><Button kind={!uncertain.length&&!reviews.length&&index===0?'primary':'default'} disabled={stopped} busy={busy} onClick={()=>void act(()=>collaborationApi.decide(projectId,taskId,operation.operation_id,true))}>确认并执行<ArrowRightOutlined aria-hidden="true"/></Button></footer></section>)}
        {questions.map(question=><section className="jj-collaboration-decision" key={question.question_id}><h3>{question.question}</h3>{question.options.length?<div className="jj-collaboration-answers">{question.options.map(option=><Button key={option} disabled={stopped} busy={busy} onClick={()=>void act(()=>collaborationApi.answer(projectId,taskId,question.question_id,option))}>{option}</Button>)}</div>:<><Field label="你的业务要求"><textarea rows={3} disabled={stopped} value={answers[question.question_id]??''} onChange={event=>setAnswers({...answers,[question.question_id]:event.target.value})}/></Field><footer><Button kind="primary" disabled={stopped||!answers[question.question_id]?.trim()} busy={busy} onClick={()=>void act(()=>collaborationApi.answer(projectId,taskId,question.question_id,answers[question.question_id]))}>补充并继续</Button></footer></>}</section>)}
        {check&&<section className="jj-collaboration-outcome" data-tone={tone(check.verdict??'')}><div><p className="jj-eyebrow">{check.revalidation?'最近一次原题复验':check.selected_scope?'最近一次选定规则检查':'最近一次检查'}</p><h3>{check.verdict?checkLabels[check.verdict]:check.lifecycle==='FAILED'?'检查未完成':check.lifecycle==='CANCELLED'?'检查已停止':'检查尚未结束'}</h3></div><ActionLink kind={decisions||activeJobs.length?'default':'primary'} href={href(reportPath!)}>{check.revalidation?'查看复验结果':'查看检查报告'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></section>}
        {copied&&<Notice tone="positive">任务已复制，尚未发送；在开发工具中继续这项任务即可。</Notice>}
        {related.length>0&&<details className="jj-collaboration-documents"><summary>本任务资料<span>{related.length} 项</span></summary><nav aria-label="本任务资料">{related.map(({label,path})=><ActionLink key={path} href={href(path)}>{label}<ArrowRightOutlined aria-hidden="true"/></ActionLink>)}</nav></details>}
        {(recent.length>0||completedJobs.length>0||task.events.length>0)&&<section className="jj-collaboration-progress">{(recent.length>0||completedJobs.length>0)&&<h2>处理记录</h2>}{recent.length>0&&<ul className="jj-collaboration-receipts">{recent.map(item=><li key={item.operation_id}><strong>{item.title}</strong><Badge tone={tone(item.state)}>{collaborationLabels[item.state]??item.state}</Badge></li>)}</ul>}
          {completedJobs.length>0&&<details className="jj-collaboration-completed"><summary>后台执行记录<span>{completedJobs.length} 项</span></summary>{completedJobs.map(item=><div key={item.id} className="jj-collaboration-live"><div><strong>{item.label}</strong><Badge tone={tone(item.phase)}>{executionLabels[item.phase]}</Badge></div><ActionLink href={href(item.destination)}>查看执行结果<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}</details>}
          {task.events.length>0&&<details><summary>完整处理过程</summary><ol>{task.events.slice().reverse().map(event=><li key={event.id}><span className="jj-collaboration-event-dot" aria-hidden="true"/><div><strong>{event.title}</strong><small>{event.actor==='USER'?'你的决定':event.actor==='AGENT'?'Agent':'界鉴'}　{new Date(event.at_us/1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</small></div></li>)}</ol></details>}
        </section>}
        {!finished&&<details className="jj-collaboration-methods"><summary>协作方式与连接</summary><div>{readyForAgent&&check&&executor.data?.available&&executor.data.ready!==false&&<Button busy={busy} onClick={()=>setLaunch(true)}>继续本地 Agent<ArrowRightOutlined aria-hidden="true"/></Button>}<Button busy={busy} onClick={()=>void copy()}>复制任务到开发工具</Button><ActionLink href={href('/tools')}>管理开发工具连接<ArrowRightOutlined aria-hidden="true"/></ActionLink></div></details>}
      </section>
    </div>
  </>
}

function OperationSummary({operation}:{operation:CollaborationOperation}){
  const labels:Record<string,string>={entry:'运行入口',port:'本地端口',revision:'当前修订',build_script:'构建步骤',allow_install_scripts:'依赖安装脚本',identity_id:'测试账号',flow_id:'操作流程',source_id:'证明来源',run_id:'检查记录',change_id:'关联修改'}
  const rows=operation.summary?.length?operation.summary.map(item=>[item.label,item.value]):Object.entries(operation.arguments).filter(([key,value])=>key in labels&&value!==null).map(([key,value])=>[labels[key],value])
  return <><dl className="jj-collaboration-summary">{rows.map(([key,value],index)=><div key={index}><dt>{String(key)}</dt><dd>{typeof value==='boolean'?value?'允许':'不执行':String(value)}</dd></div>)}</dl><details><summary>核对本次具体设置</summary><pre>{JSON.stringify(operation.arguments,null,2)}</pre></details></>
}
