import {useEffect,useRef,useState} from 'react'
import {proofSourcesApi as api,type CapturePlan,type CaptureSelection,type ProofContext,type ProofOperationKind,type ProofReceipt,type ProofSource} from '../../../entities/preparation/api/proofSources'
import {useRead} from '../../../shared/lib/useRead'
import {conditionLabels} from '../../../entities/permission/ui/RuleConditions'
import {Choice} from '../../../shared/ui/Choice'
import {FilePicker} from '../../../shared/ui/FilePicker'
import {Tabs} from '../../../shared/ui/Tabs'
import {TaskSurface} from '../../../shared/ui/TaskSurface'
import {ActionLink,Button} from '../../../shared/ui/actions'
import {Badge,ErrorNote,Loading,Notice} from '../../../shared/ui/feedback'
import {Field,FormColumns,ObjectHeading,SectionHeading,TaskActions,TaskStage} from '../../../shared/ui/layout'
import {ActivityDots} from '../../../shared/ui/ActivityDots'
import './reference-file.css'

type Props={projectId:string;context:ProofContext;source:ProofSource;busy:boolean;pending:boolean;onBack:()=>void;onRefresh:()=>void;onWrite:(kind:ProofOperationKind,body:object,content?:ArrayBuffer)=>Promise<ProofReceipt|undefined>;onRecover:()=>Promise<ProofReceipt|undefined>}
const active=(state?:string)=>['PENDING','RUNNING','RETRY_WAIT'].includes(state??'')

/** 参照候选与正式采用分开。所有写入沿用来源页的持久操作标识，恢复只查询原回执。 */
export function ReferenceFilePreparation({projectId,context,source,busy,pending,onBack,onRefresh,onWrite,onRecover}:Props){
 const config=source.config,action=context.actions.find(item=>item.action_id===config.action_id)
 const resource=context.resources.find(item=>item.resource_binding_id===config.resource_binding_id)
 const owner=context.identities.find(item=>item.identity_id===resource?.owner_identity_id)
 const label=(id:string|undefined)=>context.identities.find(item=>item.identity_id===id)?.label??'尚未对应账号'
 const key='jiejian.reference-capture:'+projectId+':'+source.source_id
 const gap=context.reference_recovery_gaps?.find(item=>item.action_id===config.action_id&&item.resource_id===resource?.resource_id&&item.owner_identity_id===owner?.identity_id&&item.reason==='REFERENCE_RECOVERY_UNVERIFIED')
 // 恢复成功后旧输入仍可保留 INCOMPLETE；只有未解决的恢复事项或运行中任务可自动接续。
 const [capture,setCapture]=useState(()=>{let remembered:string|null=null;try{remembered=sessionStorage.getItem(key)}catch{/* 存储不可用时继续按服务端当前事项接续。 */}return remembered??gap?.capture_id??context.reference_inputs?.filter(item=>item.action_id===config.action_id&&item.resource_binding_id===config.resource_binding_id&&item.state==='PENDING').sort((a,b)=>b.created_at_us-a.created_at_us)[0]?.reference_capture_id??''})
 const [method,setMethod]=useState<'upload'|'capture'>('upload'),[file,setFile]=useState<File>(),[ack,setAck]=useState(false)
 const [working,setWorking]=useState(false),[error,setError]=useState<unknown>(),lock=useRef(false)
 const [planned,setPlanned]=useState<{selection:CaptureSelection;plan:CapturePlan}>()
 const permissions=context.allow_permissions?.filter(item=>item.action_id===config.action_id&&item.action_revision===config.action_revision&&(!item.protected_effect_ids||item.protected_effect_ids.includes(config.effect_id))&&item.owner_actor_id===owner?.actor_id&&item.subject_actor_id===context.identities.find(identity=>identity.identity_id===action?.execution_identity_id)?.actor_id)??[]
 const [permission,setPermission]=useState(permissions.length===1?permissions[0].intent_id:'')
 const status=useRead(capture?'reference-capture:'+projectId+':'+capture:null,async()=>{
  const value=await api.captureStatus(projectId,capture)
  if(value.capture_id!==capture||value.action_id!==config.action_id||value.resource_binding_id!==config.resource_binding_id)throw new Error('取样记录与当前业务操作或测试数据不一致，请返回原记录核对。')
  return value
 },value=>active(value?.state)?1000:0)
 const result=status.data,report=result?.report,waiting=active(result?.state)
 useEffect(()=>{if(result&&!active(result.state))onRefresh()},[result?.capture_id,result?.state,report?.state,onRefresh])
 const blocked=busy||working||pending||Boolean(status.error)
 const act=async(run:()=>Promise<void>)=>{if(lock.current)return;lock.current=true;setWorking(true);setError(undefined);try{await run()}catch(value){setError(value)}finally{lock.current=false;setWorking(false)}}
 const remember=(id:string)=>{setCapture(id);setAck(false);setPlanned(undefined);onRefresh();sessionStorage.setItem(key,id)}
 const acceptReceipt=(receipt:ProofReceipt|undefined)=>{if(receipt?.operation_kind==='START_REFERENCE_CAPTURE'&&receipt.result.capture_id)remember(receipt.result.capture_id)}
 const preview=async(restore?:string)=>{
  const ids=new Set([action?.execution_identity_id,owner?.identity_id,action?.recovery_identity_id].filter(Boolean))
  const claims=config.identity_claims.filter(item=>ids.has(item.identity_id))
  if(!resource||!config.collection||!permission||!ids.size||claims.length!==ids.size)throw new Error('请先核对正常权限、操作账号、测试数据与恢复安排，再准备参照。')
  const selection:CaptureSelection={basis_id:context.basis_id,action_id:config.action_id,action_revision:config.action_revision,allow_intent_id:permission,resource_binding_id:config.resource_binding_id,collection:config.collection,identity_claims:claims,...(restore?{restore_capture_id:restore}:{})}
  const plan=await api.capturePreview(projectId,selection)
  if(plan.project_id!==projectId||plan.basis_id!==selection.basis_id||plan.case.resource_binding_id!==selection.resource_binding_id)throw new Error('取样预览与当前材料不一致，请重新读取。')
  setAck(false);setPlanned({selection,plan})
 }
 const facts=<dl className="jj-facts"><div><dt>业务操作</dt><dd>{action?.label??'当前文件操作'}</dd></div><div><dt>测试资源</dt><dd>{resource?.resource_id??'尚未对应'}</dd></div><div><dt>资源所有者</dt><dd>{owner?.label??'尚未对应'}</dd></div></dl>
 const recovery=pending&&<Notice tone="caution" title="上次操作的结果尚未确认" actions={<Button disabled={busy||working} onClick={()=>void act(async()=>{acceptReceipt(await onRecover());status.reload()})}>查询这次操作</Button>}>查询原操作结果后再继续。</Notice>
 const frame={onBack,backLabel:'返回结果证明',backDisabled:busy||working,width:'wide' as const,context:action?.label??'当前文件操作'}
 if(planned){
  const {plan,selection}=planned,restore=Boolean(plan.restore),stale=plan.basis_id!==context.basis_id
  return <TaskSurface {...frame} title={restore?'核对并恢复测试数据':'通过正常操作取得参照'} description={restore?'只恢复上次取样前的测试数据，不重复执行取文件操作。':'使用已批准的正常权限执行一次已保存流程，取得文件后核对测试数据恢复。'} onBack={()=>setPlanned(undefined)}>
   {recovery}{Boolean(error)&&<ErrorNote error={error}/>}<TaskStage context={<section className="jj-reference-section"><SectionHeading title="本次操作对象" appearance="group"/>{facts}<dl className="jj-facts"><div><dt>操作账号</dt><dd>{label(restore?plan.case.resource_owner_test_identity_id:plan.case.subject_test_identity_id)}</dd></div></dl></section>}><section className="jj-reference-section"><SectionHeading title={restore?'只恢复原测试数据':'本次执行与收尾'} appearance="group"/>
    <p>{restore?'沿用原取样保存的资源起点核对并恢复。':`执行“${plan.runtime.actions[0].display_name}”的已保存流程，共 ${plan.runtime.actions[0].steps.length} 步。`}</p><p>{plan.runtime.actions[0].state_changing?'执行后核对既有恢复安排；恢复未确认时，停止在这份测试数据上继续检查。':'这项操作不改变业务数据。'}</p>
    <dl className="jj-facts"><div><dt>应用地址</dt><dd className="jj-path">{plan.runtime.target.base_url}</dd></div><div><dt>本次请求上限</dt><dd>{plan.runtime.budget.max_requests} 次</dd></div><div><dt>{restore?'单次响应上限':'完整文件上限'}</dt><dd>{Math.ceil(plan.runtime.target.max_response_bytes/1024)} KiB</dd></div></dl>
   </section>{stale&&<Notice tone="caution">账号或材料已有变化，请返回重新查看执行范围。</Notice>}
   <label className="jj-checkbox"><input type="checkbox" checked={ack&&!stale} disabled={blocked||stale} onChange={event=>setAck(event.target.checked)}/><span>{restore?'允许核对并恢复上述测试数据':'允许执行上述正常操作并核对恢复'}</span></label><TaskActions><Button disabled={busy||working} onClick={()=>setPlanned(undefined)}>返回调整</Button><Button kind="primary" busy={busy||working} disabled={!ack||blocked||stale} onClick={()=>void act(async()=>acceptReceipt(await onWrite('START_REFERENCE_CAPTURE',{basis_id:plan.basis_id,selection,plan_hash:plan.plan_hash,plan_created_at_us:plan.created_at_us,confirmed:true})))}>{restore?'确认恢复一次':'确认执行一次'}</Button></TaskActions></TaskStage>
  </TaskSurface>
 }
 if(capture)return <TaskSurface {...frame} title="正常操作的参照取样" description="取样只准备文件参照；来源授权、核对与正式检查仍在后续完成。">
  {recovery}{Boolean(error)&&<ErrorNote error={error}/>}<div className="jj-reference-result">
   {status.error&&<ErrorNote error={status.error} actions={<Button onClick={status.reload}>重新读取取样进度</Button>}/>}{status.loading&&!result&&<Loading>正在读取原取样任务</Loading>}
   {result&&<TaskStage context={<section className="jj-reference-section"><SectionHeading title="这次取样的对象" appearance="group"/>{facts}</section>}><ObjectHeading title={waiting?'正在取得完整参照':report?.state==='CANDIDATE'?'完整参照已取得':report?.state==='RECOVERED'?'测试数据已恢复':gap?'先核对测试数据恢复':result.state==='CANCELLED'?'取样已停止':'这次未取得可用参照'} status={<Badge tone={report?.state==='CANDIDATE'||report?.state==='RECOVERED'?'positive':waiting?'accent':'caution'}>{waiting&&<ActivityDots/>}{waiting?'处理中':report?.state==='CANDIDATE'?'待确认使用':report?.state==='RECOVERED'?'恢复已确认':'需要核对'}</Badge>}/>
    <section className="jj-reference-section" aria-label="当前取样结果">
     {waiting?<p>正在执行已确认的正常流程，接收文件并核对恢复。离开页面后仍可回到原任务查看；停止不会重新发送取文件请求。</p>:report?.state==='CANDIDATE'?<><p>已完整接收本次正常操作返回的文件，测试数据恢复已核对。</p><p>请先下载查看，确认它是上述资源的正确完整文件，再保存为本次参照。</p>{report.manifest&&<p className="jj-reference-download"><span>{report.manifest.size} 字节</span><ActionLink href={api.referenceDownload(projectId,report.manifest.asset_id)} download>下载查看文件</ActionLink></p>}</>:report?.state==='RECOVERED'?<p>已沿用原取样起点核对测试数据恢复。本次没有重复执行取文件操作，也没有建立新参照。</p>:<><p>{gap?'上次操作可能已改变测试数据，恢复结果尚未确认。先沿原起点核对并恢复，再继续准备。':'这次没有形成可采用的完整参照。保留原任务和已有文件，不将停止或失败当作业务恢复。'}</p>{report?.reason_codes.length? <details><summary>查看本次未完成的原因</summary><ul>{report.reason_codes.map(reason=><li key={reason}>{captureReason(reason)}</li>)}</ul></details>:null}</>}
    </section>
    {!waiting&&!gap&&report?.state==='CANDIDATE'&&report.manifest&&<label className="jj-checkbox"><input type="checkbox" checked={ack} disabled={blocked} onChange={event=>setAck(event.target.checked)}/><span>我已确认文件内容与上述资源对应</span></label>}
    <TaskActions>{waiting?<Button disabled={blocked} onClick={()=>void act(async()=>{await onWrite('CANCEL_REFERENCE_CAPTURE',{basis_id:context.basis_id,capture_id:capture});status.reload();onRefresh()})}>停止本次取样</Button>:gap?<Button kind="primary" disabled={blocked} onClick={()=>void act(()=>preview(gap.capture_id))}>核对并恢复测试数据</Button>:report?.state==='CANDIDATE'&&report.manifest?<Button kind="primary" disabled={!ack||blocked} onClick={()=>void act(async()=>{const saved=await onWrite('SAVE_SOURCE',{basis_id:context.basis_id,source_id:source.source_id,expected_revision:source.revision,config:{...config,reference_artifact:report.manifest,reference_origin:'REFERENCE_CAPTURE',reference_resource_id:resource?.resource_id,reference_owner_identity_id:resource?.owner_identity_id}});if(saved){sessionStorage.removeItem(key);onBack()}})}>保存为本次参照</Button>:<><Button kind="quiet" onClick={onBack}>返回结果证明</Button><Button kind="primary" disabled={blocked} onClick={()=>{sessionStorage.removeItem(key);setCapture('');setAck(false)}}>准备新的参照</Button></>}</TaskActions>
   </TaskStage>}
  </div>
 </TaskSurface>
 return <TaskSurface {...frame} title="准备完整参照文件" description="先确认正确文件属于哪份测试资源，再选择已有文件或通过正常操作取得。">
  {recovery}{Boolean(error)&&<ErrorNote error={error}/>}<Tabs label="参照取得方式" value={method} onValueChange={value=>{setMethod(value as typeof method);setAck(false)}} items={[{value:'upload',label:'上传已有文件'},...(!config.async_export?[{value:'capture',label:'通过正常操作取得'}]:[])]} panelId="reference-method-panel" idPrefix="reference-method"/>
  <div id="reference-method-panel" role="tabpanel" aria-labelledby={'reference-method-'+method} className="jj-reference-method"><FormColumns><section className="jj-reference-section"><SectionHeading title="参照所属对象" appearance="group"/>{facts}<p>参照用于比较实际接收的文件内容。它只定义正确文件，保存后仍需授权、核对来源并确认用于检查。</p></section><section className="jj-reference-section"><SectionHeading title={method==='upload'?'选择已确认的完整文件':'使用已保存的正常流程'} appearance="group"/>
   {method==='upload'?<><p>上传属于上述测试资源和所有者的正确文件，单份最多4 MiB。保存后，返回结果证明选择“用于这项结果”。</p><FilePicker label="完整测试参照文件" file={file} maxBytes={4194304} disabled={blocked} onFileChange={setFile}/>{config.async_export&&<p>异步导出使用事先确认的完整文件作为参照；检查会另外核对任务终态与实际文件接收。</p>}</>:<><p>先预览实际账号、测试数据和执行范围。你确认后才执行一次，完成后取得参照候选并核对数据恢复。</p>{permissions.length>1&&<Field measure="standard" label="正常权限"><Choice value={permission} onValueChange={setPermission}><option value="">选择已批准的正常权限</option>{permissions.map(item=><option key={item.intent_id} value={item.intent_id}>{[item.relation==='OWNS'?'操作自己的资源':'操作已批准范围的资源',...conditionLabels(item.conditions)].join(' · ')}</option>)}</Choice></Field>}{!permissions.length&&<Notice tone="caution">尚未对应可执行的正常权限。请返回核对操作账号、资源归属与既有流程。</Notice>}</>}
   <TaskActions>{method==='upload'?<Button kind="primary" disabled={!file||blocked||!resource} onClick={()=>void act(async()=>{const bytes=await file!.arrayBuffer(),hash=await crypto.subtle.digest('SHA-256',bytes),sha256=[...new Uint8Array(hash)].map(item=>item.toString(16).padStart(2,'0')).join('');const saved=await onWrite('UPLOAD_REFERENCE',{basis_id:context.basis_id,action_id:config.action_id,action_revision:config.action_revision,resource_binding_id:config.resource_binding_id,confirmed:true,size:bytes.byteLength,sha256},bytes);if(saved)onBack()})}>确认归属并保存文件</Button>:<Button kind="primary" disabled={blocked||!permission||!resource||!context.runtime_available} onClick={()=>void act(()=>preview())}>预览本次正常操作</Button>}</TaskActions>
  </section></FormColumns></div>
 </TaskSurface>
}

function captureReason(reason:string){return ({REFERENCE_RECOVERY_UNVERIFIED:'测试数据恢复尚未确认。',CAPTURE_CANCELLED:'本次取样已停止。',FILE_RESPONSE_INCOMPLETE:'文件接收未完成。',IDENTITY_UNAVAILABLE:'本次实际账号尚未核验。',REFERENCE_FILE_INCOMPLETE:'没有取得完整文件。'} as Record<string,string>)[reason]??'这次取样未满足完整文件、账号、资源或恢复的核对要求。'}
