// 本机连接与项目授权：客户端安装由连接对话框处理，操作权限仍由人逐应用确认。
import { Alert, Button, Modal, Radio } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
import { mcpAccessApi, type MCPAccessLevel, type MCPAccessView } from '../../api/system/mcp'
import type { ApiError } from '../../api/http'
import { EditorialHeader } from '../../shared/ui/Editorial'
import { AgentConnectionDialog } from '../../shared/ui/AgentConnectionDialog'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { agentAccessChanged, notifyAgentAccessChanged } from '../../shared/runtime/agentConnectionState'
import './connections.css'

type ProjectOption={project_id:string;name?:string}
const levels:Record<MCPAccessLevel,string>={READ:'只查看',PREPARE:'协助整理',EXECUTE:'执行已确认任务'}
export function MCPAccessCard({open,projects,onError,onStatusChange,sourceProjectId,projectListState='ready',onRefreshProjects}:{open:boolean;projects:ProjectOption[];onError:(error:ApiError)=>void;onStatusChange?:(view:MCPAccessView)=>void;sourceProjectId?:string;projectListState?:'loading'|'ready'|'failed';onRefreshProjects?:()=>void}){
  const [view,setView]=useState<MCPAccessView|null>(null),[connect,setConnect]=useState(false),[manage,setManage]=useState(false),[busy,setBusy]=useState(false),[forget,setForget]=useState(false)
  const [grant,setGrant]=useState<ProjectOption>(),[level,setLevel]=useState<MCPAccessLevel>('READ')
  const active=useRef(open),epoch=useRef(0);active.current=open
  useEffect(()=>{epoch.current++;if(!open){setView(null);setConnect(false);setManage(false);setGrant(undefined);setBusy(false)}},[open])
  const read=useCallback(async()=>{const stamp=epoch.current;try{const next=await mcpAccessApi.status();if(active.current&&stamp===epoch.current){setView(next);onStatusChange?.(next)}}catch(error){if(active.current&&stamp===epoch.current)onError(error as ApiError)}},[onError,onStatusChange])
  useLiveRead(open?'agent-access':undefined,read,3000)
  useEffect(()=>{if(!open)return;const refresh=()=>{void read()};window.addEventListener(agentAccessChanged,refresh);return()=>window.removeEventListener(agentAccessChanged,refresh)},[open,read])
  const update=async(operation:()=>Promise<MCPAccessView>)=>{const stamp=epoch.current;setBusy(true);try{const next=await operation();if(active.current&&stamp===epoch.current){setView(next);onStatusChange?.(next);setGrant(undefined);setForget(false);notifyAgentAccessChanged()}}catch(error){if(active.current&&stamp===epoch.current)onError(error as ApiError)}finally{if(active.current&&stamp===epoch.current)setBusy(false)}}
  const paused=view?.connection_state==='PAUSED'
  const connected=view?.connection_state==='CONNECTED'
  const displayed=sourceProjectId?[...projects].sort((a,b)=>Number(b.project_id===sourceProjectId)-Number(a.project_id===sourceProjectId)):projects
  return <div className="mcp-access-shell connection-page">
    <EditorialHeader eyebrow="开发工具连接" title="连接与授权"><p className="editorial-muted">连接原来的 Agent，在你允许的范围内整理规则、登记修改和读取结果。</p></EditorialHeader>
    <section className="connection-status" aria-label="连接事实"><div><h3>{!view?'正在读取连接状态':paused?'连接已暂停':connected?'MCP 连接已确认':view.connection_state==='CREDENTIAL_REJECTED'?'客户端身份核验失败':view.paired?'连接凭据已保存':'连接你的 Agent'}</h3><p>{connected?`${view?.client_name||'客户端'} 已完成 MCP 协议通信；无需额外调用业务工具来确认连接。`:paused?'恢复后可继续使用原配置，项目临时授权需重新确认。':view?.connection_state==='CREDENTIAL_REJECTED'?'请查看所选客户端的具体原因，再处理连接。':view?.paired?'尚未收到本次服务的客户端请求。已配置的客户端可继续调用；需要时可查看连接状态。':'点击连接后选择客户端，界鉴自动准备配置；需要客户端确认时会提示。'}</p></div><Button type="primary" disabled={!view} onClick={()=>setConnect(true)}>连接 Agent</Button></section>
    {paused&&<Alert showIcon type="info" message="当前暂停接受所有客户端连接" action={<Button loading={busy} onClick={()=>void update(mcpAccessApi.resume)}>恢复连接</Button>}/>}
    <section aria-label="应用授权"><div className="connection-project-heading"><h3>本次允许的操作</h3>{onRefreshProjects&&<Button type="link" onClick={onRefreshProjects}>刷新应用列表</Button>}</div><p className="editorial-muted">默认只查看。提升范围仅对所选应用和本次打开界鉴期间有效，正式规则仍由你审阅批准。</p>
      {projectListState==='loading'&&!displayed.length&&<p role="status">正在读取可授权的应用…</p>}
      {projectListState==='failed'&&<Alert showIcon type="warning" message="应用列表读取失败，请刷新应用列表后重试。"/>}
      {projectListState==='ready'&&!displayed.length&&<div className="connection-project-empty"><p>尚未接入应用。接入后会在这里显示应用及可调整的操作范围。</p><Button href="#/application?new=1">接入应用</Button></div>}
      {displayed.map(project=><div className="connection-project-context" key={project.project_id}><div><h3>{project.name||project.project_id}</h3><p>{levels[view?.project_grants.find(item=>item.project_id===project.project_id)?.level??'READ']}</p></div><Button disabled={!view?.accepting_connections} onClick={()=>{setLevel(view?.project_grants.find(item=>item.project_id===project.project_id)?.level??'READ');setGrant(project)}}>调整这次允许范围</Button></div>)}
    </section>
    {view?.paired&&<><Button type="link" aria-expanded={manage} onClick={()=>setManage(!manage)}>管理本机连接</Button>{manage&&<section className="connection-management-content"><p>暂停或删除会影响所有客户端，项目临时授权也会清除。</p><div className="connection-management-actions"><Button danger disabled={busy} onClick={()=>setForget(true)}>删除连接凭据</Button><Button loading={busy} onClick={()=>void update(paused?mcpAccessApi.resume:mcpAccessApi.pause)}>{paused?'恢复接受连接':'暂停本次连接'}</Button></div></section>}</>}
    <AgentConnectionDialog open={connect} onClose={()=>{setConnect(false);void read()}} onConnected={()=>void read()}/>
    <Modal title="删除本机连接凭据？" open={forget} onCancel={()=>setForget(false)} onOk={()=>void update(mcpAccessApi.forget)} confirmLoading={busy} okText="删除" okButtonProps={{danger:true}} cancelText="取消"><p>所有客户端都会失去访问权限。之后可以重新点击“连接 Agent”。</p></Modal>
    <Modal title="这次允许 Agent 做到哪一步？" open={Boolean(grant)} onCancel={()=>setGrant(undefined)} confirmLoading={busy} okText="保存这次允许范围" cancelText="取消" onOk={()=>grant&&void update(()=>mcpAccessApi.setProjectAccess(grant.project_id,level))}>
      <p>{grant?.name||grant?.project_id}</p><Radio.Group className="mcp-access-levels" value={level} onChange={event=>setLevel(event.target.value)} options={(['READ','PREPARE','EXECUTE'] as const).map(value=>({label:levels[value],value}))}/>
      <p>协助整理可以保存候选和登记变化；执行范围允许运行已确认任务。Agent 不能批准规则、采用来源或扩大权限。</p>
    </Modal>
  </div>
}
export default MCPAccessCard
