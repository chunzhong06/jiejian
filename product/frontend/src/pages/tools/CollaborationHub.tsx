import {SearchField} from '../../shared/ui/SearchField'
import {Choice} from '../../shared/ui/Choice'
import {readPending,savePending} from '../../shared/lib/operations'
import {useEffect,useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {collaborationApi,collaborationLabels,collaborationTone,purposeLabels} from '../../entities/runtime/api/collaboration'
import {requestCollaboration} from '../../entities/runtime/model/handoff'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath} from '../../shared/lib/navigation'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Segmented} from '../../shared/ui/Segmented'
import {Badge,Empty,Loading,PageError} from '../../shared/ui/feedback'
import './collaboration.css'

export function CollaborationHub({projectId}:{projectId:string}){
  const state=useRead('collaboration-tasks:'+projectId,signal=>collaborationApi.list(projectId,signal))
  const key='collaboration-index:'+projectId
  const restored=readPending<{view:string;query:string;attention:string}>(key,(value):value is {view:string;query:string;attention:string}=>Boolean(value)&&typeof value==='object'&&typeof (value as {query?:unknown}).query==='string'&&(value as {query:string}).query.length<=200)
  const [view,setView]=useState(restored?.view??'active'),[query,setQuery]=useState(restored?.query??''),[attention,setAttention]=useState(restored?.attention??'all')
  useEffect(()=>{savePending(key,{view,query:query.slice(0,200),attention})},[key,view,query,attention])
  if(state.loading)return <Loading page/>
  if(state.error)return <PageError title="Agent 协作" error={state.error}/>
  const tasks=(state.data??[]).filter(task=>(view==='all'||!['COMPLETED','CANCELLED'].includes(task.state))&&(!query.trim()||[task.goal,purposeLabels[task.purpose],...Object.values(task.references)].some(value=>value.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase())))&&(attention==='all'||attention==='user'&&['WAITING_USER','WAITING_APPROVAL'].includes(task.state)||attention==='agent'&&task.state==='WAITING_AGENT'||attention==='paused'&&task.state==='PAUSED'))
  const create=<Button kind="primary" onClick={()=>requestCollaboration(projectId,'CHECK','',true)}>新建协作任务</Button>
  return <><Heading title="Agent 协作" actions={state.data?.length?create:undefined}/>
    {Boolean(state.data?.length)&&<Segmented value={view} onValueChange={setView} label="协作任务范围" items={[{value:'active',label:'进行中的任务'},{value:'all',label:'全部任务'}]}/>}
    {Boolean(state.data?.length)&&<div className="jj-workspace-toolbar"><SearchField label="查找协作任务" placeholder="按目标或关联对象查找" value={query} onValueChange={setQuery}/><Choice className="jj-collaboration-filter" aria-label="待谁处理" value={attention} onValueChange={setAttention}><option value="all">全部处理状态</option><option value="user">需要我处理</option><option value="agent">等待 Agent</option><option value="paused">已暂停</option></Choice><span className="jj-small jj-muted">仅筛选最近读取的 {state.data?.length} 项任务{state.data?.length===40?'，更早任务可从原链接打开':''}</span></div>}
    {tasks.length?<section className="jj-collaboration-task-list" aria-label="协作任务">{tasks.map(task=><ActionLink presentation="row" key={task.task_id} href={'#'+scopedPath('/workspace?view=collaboration&task_id='+task.task_id,projectId)}><span><span className="jj-object-line"><strong>{task.goal}</strong><Badge tone={collaborationTone(task.state)}>{collaborationLabels[task.state]}</Badge></span><small>{purposeLabels[task.purpose]}{task.references.action_id?' · 已关联具体操作':''}{task.references.rule_id?' · 已关联权限要求':''} · {new Date(task.updated_at_us/1000).toLocaleString('zh-CN')}</small></span><ArrowRightOutlined aria-hidden="true"/></ActionLink>)}</section>:<Empty layout="section" title={state.data?.length?'当前没有进行中的任务':'还没有协作任务'} action={state.data?.length?<Button onClick={()=>setView('all')}>查看全部任务</Button>:create}>{state.data?.length?'已结束的任务保留在全部任务中。':'可以交给 Agent 准备材料、解读报告或协助处理问题。每项任务会保留目标、产物和你的决定。'}</Empty>}

  </>
}
