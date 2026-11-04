import {useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import {collaborationApi,collaborationLabels,collaborationTone,purposeLabels} from '../../entities/runtime/api/collaboration'
import {requestCollaboration} from '../../entities/runtime/model/handoff'
import {useRead} from '../../shared/lib/useRead'
import {scopedPath} from '../../shared/lib/navigation'
import {Heading} from '../../shared/ui/layout'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Tabs} from '../../shared/ui/Tabs'
import {Badge,Empty,Loading,PageError} from '../../shared/ui/feedback'
import './collaboration.css'

export function CollaborationHub({projectId}:{projectId:string}){
  const state=useRead('collaboration-tasks:'+projectId,signal=>collaborationApi.list(projectId,signal))
  const [view,setView]=useState('active')
  if(state.loading)return <Loading page/>
  if(state.error)return <PageError title="Agent 协作" error={state.error}/>
  const tasks=(state.data??[]).filter(task=>view==='all'||!['COMPLETED','CANCELLED'].includes(task.state))
  return <><Heading title="Agent 协作" children="查看当前目标、接续已有工作，或建立独立任务。" actions={<Button kind="primary" onClick={()=>requestCollaboration(projectId,'CHECK','',true)}>新建协作任务</Button>}/>
    <Tabs value={view} onValueChange={setView} label="协作任务范围" items={[{value:'active',label:'进行中的任务'},{value:'all',label:'全部任务'}]}/>
    {tasks.length?<section className="jj-collaboration-task-list" aria-label="协作任务">{tasks.map(task=><article key={task.task_id}><div><div className="jj-inline-actions"><strong>{task.goal}</strong><Badge tone={collaborationTone(task.state)}>{collaborationLabels[task.state]}</Badge></div><p>{purposeLabels[task.purpose]} · {new Date(task.updated_at_us/1000).toLocaleString('zh-CN')}</p></div><ActionLink href={'#'+scopedPath('/workspace?view=collaboration&task_id='+task.task_id,projectId)}>查看任务<ArrowRightOutlined aria-hidden="true"/></ActionLink></article>)}</section>:<Empty title={view==='active'?'没有进行中的协作任务':'还没有协作任务'}/>}
  </>
}
