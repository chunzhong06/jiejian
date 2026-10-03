// 一次登记本地修改；只保存非秘密的操作定位，回执不明时回读原键，不重建请求试探。
import { Alert, Button, Form, Input, Select, Spin } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { sourceChangesApi, type RegistrationPreview } from '../../../api/changes/sourceChanges'
import { developmentApi, newOperationId } from '../../../api/changes/development'
import { ApiError } from '../../../api/http'
import { repairLabels, repairReference, type ProjectRepair } from '../../../api/checks/repairs'
import { clearPendingOperation, readPendingOperation, savePendingOperation } from '../pendingOperations'

export function ChangeRegistration({ projectId, repair, requestedRepair, onSaved, onCancel, onError }: { projectId: string; repair: ProjectRepair | null; requestedRepair?: string | null; onSaved: (change: string) => Promise<void>; onCancel: () => void; onError: (error: ApiError) => void }) {
  const legacy = useRef(Boolean(readPendingOperation(projectId,'delivery')))
  const scope = legacy.current ? 'delivery' : 'registration'
  const pending = useRef(readPendingOperation(projectId,scope))
  const [uncertain,setUncertain] = useState(Boolean(pending.current)), [busy,setBusy] = useState(false), [message,setMessage] = useState(''), [retryReady,setRetryReady] = useState(false)
  const [preview,setPreview] = useState<RegistrationPreview | null>(null), [failed,setFailed] = useState(false)
  const [reference,setReference] = useState<string | undefined>(requestedRepair ?? undefined)
  const [form] = Form.useForm<{reason?:string;paths?:string}>()
  const alive = useRef(true), locked = useRef(false)
  const load = async () => {
    setFailed(false)
    try { const value = await sourceChangesApi.registrationPreview(projectId)
      if(value.project_id !== projectId) throw new ApiError('STATE_PRECONDITION','登记范围所属应用不一致。')
      if(alive.current) setPreview(value)
    } catch(error) { if(alive.current){setPreview(null);setFailed(true);onError(error as ApiError)} }
  }
  useEffect(() => { alive.current=true;void load();return()=>{alive.current=false} },[projectId])
  const query = async () => {
    if(!pending.current || locked.current)return
    locked.current=true;setBusy(true)
    try {const result=await developmentApi.receipt(projectId,'DELIVER',pending.current.operation_id)
      if(!alive.current)return
      if(!result){setRetryReady(!legacy.current);setMessage(legacy.current?'尚未查到旧版回执，请用原客户端查询或恢复原操作。':'尚未查到成功回执。可查询，或填写原登记内容后用同一操作重试；不会另建记录。');return}
      if(result.project_id!==projectId || result.operation_id!==pending.current.operation_id || !result.change_id)throw new ApiError('STATE_PRECONDITION','登记回执关联不一致。')
      clearPendingOperation(projectId,scope,pending.current.operation_id);pending.current=null;setUncertain(false)
      setMessage('已找回本次登记，无需再次填写。');await onSaved(result.change_id)
    }catch(error){if(alive.current)onError(error as ApiError)}finally{locked.current=false;if(alive.current)setBusy(false)}
  }
  const submit = async (values:{reason?:string;paths?:string}) => {
    if(locked.current || (uncertain&&!retryReady) || !preview)return
    const task=reference?repair?.tasks.find(item=>item.contract.repair_fingerprint===reference && item.status!=='STALE'):undefined
    if(reference&&!task){onError(new ApiError('STATE_PRECONDITION','原题引用不可用，请从原问题重新进入。'));return}
    const paths=(values.paths??'').split(/\r?\n/).map(item=>item.trim()).filter(Boolean)
    if(paths.length>128){onError(new ApiError('INPUT_INVALID','最多填写 128 个相对路径。'));return}
    locked.current=true;setBusy(true)
    // 已查不到回执时只允许重放原键；服务端继续校验指纹及原请求内容。
    const operation=pending.current??{kind:'DELIVER',operation_id:newOperationId(),expected_registration_fingerprint:preview.fingerprint}
    try {
      if(!savePendingOperation(projectId,'registration',operation))throw new ApiError('BROWSER_STORAGE_UNAVAILABLE','无法保存操作定位，请允许本页会话存储后重试。')
      pending.current=operation
      const result=await sourceChangesApi.register(projectId,{operation_id:operation.operation_id,expected_registration_fingerprint:operation.expected_registration_fingerprint!,reason:values.reason?.trim()||'本地源码修改',claimed_paths:paths,repair_reference:task?repairReference(task.contract):null})
      if(!alive.current)return
      if(result.project_id!==projectId || result.operation_id!==operation.operation_id || !result.change_id)throw new ApiError('STATE_PRECONDITION','登记回执关联不一致。')
      clearPendingOperation(projectId,'registration',operation.operation_id);pending.current=null;form.resetFields();setMessage('修改已登记。检查结论将单独形成。');await onSaved(result.change_id)
    }catch(error){if(alive.current){
      // 明确的写入前范围拒绝可以重新预览；网络和写后同步失败不能创建另一个操作键。
      if(error instanceof ApiError && error.code==='STATE_PRECONDITION' && error.message.includes('登记范围已变化')){clearPendingOperation(projectId,'registration',operation.operation_id);pending.current=null;await load()}
      setRetryReady(false);setUncertain(Boolean(pending.current));onError(error as ApiError)
    }}finally{locked.current=false;if(alive.current)setBusy(false)}
  }
  return <section className="light-registration" aria-label="登记本地修改"><header><h2>登记本地修改</h2><p>开发需求继续在原客户端讨论。这里只记录源码变化及沿用的权限范围。</p></header>
    {uncertain&&<Alert type="warning" showIcon message="上次登记回执尚未确认" description={legacy.current?'发现旧版登记的未确认操作，先读取原回执。':'先查询原操作，不重新登记。'} action={<Button loading={busy} onClick={()=>void query()}>查询登记回执</Button>}/>}
    {message&&<p role="status">{message}</p>}{!preview&&!failed&&<Spin aria-label="正在核对登记范围"/>}{failed&&<Button onClick={()=>void load()}>重新读取登记范围</Button>}
    {preview&&<p className="light-meta">沿用权限版本 {preview.policy_epoch} · {preview.permission_count} 条已确认要求</p>}
    <Form form={form} layout="vertical" onFinish={submit} disabled={busy||(uncertain&&!retryReady)||!preview||failed}>
      <Form.Item name="reason" label="修改说明（选填）" rules={[{max:512}]}><Input.TextArea maxLength={512} autoSize={{minRows:2,maxRows:5}}/></Form.Item>
      {!!repair?.tasks.length&&<Form.Item label="关联原问题（可选）"><Select allowClear value={reference} onChange={setReference} options={repair.tasks.filter(item=>item.status!=='STALE').map((item,i)=>({value:item.contract.repair_fingerprint,label:`原问题 ${i+1} · ${repairLabels[item.status]}`}))}/></Form.Item>}
      <details><summary>补充涉及文件（可选）</summary><Form.Item name="paths" label="每行一个相对路径"><Input.TextArea maxLength={32768} autoSize={{minRows:2,maxRows:5}}/></Form.Item></details>
      <div className="confirmation-actions"><Button onClick={onCancel}>返回修改记录</Button><Button type="primary" htmlType="submit" loading={busy}>{uncertain?'重试原登记':'登记并核对实际变化'}</Button></div>
    </Form>
  </section>
}
