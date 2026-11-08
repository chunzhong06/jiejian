import {useState} from 'react'
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
  const [view,setView]=useState('active')
  if(state.loading)return <Loading page/>
  if(state.error)return <PageError title="Agent 协作" error={state.error}/>
  const tasks=(state.data??[]).filter(task=>view==='all'||!['COMPLETED','CANCELLED'].includes(task.state))
  return <><Heading title="Agent 协作" children="说明希望 Agent 完成的工作。建立任务后选择执行方式，需要补充业务含义或确认操作时，在同一任务中处理。" actions={<Button kind="primary" onClick={()=>requestCollaboration(projectId,'CHECK','',true)}>新建协作任务</Button>}/>
    <Segmented value={view} onValueChange={setView} label="协作任务范围" items={[{value:'active',label:'进行中的任务'},{value:'all',label:'全部任务'}]}/>
    {tasks.length?<section className="jj-collaboration-task-list" aria-label="协作任务">{tasks.map(task=><ActionLink presentation="row" key={task.task_id} href={'#'+scopedPath('/workspace?view=collaboration&task_id='+task.task_id,projectId)}><span><span className="jj-object-line"><strong>{task.goal}</strong><Badge tone={collaborationTone(task.state)}>{collaborationLabels[task.state]}</Badge></span><small>{purposeLabels[task.purpose]} · {new Date(task.updated_at_us/1000).toLocaleString('zh-CN')}</small></span><ArrowRightOutlined aria-hidden="true"/></ActionLink>)}</section>:<Empty title={state.data?.length?'当前没有进行中的任务':'先说明希望 Agent 完成的工作'}>{state.data?.length?'已结束的任务保留在“全部任务”中，也可以新建一个目标继续协作。':'例如整理检查材料或解读已发布报告。选择“新建协作任务”填写目标，再确认如何执行；权限规则与正式检查仍需你确认。'}</Empty>}

  </>
}
