// 固定当前业务引用后交给原Agent；连接、复制和迟到响应保护共用已有入口。
import {request} from '../../api/http'
import {AgentAssistEntry} from './AgentAssistEntry'

type Stage='RULES'|'MATERIALS'|'RECORDING'|'RESULTS'|'REPAIR'
export function AgentWorkflowEntry({projectId,stage,recordingId,runId,caseId,onNavigate}: {
  projectId:string;stage:Stage;recordingId?:string;runId?:string;caseId?:string;onNavigate?:(path:string)=>void
}){
  const query=new URLSearchParams({stage})
  if(recordingId)query.set('recording_id',recordingId)
  if(runId)query.set('run_id',runId)
  if(caseId)query.set('case_id',caseId)
  return <AgentAssistEntry projectId={projectId} contextKey={query.toString()} title="请原来的 Agent 协助这一步"
    description="复制请求到原来的对话。Agent 会通过界鉴读取当前记录，解释缺口或整理候选，再由你确认下一步。"
    requiredLevel={stage==='RULES'||stage==='MATERIALS'?'PREPARE':'READ'} returnTo={window.location.hash.slice(1)||'/workspace'}
    onNavigate={onNavigate??(path=>{window.location.hash=path})}
    loadContext={async()=>{
      const value=await request<{project_id:string;context_id:string;next_step:string}>(`/api/projects/${encodeURIComponent(projectId)}/agent-context?${query}`)
      return {projectId:value.project_id,revisionKey:value.context_id,requestText:[
        '请通过界鉴 MCP 的 jiejian_agent_context 读取下面这项任务，按返回的工具继续。',
        JSON.stringify({project_id:projectId,stage,recording_id:recordingId,run_id:runId,case_id:caseId}),
        value.next_step,'读取界鉴的实际记录后再解释；不要把复制请求当作已经完成，不自动批准或启动新的检查。'].join('\n')}
    }}/>
}
