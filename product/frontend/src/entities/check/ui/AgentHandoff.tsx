import {useRef,useState} from 'react'
import type {RepairReference} from '../api/repairs'
import {collaborationApi} from '../../runtime/api/collaboration'
import {Button} from '../../../shared/ui/actions'
import {ErrorNote} from '../../../shared/ui/feedback'
import {Dialog} from '../../../shared/ui/Dialog'
import {go,readRoute,returnDestination} from '../../../shared/lib/navigation'

export function AgentHandoff({projectId,runId,caseId,targets=[],repair=false,onClose}:{
  projectId:string;runId:string;caseId?:string|null;targets?:RepairReference[];repair?:boolean;onClose:()=>void
}){
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>()
  // 重试保留本次报告的交接身份；入口切换不使用“最近一次报告”替代原引用。
  const operation=useRef(crypto.randomUUID().replaceAll('-',''))
  const start=async()=>{setBusy(true);setError(undefined);try{
    const references:Record<string,string>={run_id:runId}
    const route=readRoute(),origin=returnDestination(route.path+'?'+route.query)
    if(origin)references.return_to=origin
    if(caseId)references.case_id=caseId
    if(targets.length)references.repair_references=JSON.stringify(targets)
    const active=(await collaborationApi.list(projectId)).find(item=>!['COMPLETED','CANCELLED'].includes(item.state)&&(
      item.references.run_id===runId||item.operations.some(value=>value.result&&typeof value.result==='object'&&'run_id' in value.result&&value.result.run_id===runId)))
    const goal=repair?'修复这次发现的权限问题，并复验原问题和正常功能':'解读这份检查报告，说明实际结果、依据与下一步'
    const task=active?await collaborationApi.followup(projectId,active.task_id,goal,repair?'REPAIR':'UNDERSTAND',references,operation.current):await collaborationApi.create(projectId,goal,repair?'REPAIR':'UNDERSTAND',references,operation.current)
    onClose();go('/workspace?view=collaboration&task_id='+encodeURIComponent(task.task_id))
  }catch(value){setError(value)}finally{setBusy(false)}}
  return <Dialog title={repair?'协作处理这项权限问题':'协作解读当前报告'} onClose={onClose} actions={<><Button onClick={onClose}>取消</Button><Button kind="primary" busy={busy} onClick={()=>void start()}>进入协作任务</Button></>}>
    <p>{repair?'本次报告、原问题和正常功能要求会随任务保留。修改、运行和复验继续关联同一目标。':'任务会固定当前报告及所选记录，帮助你理解实际结果、证据缺口和下一步。'}</p>
    <p className="jj-small jj-muted">进入后选择本地 Agent 或已连接开发工具；需要你的决定时，在同一任务中确认。</p>
    {Boolean(error)&&<ErrorNote error={error}/>}
  </Dialog>
}
