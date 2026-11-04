import {useRef,useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import DownOutlined from '@ant-design/icons/DownOutlined'
import QuestionCircleOutlined from '@ant-design/icons/QuestionCircleOutlined'
import FileSearchOutlined from '@ant-design/icons/FileSearchOutlined'
import SafetyOutlined from '@ant-design/icons/SafetyOutlined'
import SyncOutlined from '@ant-design/icons/SyncOutlined'
import {Dropdown} from 'antd'
import {collaborationApi,collaborationLabels,collaborationTone,purposeLabels,type CollaborationOperation,type CollaborationPurpose} from '../../entities/runtime/api/collaboration'
import {useRead} from '../../shared/lib/useRead'
import {go,scopedPath,returnDestination} from '../../shared/lib/navigation'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Heading,Field} from '../../shared/ui/layout'
import {ErrorNote, PageError,Loading,Notice} from '../../shared/ui/feedback'
import {Dialog} from '../../shared/ui/Dialog'
import {Choice} from '../../shared/ui/Choice'
import {Tabs} from '../../shared/ui/Tabs'
import {IndexSelection} from '../../shared/ui/IndexSelection'
import {ApiError} from '../../shared/api/http'
import type {CollaborationTask} from '../../entities/runtime/api/collaboration'
import './collaboration.css'

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
  const [launch,setLaunch]=useState(false),[allowChanges,setAllowChanges]=useState(false),[menuOpen,setMenuOpen]=useState(false)
  const [continuous,setContinuous]=useState(true)
  const [view,setView]=useState('work'),[selectedId,setSelectedId]=useState<string>()
  const [supplement,setSupplement]=useState(false),[goal,setGoal]=useState(''),[purpose,setPurpose]=useState<CollaborationPurpose>('CHECK')
  const followupRequest=useRef(crypto.randomUUID().replaceAll('-',''))
  const followupPayload=useRef<Pick<CollaborationTask,'goal'|'purpose'|'references'|'editor'>|undefined>(undefined)
  const menuTrigger=useRef<HTMLButtonElement>(null)
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[copied,setCopied]=useState(false),[answers,setAnswers]=useState<Record<string,string>>({})
  const act=async(work:()=>Promise<unknown>)=>{
    setBusy(true);setError(undefined)
    try{await work();state.reload();window.dispatchEvent(new Event('jiejian:collaboration-changed'))}
    catch(value){setError(value)}finally{setBusy(false)}
  }
  if(state.error)return <PageError title="Agent 协作" error={state.error}/>
  const task=state.data
  if(!task)return <Loading page/>
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
  const artifacts=artifactLinks(task.operations,task.references).filter(item=>!reviews.some(review=>review.destination===item.path)),check=task.latest_check
  const continuing=task.execution?.continuous&&['RUNNING','WAITING'].includes(task.execution.state)&&!stopped
  const readyForAgent=!continuing&&['WAITING_AGENT','BLOCKED'].includes(task.state)&&!decisions&&!activeJobs.length
  const reportPath=check?'/reports?run_id='+encodeURIComponent(check.run_id):null
  const recent=task.operations.slice(-4).reverse()
  const visibleEvents=task.events.filter(event=>event.title!=='已建立协作任务'&&!task.operations.some(operation=>event.title===operation.title||event.title.startsWith(operation.title+'：'))&&!questions.some(question=>event.title===question.question))
  const href=(path:string)=>'#'+scopedPath(path,projectId)
  const copy=()=>act(async()=>{
    await navigator.clipboard.writeText(`请继续界鉴协作任务。project_id=${projectId}\ntask_id=${taskId}\n先调用 jiejian_collaboration_context，按需读取 jiejian_collaboration_capability，再通过 jiejian_collaboration_action 处理当前目标。复用现有有效配置；业务不明确时用 jiejian_collaboration_question 提问。需要人的决定时等待同一任务回复。不能批准正式规则、读取秘密或决定检查结论。未知操作只查询原回执，不换键重发。`)
    setCopied(true)
  })
  return <>
    <div className="jj-back-link"><Button kind="quiet" onClick={()=>go('/workspace?view=collaboration',projectId)}><ArrowLeftOutlined aria-hidden="true"/>全部协作任务</Button></div>
    <Heading title="Agent 协作" actions={!finished&&<Dropdown open={menuOpen} onOpenChange={setMenuOpen} trigger={['click']} placement="bottomRight" autoFocus overlayClassName="jj-example-menu" menu={{selectable:false,items:[
      {key:task.state==='PAUSED'?'resume':'pause',label:task.state==='PAUSED'?'继续任务':'暂停任务'},
      ...(!decisions&&!activeJobs.length&&task.execution?.state!=='RUNNING'?[{key:'finish',label:'结束本次协作'}]:[]),
      {type:'divider' as const},{key:'cancel',label:'停止任务',danger:true},
    ],onClick:({key})=>{setMenuOpen(false);menuTrigger.current?.focus({preventScroll:true});void act(()=>collaborationApi.control(projectId,taskId,key))}}}><Button ref={menuTrigger} disabled={busy} aria-haspopup="menu" aria-expanded={menuOpen} className="jj-menu-trigger">任务操作<DownOutlined className="jj-menu-chevron" aria-hidden="true"/></Button></Dropdown>}/>
    {Boolean(error)&&!supplement&&<ErrorNote error={error}/>}
    {supplement&&<Dialog title="补充当前任务" closeDisabled={busy} onClose={()=>setSupplement(false)} actions={<><Button disabled={busy} onClick={()=>setSupplement(false)}>取消</Button><Button kind="primary" busy={busy} disabled={!goal.trim()} onClick={()=>void submitFollowup()}>{followupPayload.current?'核对原补充请求':'更新目标与说明'}</Button></>}><Field label="当前目标与补充要求"><textarea rows={5} maxLength={2000} value={goal} disabled={busy||Boolean(followupPayload.current)} onChange={event=>setGoal(event.target.value)}/></Field><Field label="任务类型"><Choice value={purpose} disabled={busy||Boolean(followupPayload.current)} onValueChange={value=>setPurpose(value as CollaborationPurpose)}>{Object.entries(purposeLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Choice></Field><p className="jj-small jj-muted">已有操作、产物和决定继续保留。正在执行时，后续回合读取更新后的目标；暂停的任务仍保持暂停。</p>{Boolean(error)&&<ErrorNote error={error}/>}</Dialog>}
    {launch&&<Dialog title="启动本地 Agent" onClose={()=>setLaunch(false)} actions={<><Button onClick={()=>setLaunch(false)}>取消</Button><Button kind="primary" busy={busy} onClick={()=>void act(async()=>{await collaborationApi.execute(projectId,taskId,allowChanges,executionRequest.current,continuous);executionRequest.current=crypto.randomUUID().replaceAll('-','');setLaunch(false)})}>启动并继续任务<ArrowRightOutlined aria-hidden="true"/></Button></>}>
      <div className="jj-agent-launch">
        <p>由本机 Codex 接续当前目标，进展和需要你决定的事项留在这项任务中。</p>
        <section className="jj-agent-launch-scope" aria-label="本次源码权限">
          {executor.data?.read_only?<p>当前仅可查看已有规则、任务与结果。</p>:<label className="jj-checkbox"><input type="checkbox" checked={allowChanges} onChange={event=>setAllowChanges(event.target.checked)} aria-labelledby="agent-source-title" aria-describedby="agent-source-hint"/><span><strong id="agent-source-title">允许修改当前应用的源码</strong><small id="agent-source-hint">未勾选时，Agent 仍可分析、准备材料和组织检查。</small></span></label>}
        </section>
        <div className="jj-agent-launch-limits"><span>{continuous?'最多 8 个模型回合':'执行 1 个模型回合'}</span><span>本次授权 30 分钟</span></div>
        <p className="jj-agent-launch-cost">使用本机 Codex 已配置账号的模型额度，可能产生费用。</p>
        <details><summary>执行方式与权限边界</summary><div className="jj-agent-launch-settings">
          <label className="jj-checkbox"><input type="checkbox" checked={continuous} onChange={event=>setContinuous(event.target.checked)} aria-labelledby="agent-continuous-title" aria-describedby="agent-continuous-hint"/><span><strong id="agent-continuous-title">持续推进当前任务</strong><small id="agent-continuous-hint">需要确认时暂停等待，你确认后自动接续；等待期间不调用模型。</small></span></label>
          <p>应用运行、测试请求和账号登录由界鉴处理，正式权限规则仍由你批准。文件读取范围和其他工具沿用本机 Codex 配置，可以随时暂停后续工作。</p>
        </div></details>
      </div>
    </Dialog>}
    <section className="jj-collaboration-overview" aria-label="当前任务">
      <div className="jj-collaboration-meta"><span>{purposeLabels[task.purpose]}</span><span className="jj-collaboration-state" data-tone={collaborationTone(task.state)}>{collaborationLabels[task.state]??task.state}</span></div>
      <p className="jj-collaboration-goal">{task.goal}</p>
      {!finished&&<Button kind="quiet" disabled={busy} onClick={()=>{if(!followupPayload.current){setGoal(task.goal);setPurpose(task.purpose);setError(undefined)}setSupplement(true)}}>补充目标与说明</Button>}
    </section>
    <Tabs label="协作内容" value={view} onValueChange={setView} items={[{value:'work',label:'当前工作'},{value:'context',label:'产物与上下文'},{value:'history',label:'处理记录'}]} panelId="collaboration-panel" idPrefix="collaboration-view"/>
    {copied&&<Notice tone="positive">任务已复制，尚未发送；在开发工具中继续这项任务即可。</Notice>}
    <div id="collaboration-panel" role="tabpanel" aria-labelledby={'collaboration-view-'+view} className="jj-collaboration-panel">
      {view==='work'&&<>
        {selected&&task.state==='PAUSED'&&<div className="jj-collaboration-paused"><p>继续任务后可回答或确认待办。</p><Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.control(projectId,taskId,'resume'))}>继续任务<ArrowRightOutlined aria-hidden="true"/></Button></div>}
        {selected?<div className="jj-collaboration-workbench">
          <nav className="jj-collaboration-queue" aria-label="待处理事项">
            <header><h2>需要你处理</h2><span>{decisions} 项</span></header>
            <IndexSelection identity={selected.id} label="事项选择">{items.map(item=>{const Icon=workIcons[item.kind];return <button key={item.id} className="jj-index-item jj-collaboration-item" aria-current={selected.id===item.id?'true':undefined} onClick={()=>setSelectedId(item.id)}><Icon aria-hidden="true"/><span><small>{item.label}</small><strong>{item.title}</strong></span></button>})}</IndexSelection>
          </nav>
          <section key={selected.id} className="jj-collaboration-detail" aria-label="当前事项">
            <header><p className="jj-eyebrow">{selected.label}</p><h2>{selected.title}</h2></header>
            {selected.kind==='question'&&<>
              <p className="jj-collaboration-hint">选择建议回答，或直接说明你的业务要求。</p>
              {selected.data.options.length>0&&<div className="jj-collaboration-answers" role="group" aria-label="建议回答">{selected.data.options.map(option=><Button key={option} disabled={stopped||busy} aria-pressed={answers[selected.data.question_id]===option} onClick={()=>setAnswers({...answers,[selected.data.question_id]:option})}>{option}</Button>)}</div>}
              <Field label="你的回答或补充说明"><textarea rows={4} maxLength={2000} disabled={stopped||busy} value={answers[selected.data.question_id]??''} onChange={event=>setAnswers({...answers,[selected.data.question_id]:event.target.value})}/></Field>
              <footer><Button kind="primary" disabled={stopped||!answers[selected.data.question_id]?.trim()} busy={busy} onClick={()=>void act(()=>collaborationApi.answer(projectId,taskId,selected.data.question_id,answers[selected.data.question_id].trim()))}>提交回答并继续<ArrowRightOutlined aria-hidden="true"/></Button></footer>
            </>}
            {selected.kind==='review'&&<><p className="jj-collaboration-hint">打开对应产物，核对内容与影响范围后再决定是否采用。</p><footer><ActionLink kind="primary" href={href(selected.data.destination)}>{selected.data.action_label}<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer></>}
            {selected.kind==='pending'&&<><OperationSummary operation={selected.data}/><footer><Button disabled={busy||stopped} onClick={()=>void act(()=>collaborationApi.decide(projectId,taskId,selected.data.operation_id,false))}>暂不执行</Button><Button kind="primary" disabled={stopped} busy={busy} onClick={()=>void act(()=>collaborationApi.decide(projectId,taskId,selected.data.operation_id,true))}>确认并执行<ArrowRightOutlined aria-hidden="true"/></Button></footer></>}
            {selected.kind==='uncertain'&&<><p className="jj-collaboration-hint">这项操作的执行结果尚未确认。先查询原回执，再决定后续工作。</p><footer><Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.reconcile(projectId,taskId,selected.data.operation_id))}>核对原操作<ArrowRightOutlined aria-hidden="true"/></Button></footer></>}
          </section>
        </div>:<section className="jj-collaboration-current" aria-label="当前进展" aria-live="polite">
          <header><p className="jj-eyebrow">{finished?'本次协作':task.state==='PAUSED'?'任务已暂停':continuing?'Agent 正在接续':'接下来'}</p><h2>{check?(check.verdict?checkLabels[check.verdict]:check.lifecycle==='FAILED'?'检查未完成':check.lifecycle==='CANCELLED'?'检查已停止':'检查尚未结束'):task.outcome?.title??(activeJobs.length?'正在处理已确认的操作':finished?'协作已结束，产物与记录已保留':task.state==='PAUSED'?'可以从当前进度继续':'继续推进当前目标')}</h2></header>
          {task.execution?.message&&<p className="jj-collaboration-hint">{task.execution.message}</p>}
          {task.execution?.continuous&&<p className="jj-small jj-muted">已使用 {task.execution.turn_count??1} / {task.execution.max_turns??8} 个模型回合</p>}
          {activeJobs.map(item=><div key={item.id} className="jj-collaboration-live"><strong>{item.label}</strong><span>{executionLabels[item.phase]}</span><ActionLink href={href(item.destination)}>查看执行进度<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}
          <footer>{task.state==='PAUSED'?<Button kind="primary" busy={busy} onClick={()=>void act(()=>collaborationApi.control(projectId,taskId,'resume'))}>继续任务<ArrowRightOutlined aria-hidden="true"/></Button>:readyForAgent&&(executor.data?.available?(executor.data.ready===false?<ActionLink kind="primary" href={href(executor.data.setup_path)}>{executor.data.setup_label}<ArrowRightOutlined aria-hidden="true"/></ActionLink>:<Button kind="primary" busy={busy} onClick={()=>setLaunch(true)}>继续本地 Agent<ArrowRightOutlined aria-hidden="true"/></Button>):<Button kind="primary" busy={busy} onClick={()=>void copy()}>复制任务到开发工具<ArrowRightOutlined aria-hidden="true"/></Button>)}{check&&<ActionLink kind={readyForAgent?'quiet':'primary'} href={href(reportPath!)}>{check.revalidation?'查看复验结果':'查看检查报告'}<ArrowRightOutlined aria-hidden="true"/></ActionLink>}</footer>
        </section>}
        {selected&&activeJobs.length>0&&<p className="jj-collaboration-background">另有 {activeJobs.length} 项已确认操作正在后台执行，可在处理记录中查看进展。</p>}
      </>}
      {view==='context'&&<div className="jj-collaboration-context-grid">
        <section className="jj-collaboration-artifacts"><h2>任务产物</h2>{task.outcome&&<p>{task.outcome.title}<span className="jj-small jj-muted">{task.outcome.fulfilled?' · 已取得依据':finished?' · 仍有未完成项':''}</span></p>}
          {reviews.map(item=><ActionLink key={item.id} href={href(item.destination)}><span>{item.title}<small>待审阅</small></span><ArrowRightOutlined aria-hidden="true"/></ActionLink>)}
          {artifacts.map(({label,path})=><ActionLink key={path} href={href(path)}>{label}<ArrowRightOutlined aria-hidden="true"/></ActionLink>)}
          {!artifacts.length&&!reviews.length&&<p className="jj-collaboration-hint">尚未形成产物。后续保存的规则、材料和报告会保留在这里。</p>}
        </section>
        <section className="jj-collaboration-handoff"><h2>交接上下文</h2>{task.editor?.kind==='FLOW'?<><p>{task.editor.steps.length} 个请求 · {task.editor.evidence_effect_ids.length} 项结果查询</p><ul>{task.editor.steps.map(step=><li key={step.id}><code>{step.method} {step.path??'路径待补全'}</code></li>)}</ul></>:<p className="jj-collaboration-hint">沿用此任务所属应用和已交接的对象。</p>}
          {returnDestination(task.references.return_to??null)&&<footer><ActionLink href={href(returnDestination(task.references.return_to??null)!)}>{task.editor?.kind==='FLOW'?'返回接口流程草稿':task.editor?.kind==='PROOF'?'返回判断方式草稿':'返回交接位置'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></footer>}
        </section>
        {!finished&&<section className="jj-collaboration-methods"><h2>协作连接</h2><p className="jj-collaboration-hint">在已连接的开发工具中接续同一任务。</p><footer><ActionLink href={href('/tools')}>管理开发工具连接</ActionLink>{!readyForAgent&&<Button busy={busy} onClick={()=>void copy()}>复制任务到开发工具<ArrowRightOutlined aria-hidden="true"/></Button>}</footer></section>}
      </div>}
      {view==='history'&&<section className="jj-collaboration-progress" aria-label="处理记录"><h2>处理记录</h2>
        {recent.length>0&&<section><h3>最近操作</h3><ul className="jj-collaboration-receipts">{recent.map(item=><li key={item.operation_id}><strong>{item.title}</strong><span>{collaborationLabels[item.state]??item.state}</span></li>)}</ul></section>}
        {activity.data&&activity.data.length>0&&<section><h3>后台执行</h3>{[...activeJobs,...completedJobs].map(item=><div key={item.id} className="jj-collaboration-live"><strong>{item.label}</strong><span>{executionLabels[item.phase]}</span><ActionLink href={href(item.destination)}>{jobEnded(item.phase)?'查看执行结果':'查看执行进度'}<ArrowRightOutlined aria-hidden="true"/></ActionLink></div>)}</section>}
        {visibleEvents.length>0&&<section><h3>任务进展</h3><ol>{visibleEvents.slice().reverse().map(event=><li key={event.id}><div><strong>{event.title}</strong><small>{event.actor==='USER'?'你的决定':event.actor==='AGENT'?'Agent':'界鉴'}　{new Date(event.at_us/1000).toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}</small></div></li>)}</ol></section>}
        {!recent.length&&!activity.data?.length&&!visibleEvents.length&&<p className="jj-collaboration-hint">还没有处理记录。</p>}
      </section>}
    </div>
  </>
}

function OperationSummary({operation}:{operation:CollaborationOperation}){
  const labels:Record<string,string>={entry:'运行入口',port:'本地端口',revision:'当前修订',build_script:'构建步骤',allow_install_scripts:'依赖安装脚本',identity_id:'测试账号',flow_id:'操作流程',source_id:'证明来源',run_id:'检查记录',change_id:'关联修改'}
  const rows=operation.summary?.length?operation.summary.map(item=>[item.label,item.value]):Object.entries(operation.arguments).filter(([key,value])=>key in labels&&value!==null).map(([key,value])=>[labels[key],value])
  return <><dl className="jj-collaboration-summary">{rows.map(([key,value],index)=><div key={index}><dt>{String(key)}</dt><dd>{typeof value==='boolean'?value?'允许':'不执行':String(value)}</dd></div>)}</dl><details><summary>核对本次具体设置</summary><pre>{JSON.stringify(operation.arguments,null,2)}</pre></details></>
}
