// 应用运行属于环境准备；预览、启动回执和当前进程分开，不把启动成功表示为安全通过。
import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Checkbox, Input, InputNumber, Spin } from 'antd'
import {projectsApi,type ApplicationUnderstandingDto} from '../../api/applications/projects'
import { controlledRuntimeApi as api, type RuntimePreview, type RuntimeState } from '../../api/applications/controlledRuntime'
import { ApiError } from '../../api/http'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import './controlled-runtime.css'

function storedOperation(key:string) {
  try { const value=sessionStorage.getItem(key);return value && /^[a-f0-9]{32}$/.test(value)?value:null }
  catch {return null}
}

export function ApplicationRuntimeSettings({projectId,onNavigate}:{projectId:string;onNavigate:(path:string)=>void}) {
  const [understanding,setUnderstanding]=useState<ApplicationUnderstandingDto|null>(null)
  const [error,setError]=useState(false),[revision,setRevision]=useState(0)
  useEffect(()=>{
    let current=true;setUnderstanding(null);setError(false)
    void projectsApi.understanding(projectId).then(value=>{
      if(current) { if(value.project_id!==projectId)throw new Error('project mismatch');setUnderstanding(value) }
    }).catch(()=>{if(current)setError(true)})
    return ()=>{current=false}
  },[projectId,revision])
  if(error)return <Alert type="warning" message="暂时无法读取应用运行配置" action={<Button onClick={()=>setRevision(value=>value+1)}>重新读取</Button>}/>
  if(!understanding)return <Spin/>
  return <div className="controlled-runtime-settings"><ControlledRuntimePanel key={projectId} projectId={projectId}
    revision={understanding.revision} sourceAuthorized={understanding.source_analysis_authorized}
    onChanged={()=>{void projectsApi.understanding(projectId).then(value=>{if(value.project_id===projectId)setUnderstanding(value)}).catch(()=>setError(true))}}
    onEndpoint={()=>{}}/><Button type="link" onClick={()=>onNavigate('/application')}>核对应用访问地址</Button></div>
}

export function ControlledRuntimePanel({ projectId, revision, sourceAuthorized, onChanged, onEndpoint }: {
  projectId:string; revision:number; sourceAuthorized:boolean; onChanged:()=>void; onEndpoint:(endpoint:string)=>void
}) {
  const [entry,setEntry]=useState('app.mjs')
  const [port,setPort]=useState<number|null>(3000)
  const [consent,setConsent]=useState(false)
  const [preview,setPreview]=useState<RuntimePreview|null>(null)
  const [state,setState]=useState<RuntimeState|null>(null)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const key=`jiejian-runtime-operation:${projectId}`
  const [pending,setPending]=useState(()=>storedOperation(key))
  const current=useRef(projectId); current.current=projectId
  const requestSequence=useRef(0)
  const restoredConfiguration=useRef(false)
  const isActive=(id:string,sequence:number)=>current.current===id && requestSequence.current===sequence
  const fail=(value:unknown)=>setError(value instanceof ApiError?value.message:'暂时无法读取运行状态，请查询原操作。')

  async function refresh() {
    const project=projectId,sequence=++requestSequence.current
    setBusy(true);setError('')
    try {
      if(pending) {
        const receipt=await api.operation(project,pending)
        if(!isActive(project,sequence))return
        if(!receipt) { setError('原操作尚未查到回执。请稍后继续查询，避免重复启动。'); return }
        if(receipt.project_id!==project || receipt.operation_id!==pending)throw new Error('receipt mismatch')
        sessionStorage.removeItem(key);setPending(null)
      }
      const result=await api.state(project)
      if(!isActive(project,sequence))return
      if(result.project_id!==project)throw new Error('project mismatch')
      setState(result)
      if(!restoredConfiguration.current) {
        restoredConfiguration.current=true
        if(result.configuration) {setEntry(result.configuration.entry);setPort(result.configuration.port)}
      }
      if(result.running && result.operation?.receipt) onEndpoint(`http://127.0.0.1:${result.operation.receipt.reference.port}`)
    } catch(value) {if(isActive(project,sequence))fail(value)}
    finally {if(isActive(project,sequence))setBusy(false)}
  }
  useEffect(()=>{
    void refresh()
    return ()=>{requestSequence.current++}
    // 父组件按项目key重建；刷新只读取，不重新提交已保存操作。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  },[projectId])

  async function readPreview() {
    if(port===null)return
    const project=projectId,sequence=++requestSequence.current
    setBusy(true);setError('');setPreview(null)
    try {
      const result=await api.preview(project,{entry:entry.trim(),port,revision,consent_source_read:sourceAuthorized||consent})
      if(!isActive(project,sequence))return
      if(result.project_id!==project)throw new Error('project mismatch')
      setPreview(result);onChanged()
    } catch(value){if(isActive(project,sequence)){fail(value);onChanged()}}
    finally {if(isActive(project,sequence))setBusy(false)}
  }
  async function start() {
    if(!preview || pending)return
    const project=projectId,sequence=++requestSequence.current
    const operation=crypto.randomUUID().replaceAll('-','')
    // 发出写请求之前保存操作键，刷新或连接中断后仍只能查询这个操作。
    try {sessionStorage.setItem(key,operation)}
    catch {setError('浏览器无法保留操作定位。请允许会话存储后再启动。');return}
    setPending(operation);setBusy(true);setError('')
    try {
      const result=await api.start(project,{entry:preview.entry,port:preview.port,revision:preview.revision,
        preview_fingerprint:preview.preview_fingerprint,operation_id:operation,consent_execute:true})
      if(!isActive(project,sequence))return
      if(result.project_id!==project || result.operation_id!==operation)throw new Error('receipt mismatch')
      sessionStorage.removeItem(key);setPending(null);setPreview(null)
      setState({project_id:project,operation:result,running:false,source_matches:false})
    } catch(value){if(isActive(project,sequence)){
      // 明确的前置拒绝没有提交加载；网络或持久化未知仍保留原键并只读查询。
      if(value instanceof ApiError && ['STATE_PRECONDITION','SELF_TARGET_FORBIDDEN','REQUEST_VALIDATION_FAILED'].includes(value.code)) {
        sessionStorage.removeItem(key);setPending(null);setPreview(null);onChanged()
      }
      fail(value)
    }}
    finally {if(isActive(project,sequence))setBusy(false)}
  }
  async function stop() {
    if(!state?.operation)return
    const project=projectId,sequence=++requestSequence.current
    setBusy(true);setError('')
    try {
      const result=await api.stop(project,state.operation.instance_id)
      if(!isActive(project,sequence))return
      if(result.project_id!==project)throw new Error('project mismatch')
      setState(result);onChanged()
    } catch(value){if(isActive(project,sequence))fail(value)}
    finally {if(isActive(project,sequence))setBusy(false)}
  }
  async function cancelStart() {
    if(!state?.operation)return
    const project=projectId,sequence=++requestSequence.current
    setBusy(true);setError('')
    try {
      const result=await api.cancel(project,state.operation.operation_id)
      if(!isActive(project,sequence))return
      if(result.project_id!==project || result.operation_id!==state.operation.operation_id)throw new Error('operation mismatch')
      setState({...state,operation:result})
    } catch(value){if(isActive(project,sequence))fail(value)}
    finally {if(isActive(project,sequence))setBusy(false)}
  }
  const queued=state?.operation && ['PENDING','RUNNING','RETRY_WAIT'].includes(state.operation.state)
  return <section className="controlled-runtime" aria-label="由界鉴启动本地应用">
    <header><div><h3>由界鉴启动本地应用</h3><p>保留一份固定源码用于核对，关闭界鉴时停止本次运行。</p></div>
      <StatusBadge kind="lifecycle" tone={state?.running?'info':queued?'warning':'neutral'}>{pending?'回执待查询':state?.running?'正在运行':queued?'正在启动':state?.operation?.state==='FAILED'?'启动失败':'尚未运行'}</StatusBadge></header>
    {error && <Alert type="warning" showIcon message={error}/>}
    <p className="controlled-runtime-scope">支持无外部依赖的 Node ESM 应用。入口使用 .mjs，只加载静态相对模块；其他项目可继续使用已启动的本地地址。</p>
    <div className="controlled-runtime-fields"><label>入口文件<Input value={entry} disabled={busy||Boolean(queued)||Boolean(pending)} onChange={event=>{setEntry(event.target.value);setPreview(null)}} placeholder="app.mjs"/></label>
      <label>本地端口<InputNumber min={1024} max={65535} value={port} disabled={busy||Boolean(queued)||Boolean(pending)} onChange={value=>{setPort(value);setPreview(null)}}/></label></div>
    {!sourceAuthorized && <Checkbox checked={consent} disabled={busy} onChange={event=>setConsent(event.target.checked)}>允许只读当前源码，生成启动预览</Checkbox>}
    {preview && <div className="controlled-runtime-preview"><strong>将启动 {preview.entry}</strong><span>{preview.files.length} 个文件 · http://127.0.0.1:{preview.port}</span><p>应用可写入本项目的独立数据目录。预览尚未执行任何代码。</p></div>}
    {state?.running && !state.source_matches && <Alert type="warning" showIcon message="本地源码已变化，当前运行仍对应上一次启动副本。"/>}
    {state?.running && state.operation?.receipt && <p>当前运行地址：http://127.0.0.1:{state.operation.receipt.reference.port}</p>}
    <footer><span>{state?.operation?.state==='SUCCEEDED' && !state.running?'已保留上次启动回执；当前没有确认到仍运行的实例。':'运行状态不代表权限检查结果。'}</span><div className="confirmation-actions">
      {queued && <Button disabled={busy} onClick={()=>void cancelStart()}>取消本次启动</Button>}
      {state?.running && <Button disabled={busy||Boolean(queued)} onClick={()=>void stop()}>停止本次运行</Button>}
      <Button loading={busy} onClick={()=>void refresh()}>{pending?'查询原操作结果':'刷新运行状态'}</Button>
      {!pending && !queued && (preview?<Button type="primary" disabled={busy} onClick={()=>void start()}>确认启动应用</Button>:<Button type="primary" disabled={busy||!entry.trim()||port===null||(!sourceAuthorized&&!consent)} onClick={()=>void readPreview()}>预览启动</Button>)}
    </div></footer>
  </section>
}
