import {useRef,useState} from 'react'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import CommentOutlined from '@ant-design/icons/CommentOutlined'
import {collaborationApi,collaborationLabels} from '../api/collaboration'
import {useRead} from '../../../shared/lib/useRead'
import {go} from '../../../shared/lib/navigation'
import {Button} from '../../../shared/ui/actions'
import {Dialog} from '../../../shared/ui/Dialog'
import {Field} from '../../../shared/ui/layout'
import {ErrorNote} from '../../../shared/ui/feedback'

export function CollaborationEntry({projectId,route,viewedTaskId}:{projectId:string;route:string;viewedTaskId?:string|null}){
  const state=useRead('collaboration:'+projectId,signal=>collaborationApi.current(projectId,signal),4000)
  const [open,setOpen]=useState(false),[goal,setGoal]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>()
  const [repair,setRepair]=useState(false)
  // 网络回执未知时继续使用同一请求，避免再次点击建立重复任务。
  const operation=useRef(crypto.randomUUID().replaceAll('-',''))
  const current=state.data
  const label=current?'继续协作':'开始协作'
  const visit=(id:string)=>go('/workspace?view=collaboration&task_id='+encodeURIComponent(id),projectId)
  const create=async()=>{setBusy(true);setError(undefined);try{const task=await collaborationApi.create(projectId,goal.trim(),repair?'CHECK_AND_REPAIR':'CHECK',{origin:route},operation.current);operation.current=crypto.randomUUID().replaceAll('-','');setOpen(false);state.reload();visit(task.task_id)}catch(value){setError(value)}finally{setBusy(false)}}
  return <>
    <Button kind="quiet" className="jj-toolbar-action jj-collaboration-entry" icon={<CommentOutlined aria-hidden="true"/>} aria-label={label} tip={current?`${current.goal}，${collaborationLabels[current.state]}`:label} aria-current={current&&current.task_id===viewedTaskId?'page':undefined} disabled={state.loading} onClick={()=>current?visit(current.task_id):setOpen(true)}><span className="jj-collaboration-entry-label">{label}</span></Button>
    {open&&<Dialog title="交代这次要完成的目标" onClose={()=>setOpen(false)} actions={<><Button onClick={()=>setOpen(false)}>取消</Button><Button kind="primary" busy={busy} disabled={!goal.trim()} onClick={()=>void create()}>建立任务<ArrowRightOutlined aria-hidden="true"/></Button></>}>
      <Field label="目标"><textarea rows={3} value={goal} onChange={event=>setGoal(event.target.value)} placeholder="例如：核对成员能否修改其他人的工单"/></Field>
      <label className="jj-checkbox"><input type="checkbox" checked={repair} onChange={event=>setRepair(event.target.checked)}/><span>同时修复本次发现的问题并复验</span></label>
      <p className="jj-small jj-muted">已有内容会继续保留。需要业务决定、登录或新增授权时，会在任务中请你处理。</p>{Boolean(error)&&<ErrorNote error={error}/>}
    </Dialog>}
  </>
}
