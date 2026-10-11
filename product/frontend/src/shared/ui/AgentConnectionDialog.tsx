// 选择客户端后自动配置；只按服务回执展示工具读取，未知写入结果只回读。
import { Alert, Button, Modal, Select } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { agentClients, agentConnectionsApi, type AgentClient, type AgentConnection } from '../../api/system/mcp'
import { configurationFailed as hasConfigurationFailure, notifyAgentAccessChanged, reusableConnection } from '../runtime/agentConnectionState'
import './agent-connection.css'

export function AgentConnectionDialog({open,onClose,onConnected}:{open:boolean;onClose:()=>void;onConnected?:()=>void}) {
  const [client,setClient]=useState<AgentClient>()
  const [value,setValue]=useState<AgentConnection>()
  const [profile,setProfile]=useState<string>()
  const [busy,setBusy]=useState(false)
  const [uncertain,setUncertain]=useState(false)
  const [error,setError]=useState<string>()
  const [reading,setReading]=useState(false)
  const [readMs,setReadMs]=useState<number>()
  const pendingRead=useRef<number | undefined>(undefined),lastFact=useRef('')
  const generation=useRef(0),callback=useRef(onConnected),reported=useRef(false)
  callback.current=onConnected
  useEffect(()=>{generation.current++;setClient(undefined);setValue(undefined);setProfile(undefined);setBusy(false);setUncertain(false);setError(undefined);setReading(false);setReadMs(undefined);lastFact.current='';reported.current=false;return()=>{generation.current++}},[open])
  const accept=(next:AgentConnection)=>{setValue(previous=>previous?.client===next.client?{...previous,...next}:next);setError(undefined);const fact=`${next.client}:${next.state}:${next.code}`;if(lastFact.current!==fact){lastFact.current=fact;notifyAgentAccessChanged()}if(['CONNECTED','TOOLS_READ','REQUEST_ACCEPTED'].includes(next.state)&&!reported.current){reported.current=true;callback.current?.()}}
  const read=async()=>{
    if(!client||pendingRead.current===generation.current)return
    const epoch=generation.current
    pendingRead.current=epoch;setReading(true);const started=performance.now()
    try{const next=await agentConnectionsApi.status(client);if(epoch===generation.current){accept(next);setUncertain(false)}}
    catch{if(epoch===generation.current)setError('无法联系界鉴服务或读取回执。请确认界鉴仍在运行，再重新检测；不会重复写入配置。')}
    finally{if(pendingRead.current===epoch)pendingRead.current=undefined;if(epoch===generation.current){setReading(false);setReadMs(Math.round(performance.now()-started))}}
  }
  useEffect(()=>{
    if(!open||!client||busy||(!uncertain&&!['AWAITING_CLIENT','STARTED','CONNECTED','TOOLS_READ','REQUEST_ACCEPTED','DISCONNECTED'].includes(value?.state??'')&&!['SERVICE_UNAVAILABLE','SESSION_EXPIRED','CONNECT_TIMEOUT','RESPONSE_TIMEOUT'].includes(value?.code??'')))return
    let active=true,pending=false
    const timer=window.setInterval(()=>{if(!active||pending||document.visibilityState==='hidden')return;pending=true;void read().finally(()=>{pending=false})},2000)
    return()=>{active=false;window.clearInterval(timer)}
  },[open,client,busy,uncertain,value?.state,value?.code])
  const install=async(key:AgentClient,reconfigure=false)=>{
    if(busy||uncertain)return
    const epoch=++generation.current;setClient(key);setBusy(true);setValue(undefined);setError(undefined);reported.current=false
    // 重进对话框先读已有连接，不能为显示状态而重装、作废正在使用的回执。
    let writing=false
    try{
      if(!reconfigure){
        const existing=await agentConnectionsApi.status(key)
        if(epoch!==generation.current)return
        if(existing.state!=='NOT_CONFIGURED'){accept(existing);return}
      }
      writing=true
      const next=await agentConnectionsApi.connect(key,profile);if(epoch===generation.current)accept(next)
    }
    catch{if(epoch===generation.current){setUncertain(writing);setError(writing?'配置操作的回执尚未确认，先检测当前状态，不重复提交。':'无法联系界鉴服务或读取已有连接。请确认界鉴仍在运行，再重新检测。')}}
    finally{if(epoch===generation.current)setBusy(false)}
  }
  const reset=()=>{generation.current++;setClient(undefined);setValue(undefined);setProfile(undefined);setError(undefined);setUncertain(false);setBusy(false);setReading(false);setReadMs(undefined)}
  const configurationFailed=hasConfigurationFailure(value)
  const usable=value?.state==='CONNECTED'||value?.state==='TOOLS_READ'||value?.state==='REQUEST_ACCEPTED'
  const configured=Boolean(value&&reusableConnection(value))
  const stage=busy||configurationFailed?0:['TOOLS_READ','REQUEST_ACCEPTED','STARTED'].includes(value?.state??'')?2:1
  return <Modal open={open} onCancel={onClose} footer={null} width={800} title="连接 Agent" destroyOnHidden>
    <div className="agent-connect-dialog">
      {!client?<><h2>你正在使用哪个客户端？</h2><p>选择后自动准备配置；需要在客户端确认时，会在这里提示。</p>
        <div className="agent-client-grid">{agentClients.map(item=><Button key={item.key} onClick={()=>void install(item.key)}><strong>{item.name}</strong><span>{item.description}</span></Button>)}</div>
        <p className="agent-connect-note">无需复制凭据或编辑配置。已有界鉴条目将连接当前实例，其他服务保持原样。</p>
      </>:<><div className="agent-connect-heading"><h2>{agentClients.find(item=>item.key===client)?.name}</h2><Button disabled={busy||uncertain} onClick={reset}>返回选择</Button></div>
        <ol className="agent-connect-stages" aria-label="连接步骤">{['自动配置',usable?'连接已确认':'客户端确认','读取工具'].map((label,index)=><li key={index} data-complete={index<stage} aria-current={stage===index?'step':undefined}><span aria-hidden/>{index+1} · {label}</li>)}</ol>
        {busy?<p role="status">正在核对客户端并准备本机连接…</p>:value&&<Alert showIcon type={usable?'success':value.state==='FAILED'?'error':'info'} message={value.state==='CONNECTED'?'MCP 连接已确认':value.state==='REQUEST_ACCEPTED'?'客户端已调用工具':value.state==='TOOLS_READ'?'客户端已读取工具':value.state==='FAILED'?'连接异常':configured?'配置已保存，可复用':'等待客户端确认'} description={value.message}/>}
        {error&&<Alert type="warning" showIcon message={error}/>}
        {value?.code==='PROFILE_REQUIRED'&&<label className="agent-profile-choice">DSH 配置档<Select aria-label="DSH 配置档" value={profile} onChange={setProfile} options={value.profiles.map(name=>({label:name,value:name}))}/></label>}
        {value?.config_path&&<details><summary>查看配置位置</summary><p className="agent-config-path">{value.config_path}</p></details>}
        <p className="agent-connect-note">配置只需准备一次。界鉴重启后，已加载配置的客户端可继续使用；首次加载仍需客户端确认。项目临时授权需重新确认。</p>
        {readMs!==undefined&&<p className="agent-connect-note" role="status">已检测，本次读取用时 {readMs} 毫秒。检测只读取状态，不会触发客户端调用。</p>}
        <div className="agent-connect-actions">{!busy&&<>
          {usable?<Button type="primary" onClick={onClose}>返回当前工作</Button>:<>
            <Button loading={reading} onClick={()=>void read()}>重新检测</Button>
            {value?.open_url?.startsWith('trae-cn://trae.ai-ide/mcp-import?')&&<Button type="primary" href={value.open_url}>在 TRAE 中确认</Button>}
            {!uncertain&&(configurationFailed||value?.state==='NOT_CONFIGURED')&&<Button type="primary" disabled={reading||value?.code==='PROFILE_REQUIRED'&&!profile} onClick={()=>void install(client,true)}>{value?.code==='CONFIG_UPDATE_REQUIRED'?'更新连接配置':'重新连接'}</Button>}
            {configured&&!uncertain&&<Button type="primary" onClick={onClose}>返回当前工作</Button>}
          </>}
        </>}</div>
      </>}
    </div>
  </Modal>
}
