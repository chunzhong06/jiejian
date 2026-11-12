import {TaskActions} from '../../shared/ui/layout'
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import {markMilestone,useMilestone,useMilestoneTransition} from '../../shared/lib/milestone'
import {proofSourcesApi} from '../../entities/preparation/api/proofSources'
import {assertProject} from '../../shared/model/page'
import {useEffect,useRef,useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import DownOutlined from '@ant-design/icons/DownOutlined'
import QuestionCircleOutlined from '@ant-design/icons/QuestionCircleOutlined'
import FileSearchOutlined from '@ant-design/icons/FileSearchOutlined'
import SafetyOutlined from '@ant-design/icons/SafetyOutlined'
import SyncOutlined from '@ant-design/icons/SyncOutlined'
import {CommandMenu} from '../../shared/ui/CommandMenu'
import {collaborationApi,collaborationLabels,collaborationTone,purposeLabels,type CollaborationOperation,type CollaborationPurpose} from '../../entities/runtime/api/collaboration'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath,returnDestination,withReturnDestination} from '../../shared/lib/navigation'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Heading,Field} from '../../shared/ui/layout'
import {ErrorNote, InlineFeedback,PageError,Notice} from '../../shared/ui/feedback'
import {Dialog} from '../../shared/ui/Dialog'
import {Choice} from '../../shared/ui/Choice'
import {Tabs} from '../../shared/ui/Tabs'
import {IndexSelection} from '../../shared/ui/IndexSelection'
import {ApiError} from '../../shared/api/http'
import type {CollaborationTask} from '../../entities/runtime/api/collaboration'
import './collaboration.css'
import {CollaborationArtifactReview} from './CollaborationArtifactReview'
import {issueDestination} from '../../entities/check/issueDestination'

const ended=(state:string)=>['COMPLETED','CANCELLED'].includes(state)
const jobEnded=(state:string)=>['SUCCEEDED','FAILED','CANCELLED'].includes(state)
const executionLabels:Record<string,string>={PENDING:'等待执行',RUNNING:'正在执行',RETRY_WAIT:'等待重试',CANCELLING:'正在停止并清理',SUCCEEDED:'执行已完成',FAILED:'执行未完成',CANCELLED:'执行已停止'}
const checkLabels:Record<string,string>={PASS:'本次范围符合规则',BLOCK:'发现权限问题',INCONCLUSIVE:'还缺少判断依据'}
type WorkItem=
  |{id:string;kind:'question';label:string;title:string;data:CollaborationTask['questions'][number]}
  |{id:string;kind:'review';label:string;title:string;data:NonNullable<CollaborationTask['reviews']>[number]}
  |{id:string;kind:'pending'|'uncertain';label:string;title:string;data:CollaborationOperation}
const workIcons={question:QuestionCircleOutlined,review:FileSearchOutlined,pending:SafetyOutlined,uncertain:SyncOutlined}

const artifactLinks=(operations:CollaborationOperation[],references:Record<string,string>)=>{
  // 当前产物与原问题分开保留；同名旧回执不成为第二条修复导航。
  const links=new Map<string,{label:string;path:string}>()
  if(references.run_id)links.set('source-report',{label:'原问题报告',path:'/reports?'+new URLSearchParams({run_id:references.run_id,...(references.case_id?{case_id:references.case_id}:{})})})
  // 协作完成或工单回执只是交付事实；继续处理仍回到最初交接的准确原题。
  try{
    const originals:unknown=JSON.parse(references.repair_references??'[]')
    if(Array.isArray(originals))for(const [index,item] of originals.slice(0,128).entries()){
      if(item&&typeof item==='object'&&typeof item.repair_fingerprint==='string'&&/^[0-9a-f]{64}$/.test(item.repair_fingerprint)&&typeof item.source_run_id==='string'&&typeof item.source_case_id==='string')
        links.set('repair:'+item.repair_fingerprint,{label:originals.length===1?'继续处理原问题':'原问题 '+(index+1),path:issueDestination(item,undefined,{section:'repair'})})
    }
  }catch{/* 缺失或旧格式交接仍可从原报告核对，不选择最近的问题。 */}
  for(const operation of operations){
    if(operation.state!=='SUCCEEDED'||!operation.result||typeof operation.result!=='object')continue
    const result=operation.result as Record<string,unknown>
    if(operation.capability==='checks.start'&&typeof result.run_id==='string'){
      if(result.run_id===references.run_id)links.delete('source-report')
      links.set('report',{label:'最新检查报告',path:'/reports?run_id='+encodeURIComponent(result.run_id)})
    }
    if(operation.capability==='changes.register'&&typeof result.change_id==='string')links.set('change',{label:'本次修改与复验',path:'/changes?change_id='+encodeURIComponent(result.change_id)})
    if(operation.capability==='rules.save'&&result.candidate&&typeof result.candidate==='object'&&'candidate_id' in result.candidate)links.set('rules',{label:'本次权限要求',path:'/permissions?candidate_id='+encodeURIComponent(String(result.candidate.candidate_id))})
    if(operation.capability==='proofs.save'&&typeof result.source_id==='string')links.set('proof',{label:'结果判断方式',path:'/preparation?proof_sources=1&source_id='+encodeURIComponent(result.source_id)+'&revision='+String(result.revision)})
    if(operation.capability==='flows.save'&&typeof result.id==='string'&&typeof result.revision==='number'&&typeof result.business_action_id==='string')links.set('flow:'+result.id,{label:'流程候选 · 第 '+result.revision+' 修订',path:'/testing?action_id='+encodeURIComponent(result.business_action_id)+'&flow_id='+encodeURIComponent(result.id)+'&revision='+result.revision+'&review=1'})
    if(operation.capability.startsWith('identities.')&&typeof result.identity_id==='string')links.set('identity:'+result.identity_id,{label:'测试账号',path:'/preparation?identities=1&identity_id='+encodeURIComponent(result.identity_id)})
    if(operation.capability==='materials.select_data')links.set('resources',{label:'本次测试数据',path:'/preparation?focus=resource'})
    if(operation.capability.startsWith('environments.')&&typeof result.environment_id==='string')links.set('environment:'+result.environment_id,{label:'运行环境',path:'/application?view=environment&environment_id='+encodeURIComponent(result.environment_id)})
    if(operation.capability==='sources.accept'&&typeof result.source_id==='string')links.set('source:'+result.source_id,{label:'接口来源',path:'/application?view=sources&source_id='+encodeURIComponent(result.source_id)})
  }
  return [...links.values()]
}

export function Collaboration({projectId,taskId}:{projectId:string;taskId:string}){
  const state=useRead('collaboration-task:'+taskId,()=>collaborationApi.show(projectId,taskId),value=>value&&!ended(value.state)&&value.state!=='PAUSED'?2000:0)
  const executor=useRead('collaboration-executor:'+projectId,()=>collaborationApi.executor(projectId))
  const activity=useRead('collaboration-activity:'+taskId+':'+state.data?.revision,()=>collaborationApi.activity(projectId,taskId),value=>value?.some(item=>!jobEnded(item.phase))?2000:0)
  // 请求标识跨网络失败保留；页面 busy 或离开页面均不意味着执行已结束。
  const executionRequest=useRef(crypto.randomUUID().replaceAll('-',''))
  const [launch,setLaunch]=useState(false),[allowChanges,setAllowChanges]=useState(false)
  const [continuous,setContinuous]=useState(true)
  const [view,setView]=useState('work'),[selectedId,setSelectedId]=useState<string>()
  const [supplement,setSupplement]=useState(false),[goal,setGoal]=useState(''),[purpose,setPurpose]=useState<CollaborationPurpose>('CHECK')
  const followupRequest=useRef(crypto.randomUUID().replaceAll('-',''))
  const followupPayload=useRef<Pick<CollaborationTask,'goal'|'purpose'|'references'|'editor'>|undefined>(undefined)
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[copied,setCopied]=useState(false),[answers,setAnswers]=useState<Record<string,string>>({})
  const [answered,setAnswered]=useState<string>()
  useEffect(()=>setAnswered(undefined),[projectId,taskId])
  const answerCompletion=useMilestone<HTMLDivElement>('answer:'+projectId+':'+taskId+':'+answered,Boolean(answered),'collaboration')
  useEffect(()=>{if(!copied)return;const timer=setTimeout(()=>setCopied(false),2200);return()=>clearTimeout(timer)},[copied])
  const act=async(work:()=>Promise<unknown>)=>{
    setBusy(true);setError(undefined)
    try{await work();state.reload();window.dispatchEvent(new Event('jiejian:collaboration-changed'))}
    catch(value){setError(value)}finally{setBusy(false)}
  }
  const completion=useMilestoneTransition<HTMLDivElement>('collaboration:'+projectId+':'+taskId,state.data?state.data.state==='COMPLETED'||Boolean(state.data.reviews?.length):undefined,'collaboration')
  if(state.error&&!state.data)return <PageError title="Agent 协作" error={state.error}/>;
  const task=state.data
  if(!task)return <PageSkeleton view="/workspace" title="Agent 协作"/>
  const submitFollowup=()=>act(async()=>{
    const input=followupPayload.current??{goal:goal.trim(),purpose,references:task.references,editor:task.editor};followupPayload.current=input
    try{await collaborationApi.followup(projectId,taskId,input.goal,input.purpose,input.references,followupRequest.current,input.editor);followupPayload.current=undefined;followupRequest.current=crypto.randomUUID().replaceAll('-','');setSupplement(false)}
    catch(value){if(value instanceof ApiError&&['INPUT_INVALID','STATE_PRECONDITION','MCP_PERMISSION_REQUIRED','RECORD_NOT_FOUND'].includes(value.code))followupPayload.current=undefined;throw value}
  })
  const pending=task.operations.filter(item=>item.state==='WAITING_USER')
  const uncertain=task.operations.filter(item=>['UNKNOWN','RUNNING'].includes(item.state))
  const questions=task.questions.filter(item=>item.answer===null),reviews=task.reviews??[]
  const finished=ended(task.state),stopped=finished||task.state==='PAUSED'
  const activeJobs=activity.data?.filter(item=>!jobEnded(item.phase))??[]
  const completedJobs=activity.data?.filter(item=>jobEnded(item.phase))??[]
  const decisions=pending.length+questions.length+reviews.length+uncertain.length
  // 先核对未知副作用，再补充业务含义；用户可自由切换，选择本身不执行操作。
  const items:WorkItem[]=[
    ...uncertain.map(data=>({id:'uncertain:'+data.operation_id,kind:'uncertain' as const,label:'核对原操作',title:data.title,data})),
    ...questions.map(data=>({id:'question:'+data.question_id,kind:'question' as const,label:'补充说明',title:data.question,data})),
    ...pending.map(data=>({id:'pending:'+data.operation_id,kind:'pending' as const,label:'确认执行',title:data.title,data})),
    ...reviews.map(data=>({id:'review:'+data.id,kind:'review' as const,label:'审阅产物',title:data.title,data})),
  ]
  const selected=items.find(item=>item.id===selectedId)??items[0]
  const resumeForDecision=selected&&['question','pending'].includes(selected.kind)
  const focusQuestion=view==='work'&&items.length===1&&selected?.kind==='question'
  const artifacts=artifactLinks(task.operations,task.references).filter(item=>!reviews.some(review=>review.destination===item.path)),check=task.latest_check
  const continuing=task.execution?.continuous&&['RUNNING','WAITING'].includes(task.execution.state)&&!stopped
  const readyForAgent=!continuing&&['WAITING_AGENT','BLOCKED'].includes(task.state)&&!decisions&&!activeJobs.length
  const reportPath=check?'/reports?run_id='+encodeURIComponent(check.run_id):null
  const recent=task.operations.slice(-4).reverse()
  const visibleEvents=task.events.filter(event=>event.title!=='已建立协作任务'&&!task.operations.some(operation=>event.title===operation.title||event.title.startsWith(operation.title+'：'))&&!questions.some(question=>event.title===question.question))
  const taskPath='/workspace?'+new URLSearchParams({view:'collaboration',task_id:taskId})
  const href=(path:string)=>'#'+scopedPath(withReturnDestination(path,taskPath),projectId)
  const copy=()=>act(async()=>{
    await navigator.clipboard.writeText(`请继续界鉴协作任务。project_id=${projectId}\ntask_id=${taskId}\n先调用 jiejian_collaboration_context，按需读取 jiejian_collaboration_capability，再通过 jiejian_collaboration_action 处理当前目标。复用现有有效配置；业务不明确时用 jiejian_collaboration_question 提问。需要人的决定时等待同一任务回复。不能批准正式规则、读取秘密或决定检查结论。未知操作只查询原回执，不换键重发。`)
    setCopied(true)
  })
  return <div ref={completion} className="jj-collaboration-task" data-single={items.length===1||undefined}>
    <div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath('/workspace?view=collaboration',projectId)} kind="quiet"><ArrowLeftOutlined aria-hidden="true"/>全部协作任务</ActionLink></div>
    <Heading eyebrow={focusQuestion&&task.goal.length<=80?task.goal:undefined} title={focusQuestion?selected.title:task.goal.length<=80?task.goal:"Agent 协作"} actions={!finished&&<CommandMenu className="jj-example-menu" menu={{selectable:false,items:[
      {key:'supplement',label:'补充目标与说明'},
      {key:task.state==='PAUSED'?'resume':'pause',label:task.state==='PAUSED'?'继续任务':'暂停任务'},
      ...(!decisions&&!activeJobs.length&&task.execution?.state!=='RUNNING'?[{key:'finish',label:'结束本次协作'}]:[]),
      {type:'divider' as const},{key:'cancel',label:'停止任务',danger:true},
    ],onClick:({key})=>{if(key==='supplement'){if(!followupPayload.current){setGoal(task.goal);setPurpose(task.purpose);setError(undefined)}setSupplement(true);return}void act(()=>collaborationApi.control(projectId,taskId,key))}}}><Button disabled={busy} className="jj-menu-trigger">任务操作<DownOutlined className="jj-menu-chevron" aria-hidden="true"/></Button></CommandMenu>}/>
    {state.error&&<Notice tone="caution">任务更新失败，保留上次读取的内容。<Button onClick={state.reload}>重新读取任务</Button></Notice>}{Boolean(error)&&!supplement&&<ErrorNote error={error}/>}
    {answered&&<div ref={answerCompletion} data-milestone-part="facts"><InlineFeedback tone="positive">回答已保存到当前任务。</InlineFeedback></div>}
    {supplement&&<Dialog title="补充当前任务" closeDisabled={busy} onClose={()=>setSupplement(false)} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} disabled={!goal.trim()} onClick={()=>void submitFollowup()}>{followupPayload.current?'核对原补充请求':'更新目标与说明'}</Button></>}><Field label="当前目标与补充要求"><textarea rows={5} maxLength={2000} value={goal} disabled={busy||Boolean(followupPayload.current)} onChange={event=>setGoal(event.target.value)}/></Field><Field label="任务类型"><Choice value={purpose} disabled={busy||Boolean(followupPayload.current)} onValueChange={value=>setPurpose(value as CollaborationPurpose)}>{Object.entries(purposeLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Choice></Field><p className="jj-small jj-muted">已有操作、产物和决定继续保留。正在执行时，后续回合读取更新后的目标；暂停的任务仍保持暂停。</p>{Boolean(error)&&<ErrorNote error={error}/>}</Dialog>}
    {launch&&<Dialog title="启动本地 Agent" onClose={()=>setLaunch(false)} actions={dismiss=><><Button onClick={dismiss}>取消</Button><Button kind="primary" busy={busy} onClick={()=>void act(async()=>{await collaborationApi.execute(projectId,taskId,allowChanges,executionRequest.current,continuous);executionRequest.current=crypto.randomUUID().replaceAll('-','');setLaunch(false)})}>启动并继续任务<ArrowRightOutlined aria-hidden="true"/></Button></>}>
      <div className="jj-agent-launch">
        <p>使用本机 Codex 继续处理当前任务。进展和需要你确认的事项会显示在这里。</p>
        <section className="jj-agent-launch-scope" aria-label="本次源码权限">
          {executor.data?.read_only?<p>当前仅可查看已有规则、任务与结果。</p>:<label className="jj-checkbox"><input type="checkbox" checked={allowChanges} onChange={event=>setAllowChanges(event.target.checked)} aria-labelledby="agent-source-title" aria-describedby="agent-source-hint"/><span><strong id="agent-source-title">允许修改当前应用的源码</strong><small id="agent-source-hint">未勾选时，Agent 仍可分析、准备材料和组织检查。</small></span></label>}
        </section>
        <div className="jj-agent-launch-limits"><span>{continuous?'最多 8 个模型回合':'执行 1 个模型回合'}</span><span>本次授权 30 分钟</span></div>
        <p className="jj-agent-launch-cost">使用本机 Codex 已配置账号的模型额度，可能产生费用。</p>
        <details><summary>执行方式与权限边界</summary><div className="jj-agent-launch-settings">
          <label className="jj-checkbox"><input type="checkbox" checked={continuous} onChange={event=>setContinuous(event.target.checked)} aria-labelledby="agent-continuous-title" aria-describedby="agent-continuous-hint"/><span><strong id="agent-continuous-title">持续推进当前任务</strong><small id="agent-continuous-hint">需要你确认时，任务会暂停；确认后自动继续，等待期间不调用模型。</small></span></label>
          <p>应用运行、测试请求和账号登录由界鉴处理，正式权限规则仍由你批准。文件读取范围和其他工具沿用本机 Codex 配置，可以随时暂停后续工作。</p>
        </div></details>
      </div>
    </Dialog>}
    <section className="jj-collaboration-overview" aria-label="当前任务">
      <div className="jj-collaboration-meta"><span>{purposeLabels[task.purpose]}</span><span className="jj-collaboration-state" data-tone={collaborationTone(task.state)} data-active={task.execution?.state==='RUNNING'&&!stopped||undefined}>{collaborationLabels[task.state]??task.state}</span></div>
      {task.goal.length>80&&<p className="jj-collaboration-goal">{task.goal}</p>}
    </section>
    <Tabs label="协作内容" value={view} onValueChange={setView} items={[{value:'work',label:'当前工作'},{value:'context',label:'产物与相关资料'},{value:'history',label:'操作记录'}]} panelId="collaboration-panel" idPrefix="collaboration-view"/>
    {copied&&<InlineFeedback tone="positive">任务已复制，尚未发送；在开发工具中继续这项任务即可。</InlineFeedback>}
    <div id="collaboration-panel" role="tabpanel" aria-labelledby={'collaboration-view-'+view} className="jj-collaboration-panel">
      {view==='work'&&<>
        {selected&&task.state==='PAUSED'&&<div className="jj-collaboration-paused"><p>{resumeForDecision?"任务已暂停，继续后可回答或确认当前待办。":"任务已暂停，可以先核对已保存产物或原操作回执；需要继续运行时，从任务操作恢复。"}</p>{resumeForDecision&&<Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.control(projectId,taskId,'resume'))}>继续任务<ArrowRightOutlined aria-hidden="true"/></Button>}</div>}
        {selected?<div className="jj-collaboration-workbench" data-single={items.length===1||undefined}>
          {items.length>1&&<nav className="jj-collaboration-queue" aria-label="待处理事项">
            <header><h2 className="jj-title-group">需要你处理</h2><span>{decisions} 项</span></header>
            <IndexSelection identity={selected.id} label="事项选择">{items.map(item=>{const Icon=workIcons[item.kind];return <button key={item.id} className="jj-index-item jj-collaboration-item" aria-current={selected.id===item.id?'true':undefined} onClick={()=>setSelectedId(item.id)}><Icon aria-hidden="true"/><span><small>{item.label}</small><strong>{item.title}</strong></span></button>})}</IndexSelection>
          </nav>}
          <section key={selected.id} className="jj-collaboration-detail" data-kind={selected.kind} aria-label="当前事项">
            {!focusQuestion&&<header>{selected.kind!=='question'&&<p className="jj-eyebrow">{selected.label}</p>}<h2>{selected.title}</h2></header>}
            {selected.kind==='question'&&<>
              <QuestionAnswer task={task} question={selected.data} answer={answers[selected.data.question_id]??''} disabled={stopped||busy} onChange={value=>setAnswers({...answers,[selected.data.question_id]:value})}/>
              <TaskActions><Button kind="primary" disabled={stopped||!answers[selected.data.question_id]?.trim()} busy={busy} onClick={()=>void act(async()=>{const id=selected.data.question_id;await collaborationApi.answer(projectId,taskId,id,answers[id].trim());markMilestone('answer:'+projectId+':'+taskId+':'+id);setAnswered(id)})}>提交回答并继续<ArrowRightOutlined aria-hidden="true"/></Button></TaskActions>
            </>}
            {selected.kind==='review'&&<CollaborationArtifactReview projectId={projectId} task={task} review={selected.data}/>}
            {selected.kind==='pending'&&<><p className="jj-collaboration-hint">{selected.data.capability.includes('check')?'本次检查用于核对当前任务所需的业务结果，检查对象与执行范围如下。':'确认后执行下面列出的操作，以继续处理当前任务。'}</p><OperationSummary operation={selected.data}/><TaskActions><Button disabled={busy||stopped} onClick={()=>void act(()=>collaborationApi.decide(projectId,taskId,selected.data.operation_id,false))}>{selected.data.capability==='github.issue_create'?'暂不创建':'暂不执行'}</Button><Button kind="primary" disabled={stopped} busy={busy} onClick={()=>void act(()=>collaborationApi.decide(projectId,taskId,selected.data.operation_id,true))}>{selected.data.capability==='github.issue_create'?'创建这张工单':'确认并执行'}<ArrowRightOutlined aria-hidden="true"/></Button></TaskActions></>}
            {selected.kind==='uncertain'&&<><p className="jj-collaboration-hint">这项操作的结果还未确认。先查看上次操作结果，再决定后续工作。</p><TaskActions><Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.reconcile(projectId,taskId,selected.data.operation_id))}>核对原操作<ArrowRightOutlined aria-hidden="true"/></Button></TaskActions></>}
          </section>
        </div>:<section data-milestone-part="results" className="jj-collaboration-current" aria-label="当前进展" aria-live="polite">
          <header><h2>{check?(check.verdict?checkLabels[check.verdict]:check.lifecycle==='FAILED'?'检查未完成':check.lifecycle==='CANCELLED'?'检查已停止':'检查尚未结束'):task.outcome?.title??(activeJobs.length?'正在处理已确认的操作':finished?'协作已结束':task.state==='PAUSED'?'任务已暂停':'等待 Agent 继续处理')}</h2></header>
          {task.execution?.message&&<p className="jj-collaboration-hint">{task.execution.message}</p>}
          {activeJobs.map(item=><div key={item.id} className="jj-collaboration-live"><strong>{item.label}</strong><span>{executionLabels[item.phase]}</span><ActionLink href={href(item.destination)}>查看执行进度<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}
          <TaskActions>
            {check&&<ActionLink kind={task.state==='PAUSED'||readyForAgent?'quiet':'primary'} href={href(reportPath!)}>{check.revalidation?'查看复验结果':'查看检查报告'}<ArrowRightOutlined aria-hidden="true"/></ActionLink>}
            {task.state==='PAUSED'?<Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.control(projectId,taskId,'resume'))}>继续任务<ArrowRightOutlined aria-hidden="true"/></Button>:readyForAgent&&(executor.data?.available?(executor.data.ready===false?<ActionLink kind="primary" href={href(executor.data.setup_path)}>{executor.data.setup_label}<ArrowRightOutlined aria-hidden="true"/></ActionLink>:<Button kind="primary" busy={busy} onClick={()=>setLaunch(true)}>继续本地 Agent<ArrowRightOutlined aria-hidden="true"/></Button>):<Button kind="primary" busy={busy} complete={copied} onClick={()=>void copy()}>复制任务到开发工具<ArrowRightOutlined aria-hidden="true"/></Button>)}
          </TaskActions>
        </section>}
        {selected&&activeJobs.length>0&&<p className="jj-collaboration-background">另有 {activeJobs.length} 项已确认操作正在后台执行，可在操作记录中查看进展。</p>}
      </>}
      {view==='context'&&<div className="jj-collaboration-context-grid">
        <section className="jj-collaboration-artifacts"><h2>任务产物</h2>{task.outcome&&<p>{task.outcome.title}<span className="jj-small jj-muted">{task.outcome.fulfilled?' · 已取得依据':finished?' · 仍有未完成项':''}</span></p>}
          {reviews.map(item=><ActionLink presentation="row" key={item.id} href={href(item.destination)}><span>{item.title}<small>待审阅</small></span><ArrowRightOutlined aria-hidden="true"/></ActionLink>)}
          {artifacts.map(({label,path})=><ActionLink presentation="row" key={path} href={href(path)}>{label}<ArrowRightOutlined aria-hidden="true"/></ActionLink>)}
          {!artifacts.length&&!reviews.length&&<p className="jj-collaboration-hint">尚无任务产物。</p>}
        </section>
        {(task.editor||task.references.run_id||returnDestination(task.references.return_to??null))&&<section className="jj-collaboration-handoff"><h2>交接内容</h2>{task.editor?.kind==='FLOW'?<><p>{task.editor.steps.length} 个请求 · {task.editor.evidence_effect_ids.length} 项结果查询</p><ul>{task.editor.steps.map(step=><li key={step.id}><code>{step.method} {step.path??'路径待补全'}</code></li>)}</ul></>:task.editor?.kind==='PROOF'?<dl className="jj-facts"><div><dt>业务数据</dt><dd>{task.editor.collection??task.editor.table??'尚未选择'}</dd></div><div><dt>判断字段</dt><dd>{task.editor.protected_column??'尚未选择'}</dd></div></dl>:task.editor?.kind==='SCENARIO'?<p>{task.editor.document.label} · {task.editor.document.experiments.length} 项实验</p>:task.references.run_id?<ActionLink href={href('/reports?run_id='+encodeURIComponent(task.references.run_id))}>交接的检查报告<ArrowRightOutlined aria-hidden="true"/></ActionLink>:null}
          {returnDestination(task.references.return_to??null)&&<TaskActions><ActionLink href={'#'+scopedPath(returnDestination(task.references.return_to??null)!,projectId)}>{task.editor?.kind==='FLOW'?'返回接口流程草稿':task.editor?.kind==='PROOF'?'返回判断方式草稿':'返回交接位置'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></TaskActions>}
        </section>}
        {!finished&&<section className="jj-collaboration-methods"><h2>协作连接</h2><p className="jj-collaboration-hint">在已连接的开发工具中继续处理这项任务。</p><TaskActions><ActionLink href={href('/tools')}>管理开发工具连接</ActionLink>{!readyForAgent&&<Button busy={busy} complete={copied} onClick={()=>void copy()}>复制任务到开发工具<ArrowRightOutlined aria-hidden="true"/></Button>}</TaskActions></section>}
      </div>}
      {view==='history'&&<section className="jj-collaboration-progress" aria-label="操作记录"><h2>操作记录</h2>
        {recent.length>0&&<section><h3>最近操作</h3><ul className="jj-collaboration-receipts">{recent.map(item=><li key={item.operation_id}><strong>{item.title}</strong><span>{collaborationLabels[item.state]??item.state}</span></li>)}</ul></section>}
        {activity.data&&activity.data.length>0&&<section><h3>后台执行</h3>{[...activeJobs,...completedJobs].map(item=><div key={item.id} className="jj-collaboration-live"><strong>{item.label}</strong><span>{executionLabels[item.phase]}</span><ActionLink href={href(item.destination)}>{jobEnded(item.phase)?'查看执行结果':'查看执行进度'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}</section>}
        {visibleEvents.length>0&&<section><h3>任务进展</h3><ol>{visibleEvents.slice().reverse().map(event=><li key={event.id}><div><strong>{event.title}</strong><small>{event.actor==='USER'?'你的决定':event.actor==='AGENT'?'Agent':'界鉴'}　{new Date(event.at_us/1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</small></div></li>)}</ol></section>}
        {!recent.length&&!activity.data?.length&&!visibleEvents.length&&<p className="jj-collaboration-hint">还没有操作记录。</p>}
      </section>}
    </div>
  </div>
}

function OperationSummary({operation}:{operation:CollaborationOperation}){
  if(operation.capability==='github.issue_create'){
    const content=Object.fromEntries((operation.summary??[]).map(item=>[item.label,String(item.value)]))
    return <div className="jj-github-issue-review"><p>确认后，会在 <strong>{String(operation.arguments.repository)}</strong> 新建一张工单，把当前问题交给协作者继续处理。</p><article aria-label="将要创建的工单"><h3>{content['工单标题']??'当前问题的检查结果'}</h3>{(content['将发送的正文']??'请先核对原报告中的问题。').split('\n\n').map((paragraph,index)=><p key={index}>{paragraph}</p>)}</article><details><summary>工单关联的检查记录</summary><p>工单会关联原报告和问题，方便返回查看这次检查。</p><dl className="jj-facts"><div><dt>原报告</dt><dd><code>{String(operation.arguments.run_id)}</code></dd></div><div><dt>原问题</dt><dd><code>{String(operation.arguments.case_id)}</code></dd></div></dl></details><p className="jj-small jj-muted">发送结果不明确时，界鉴会先查找原工单，避免重复创建。</p></div>
  }

  const labels:Record<string,string>={entry:'运行入口',port:'本地端口',revision:'当前修订',build_script:'构建步骤',allow_install_scripts:'依赖安装脚本',identity_id:'测试账号',flow_id:'操作流程',source_id:'证明来源',run_id:'检查记录',change_id:'关联修改'}
  const rows=(operation.summary??[]).map(item=>[item.label,item.value])
  // 服务端摘要可只包含执行原因；已知授权对象仍须常显，原始协议细节留在展开区。
  for(const [key,value] of Object.entries(operation.arguments))if(key in labels&&value!==null&&!rows.some(([label])=>label===labels[key]))rows.push([labels[key],typeof value==='boolean'?value?'允许':'不执行':String(value)])
  return <><dl className="jj-facts jj-collaboration-summary" data-layout="columns">{rows.map(([key,value],index)=><div key={index}><dt>{String(key)}</dt><dd>{typeof value==='boolean'?value?'允许':'不执行':String(value)}</dd></div>)}</dl><details><summary>核对本次具体设置</summary><pre>{JSON.stringify(operation.arguments,null,2)}</pre></details></>
}

const investigateAnswer='暂不确定，请在当前任务已有授权范围内继续查证，并提供可以核对的依据；涉及业务决定时再向我确认。'
function QuestionAnswer({task,question,answer,disabled,onChange}:{task:CollaborationTask;question:CollaborationTask['questions'][number];answer:string;disabled:boolean;onChange:(value:string)=>void}){
  const uncertain=answer===investigateAnswer, editor=task.editor?.kind==='PROOF'?task.editor:undefined
  const origin=returnDestination(task.references.return_to??null)
  // 依据来自当前应用已保存的来源配置；交接草稿另行标注，不能冒充已核对事实。
  const sources=useRead('question-proof-context:'+task.project_id+':'+(editor?.action_id??'')+':'+(editor?.effect_id??''),async()=>{
    if(!editor)return undefined
    const value=await proofSourcesApi.context(task.project_id);assertProject(value.project_id,task.project_id);return value
  })
  const contextAction=sources.data?.actions?.find(action=>action.action_id===editor?.action_id)
  const contextEffect=contextAction?.effects.find(effect=>effect.effect_id===editor?.effect_id)
  const sameBasis=Boolean(editor&&sources.data?.basis_id===editor.basis_id)
  const matching=(sameBasis?sources.data?.sources:undefined)?.filter(source=>source.config.action_id===editor?.action_id&&source.config.effect_id===editor?.effect_id&&(!contextAction||source.config.action_revision===contextAction.revision)&&source.config.resource_binding_id===editor?.resource_binding_id&&(source.config.table??source.config.collection??null)===(editor?.table??editor?.collection??null)&&(source.config.protected_column??null)===(editor?.protected_column??null))??[]
  return <div className="jj-question-answer">{editor&&<section className="jj-question-purpose"><p>{contextAction?`正在为“${contextAction.label}”准备结果证明，用于判断“${contextEffect?.label??'对应业务结果'}”是否发生。请选择实际保存该结果的字段。`:'正在读取这次交接对应的业务操作。'}</p></section>}
    {editor?<section className="jj-question-basis"><p>交接草稿：<code>{editor.collection??editor.table??'尚未指定的数据位置'}</code>{editor.protected_column&&<>，判断字段为 <code>{editor.protected_column}</code></>}。{!editor.protected_column&&'当前草稿尚未指定判断字段。'}</p>
      {matching.length>0?matching.map(source=><ActionLink key={source.source_id} kind="quiet" href={'#'+scopedPath(withReturnDestination('/preparation?'+new URLSearchParams({proof_sources:'1',source_id:source.source_id,revision:String(source.revision)}),'/workspace?view=collaboration&task_id='+task.task_id),task.project_id)}>核对这份来源<span className="jj-small jj-muted">第 {source.revision} 修订 · {source.adopted?'已用于检查':'尚未采用'}</span><ArrowRightOutlined aria-hidden="true"/></ActionLink>):origin&&<ActionLink kind="quiet" href={'#'+scopedPath(origin,task.project_id)}>查看交接的判断方式<ArrowRightOutlined aria-hidden="true"/></ActionLink>}
    </section>:<p className="jj-collaboration-hint">请按实际业务回答。若现有信息不足，可以让 Agent 留在本任务继续查证。</p>}
    {editor&&!sources.loading&&!sameBasis&&!sources.error&&<p className="jj-small jj-muted">交接后的应用依据已有变化，请先回到判断方式核对。原回答继续保留。</p>}{editor&&!sources.loading&&!matching.length&&!sources.error&&<p className="jj-small jj-muted">当前只有交接草稿，尚无对应的已保存来源。字段名不足以确认业务用途时，可选择“暂不确定”继续查证。</p>}
    {sources.error&&<><ErrorNote error={sources.error}/><Button onClick={sources.reload}>重新读取来源依据</Button></>}
    <fieldset className="jj-choice-field" aria-label="你的回答"><legend className="jj-sr-only">你的回答</legend>{question.options.map(option=><label key={option}><input type="radio" aria-label={option} name={'question-'+question.question_id} checked={answer===option} disabled={disabled} onChange={()=>onChange(option)}/><span>{option}{editor&&<small>{matching.some(source=>source.config.protected_column===option)?`已保存的判断字段，关联“${contextEffect?.label??'当前业务结果'}”；请核对其业务含义`:sources.data?.sqlite?.some(table=>table.table===editor.table&&table.fields.includes(option))?(sources.data.sqlite.find(table=>table.table===editor.table)?.resource_column===option?'用于对应测试资源的编号字段':sources.data.sqlite.find(table=>table.table===editor.table)?.owner_column===option?'用于对应资源所有者的字段':`已声明于 ${editor.table}，尚未确认它保存的业务内容`):'尚未取得足以确认此选项用途的依据'}</small>}</span></label>)}
      <label><input type="radio" name={'question-'+question.question_id} checked={Boolean(answer)&&!uncertain&&!question.options.includes(answer)} disabled={disabled} onChange={()=>onChange(' ')}/><span>填写其他回答</span></label>
      <label><input type="radio" name={'question-'+question.question_id} checked={uncertain} disabled={disabled} onChange={()=>onChange(investigateAnswer)}/><span>暂不确定<small>让 Agent 在原任务的授权范围内继续查证</small></span></label>
    </fieldset>
    {uncertain?<p className="jj-question-next">回答将保存到当前任务。条件不足时，Agent 会说明需要补充的信息并等待处理。</p>:<details className="jj-question-supplement" open={Boolean(answer)&&!question.options.includes(answer)}><summary>补充说明或填写回答</summary><Field label="你的回答或补充说明"><textarea rows={3} maxLength={2000} disabled={disabled} value={answer} onChange={event=>onChange(event.target.value)}/></Field></details>}
  </div>
}
