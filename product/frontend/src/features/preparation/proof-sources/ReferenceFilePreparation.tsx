// 文件参照留在当前结果证明中；预览不执行，原操作未知时只读回执，项目/修订变化废弃旧预览。
import {useContext,useEffect,useRef,useState} from 'react'
import {Alert,Button,Checkbox,Modal,Radio,Select,Upload} from 'antd'
import {proofSourcesApi as api,type ProofContext,type ProofSource,type ProofOperationKind,type CaptureSelection,type CapturePlan,type CaptureStatus} from '../../../api/preparation/proofSources'
import {StatusBadge} from '../../../shared/ui/StatusBadge'
import {WorkPageVisible} from '../../../shared/runtime/visibility'

export function ReferenceFilePreparation({projectId,context,source,busy,pending,preferredAsset,captureId,onWrite,onRefresh}: {
  projectId:string;context:ProofContext;source:ProofSource;busy:boolean;pending:boolean;preferredAsset?:string;captureId?:string
  onWrite:(kind:ProofOperationKind,body:object,file?:File)=>Promise<void>;onRefresh:()=>Promise<unknown>
}) {
  const visible=useContext(WorkPageVisible)
  const [mode,setMode]=useState<'capture'|'upload'>('capture'),[file,setFile]=useState<File>()
  const [selected,setSelected]=useState(''),[permission,setPermission]=useState('')
  const [plan,setPlan]=useState<CapturePlan>(),[selection,setSelection]=useState<CaptureSelection>(),[confirmed,setConfirmed]=useState(false)
  const [reading,setReading]=useState(false),[issue,setIssue]=useState<string>(),[status,setStatus]=useState<CaptureStatus>()
  const [removal,setRemoval]=useState<string>()
  const scope=`${projectId}:${context.basis_id}:${source.source_id}:${source.revision}`
  const live=useRef(scope);live.current=scope
  useEffect(()=>{setPlan(undefined);setSelection(undefined);setFile(undefined);setConfirmed(false);setReading(false);setIssue(undefined);setStatus(undefined);setRemoval(undefined)},[scope])
  useEffect(()=>()=>{live.current=''},[])
  const config=source.config,action=context.actions.find(item=>item.action_id===config.action_id)
  const resource=context.resources.find(item=>item.resource_binding_id===config.resource_binding_id)
  const account=(id?:string|null)=>context.identities.find(item=>item.identity_id===id)
  const subject=account(action?.execution_identity_id),owner=account(resource?.owner_identity_id)
  const permissions=(context.allow_permissions??[]).filter(item=>item.action_id===config.action_id&&item.action_revision===config.action_revision
    && item.subject_actor_id===subject?.actor_id&&item.owner_actor_id===owner?.actor_id)
  const allow=permissions.find(item=>item.intent_id===permission)??(permissions.length===1?permissions[0]:undefined)
  const inputs=(context.reference_inputs??[]).filter(item=>item.action_id===config.action_id&&item.action_revision===config.action_revision&&item.resource_binding_id===config.resource_binding_id)
  const gaps=(context.reference_recovery_gaps??[]).filter(item=>item.resource_id===resource?.resource_id&&item.owner_identity_id===resource?.owner_identity_id)
  const recoveryGap=gaps.find(item=>item.reason==='REFERENCE_RECOVERY_UNVERIFIED')
  const available=inputs.filter(item=>item.state==='COMPLETE'&&item.manifest)
  const chosen=available.find(item=>item.asset_id===(selected||preferredAsset||config.reference_artifact?.asset_id)) ?? (!selected && !preferredAsset && !config.reference_artifact && available.length===1 ? available[0] : undefined)
  const referenced=(assetId:string)=>context.sources.some(item=>item.config.reference_artifact?.asset_id===assetId)
  const activeCapture=captureId??inputs.find(item=>item.asset_id===preferredAsset)?.reference_capture_id??inputs.find(item=>item.state==='PENDING')?.reference_capture_id
  useEffect(()=>{
    if(!activeCapture||!visible)return
    let stopped=false
    let timer:ReturnType<typeof setInterval>|undefined
    const epoch=scope
    const read=async()=>{
      try {const value=await api.captureStatus(projectId,activeCapture)
        if(!stopped&&live.current===epoch&&value.capture_id===activeCapture){
          if(value.action_id!==config.action_id||value.resource_binding_id!==config.resource_binding_id){if(timer)clearInterval(timer);return}
          setStatus(value);if(!['PENDING','RUNNING','RETRY_WAIT'].includes(value.state)){if(timer)clearInterval(timer);await onRefresh()}}}
      catch{if(!stopped&&live.current===epoch)setIssue('取样状态暂时无法读取，请刷新；原操作不会再次发出。')}
    }
    void read();timer=setInterval(()=>void read(),1500)
    return()=>{stopped=true;clearInterval(timer)}
  },[activeCapture,projectId,scope,onRefresh,visible,config.action_id,config.resource_binding_id])
  const running=status&&['PENDING','RUNNING','RETRY_WAIT'].includes(status.state)
  const disabled=busy||pending||reading||Boolean(running)
  const preview=async(restoreCapture?:string)=>{
    if(!allow||!resource||!action?.execution_identity_id||!config.collection)return
    const ids=new Set([action.execution_identity_id,resource.owner_identity_id,action.recovery_identity_id].filter(Boolean))
    const value:CaptureSelection={basis_id:context.basis_id,action_id:config.action_id,action_revision:config.action_revision,
      allow_intent_id:allow.intent_id,resource_binding_id:resource.resource_binding_id,collection:config.collection,
      identity_claims:config.identity_claims.filter(item=>ids.has(item.identity_id)),...(restoreCapture?{restore_capture_id:restoreCapture}:{})}
    const epoch=scope;setReading(true);setIssue(undefined)
    try{const result=await api.capturePreview(projectId,value)
      if(live.current===epoch&&result.project_id===projectId&&result.basis_id===context.basis_id){setSelection(value);setPlan(result);setConfirmed(false)}}
    catch(error){if(live.current===epoch)setIssue(error instanceof Error?error.message:'暂时无法准备取样计划。')}
    finally{if(live.current===epoch)setReading(false)}
  }
  return <section className="proof-reference" aria-label="文件参照准备">
    <p className="editorial-muted">这份测试文件应属于：{resource?.resource_id??'需先确认测试资源'} · {owner?.label??'所有者尚未确认'}。</p>
    {issue&&<Alert type="warning" showIcon message={issue}/>}
    {recoveryGap&&<Alert type="warning" showIcon message="这份资源的恢复尚未确认" description="先核对原状态，必要时执行已确认的恢复操作。原取样不会自动重发。"
      action={<Button disabled={disabled||!allow||!context.runtime_available} onClick={()=>void preview(recoveryGap.capture_id)}>核对并恢复</Button>}/>}
    <Radio.Group className="proof-reference-modes" aria-label="测试文件的准备方式" value={mode} disabled={disabled} onChange={event=>setMode(event.target.value)}>
      <Radio value="capture" aria-label="让界鉴获取测试文件"><strong>让界鉴获取测试文件</strong><span>使用允许正常操作的账号，运行已录制的操作取得文件。</span></Radio>
      <Radio value="upload" aria-label="使用已有测试文件"><strong>使用已有测试文件</strong><span>选择一份能代表这项测试资源完整内容的文件。</span></Radio>
    </Radio.Group>
    {mode==='capture'?<div className="proof-reference-choice">
      <p>{subject?`使用已录制的正常操作，账号为${subject.label}。`:'请先完成正常账号、动作录制和测试资源。'}{action?.recovery_identity_id?'取样后还会执行已确认的恢复操作。':''}</p>
      {permissions.length>1&&<label>采用哪条正常权限<Select aria-label="取样采用的正常权限" value={permission||undefined} options={permissions.map(item=>({value:item.intent_id,label:`允许 · ${subject?.label}操作${owner?.label}的资源`}))} onChange={setPermission} disabled={disabled}/></label>}
      {!allow&&<p className="editorial-muted">需要一条与这次账号和资源对应的正常允许规则。</p>}
      <div className="proof-reference-primary"><p className="editorial-muted">先预览将使用的账号、操作和恢复方式。你确认后，界鉴才会运行这一次操作。</p><Button type={available.length?'default':'primary'} disabled={disabled||!allow||!context.runtime_available||gaps.length>0} loading={reading} onClick={()=>void preview()}>预览获取操作</Button></div>
    </div>:<div className="proof-reference-choice"><Upload maxCount={1} beforeUpload={value=>{setFile(value);return false}} onRemove={()=>setFile(undefined)} fileList={file?[{uid:'reference',name:file.name}]:[]} disabled={disabled}>
      <Button disabled={disabled}>选择测试文件</Button></Upload><p className="editorial-muted">选择代表上述测试资源完整内容的文件，非空且不超过4MiB。</p>
      <Button type={available.length?'default':'primary'} disabled={disabled||!file||!resource||!file.size||file.size>4194304} onClick={()=>void onWrite('UPLOAD_REFERENCE',{
        basis_id:context.basis_id,action_id:config.action_id,action_revision:config.action_revision,resource_binding_id:config.resource_binding_id,confirmed:true},file)}>上传测试参照</Button></div>}
    {status&&<div className="proof-reference-status" role="status"><StatusBadge kind="preparation" tone={status.report?.state==='CANDIDATE'||status.report?.state==='RECOVERED'?'neutral':'warning'}>{running?status.asset_id?'正在正常取样':'正在核对恢复':status.report?.state==='RECOVERED'?'原资源已恢复':status.report?.state==='CANDIDATE'?'候选待核对':status.state==='CANCELLED'?'取样已取消':'未取得可用参照'}</StatusBadge>
      {!recoveryGap&&status.operation_may_have_run&&!status.report?.recovery_verified&&!running&&<p>本次操作可能已经发出，恢复尚未确认。请刷新并核对原任务。</p>}
      {running&&<Button danger disabled={busy||pending} onClick={()=>void onWrite('CANCEL_REFERENCE_CAPTURE',{basis_id:context.basis_id,capture_id:status.capture_id})}>取消这次取样</Button>}</div>}
    {inputs.some(item=>item.state==='INCOMPLETE'||item.state==='CANCELLED')&&<details><summary>未取得可用参照的输入</summary>{inputs.filter(item=>item.state==='INCOMPLETE'||item.state==='CANCELLED').map(item=><div key={item.asset_id} className="proof-reference-actions"><span>{new Date(item.created_at_us/1000).toLocaleString('zh-CN')} · {item.state==='CANCELLED'?'已取消':'未完成'}</span><Button danger disabled={disabled} onClick={()=>setRemoval(item.asset_id)}>移除这份参照</Button></div>)}</details>}
    {available.length>0&&<div className="proof-reference-choice"><label>核对取得的参照<Select aria-label="本次参照文件" value={chosen?.asset_id} placeholder="选择一份已取得的参照" disabled={disabled}
      options={available.map(item=>({value:item.asset_id,label:`${item.origin==='UPLOAD'?'上传的文件':'正常取样'} · ${Math.ceil(item.manifest!.size/1024)} KiB · ${new Date(item.created_at_us/1000).toLocaleString('zh-CN')}`}))} onChange={setSelected}/></label>
      {chosen&&<><div className="proof-reference-actions">{referenced(chosen.asset_id)&&<p className="editorial-muted proof-reference-note">这份文件已用于检查材料，会随记录保留。</p>}{!referenced(chosen.asset_id)&&<Button danger disabled={disabled} onClick={()=>setRemoval(chosen.asset_id)}>移除未使用的参照</Button>}<Button type={config.reference_artifact?.asset_id===chosen.asset_id ? 'primary' : 'default'} href={api.referenceDownload(projectId,chosen.asset_id)}>保存文件并核对内容</Button>{config.reference_artifact?.asset_id!==chosen.asset_id&&<Button type="primary" disabled={disabled} onClick={()=>void onWrite('SAVE_SOURCE',{
        basis_id:context.basis_id,source_id:source.source_id,expected_revision:source.revision,config:{...config,reference_artifact:chosen.manifest,reference_origin:chosen.origin,
          reference_resource_id:chosen.resource_id,reference_owner_identity_id:chosen.owner_identity_id}})}>以此参照继续</Button>}</div><details><summary>查看文件摘要</summary><code>{chosen.manifest!.sha256}</code><p>实际大小：{chosen.manifest!.size} 字节。</p></details></>}
    </div>}
    <Modal open={Boolean(removal)} title="移除这份未采用的参照？" okText="移除参照" cancelText="保留" confirmLoading={busy} okButtonProps={{danger:true,disabled:pending}} cancelButtonProps={{disabled:busy||pending}}
      onCancel={()=>{if(!busy&&!pending)setRemoval(undefined)}} onOk={()=>{const epoch=scope;if(removal)void onWrite('CANCEL_REFERENCE',{basis_id:context.basis_id,asset_id:removal,confirmed:true}).then(()=>{if(live.current===epoch)setRemoval(undefined)})}}>
      <p>只清理这份输入文件，原任务与恢复记录仍然保留。被来源或检查引用的文件会保留。</p>
    </Modal>
    <Modal open={Boolean(plan)} title={plan?.restore?'核对并恢复原资源':'正常取得一份参照'} onCancel={()=>{if(!busy&&!pending)setPlan(undefined)}} maskClosable={false} closable={!busy&&!pending}
      okText={plan?.restore?'允许本次恢复核对':'允许并开始本次取样'} cancelText="返回核对" confirmLoading={busy} okButtonProps={{disabled:!confirmed||pending}} cancelButtonProps={{disabled:busy||pending}}
      onOk={()=>{const epoch=scope;if(plan&&selection)void onWrite('START_REFERENCE_CAPTURE',{basis_id:context.basis_id,selection,plan_hash:plan.plan_hash,plan_created_at_us:plan.created_at_us,confirmed:true}).then(()=>{if(live.current===epoch)setPlan(undefined)})}}>
      {plan&&<>{plan.restore?<><p>核对「{plan.case.resource_id}」是否回到原取样前的状态。必要时使用已确认的恢复操作。</p><p>本次不会重新下载，也不会取得或采用新的文件参照。</p></>:<><p>以「{account(plan.case.subject_test_identity_id)?.label??'所选账号'}」对「{plan.case.resource_id}」执行一次「{plan.runtime.actions[0].display_name}」，最多接收{Math.min(4096,Math.ceil(plan.runtime.target.max_response_bytes/1024))} KiB。</p>
        <p>{plan.runtime.actions[0].state_changing?'这次操作会改变测试应用，完成后按已确认的方式恢复。':'这项录制为只读操作。'}此次只准备参照，文件取得后仍需核对并采用。</p></>}
        <details><summary>查看运行与来源</summary><p>{plan.runtime.target.base_url}</p><code>{plan.runtime.source_fingerprint}</code></details>
        <Checkbox checked={confirmed} onChange={event=>setConfirmed(event.target.checked)} disabled={busy||pending}>{plan.restore?'允许本次核对及必要的恢复操作':'允许本次正常操作及所列恢复'}</Checkbox></>}
    </Modal>
  </section>
}
