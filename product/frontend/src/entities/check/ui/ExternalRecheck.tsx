import {PendingRecovery} from '../../../shared/ui/PendingRecovery'
import {useRef,useState} from 'react'
import {currentChecksApi as api,type CheckPreview,type ExternalRecheckCommand} from '../api/currentChecks'
import {repairReference,type RepairContract,type RepairComparisonRow} from '../api/repairs'
import {Dialog} from '../../../shared/ui/Dialog'
import {Field} from '../../../shared/ui/layout'
import {Button} from '../../../shared/ui/actions'
import {ContextNote,ErrorNote,InlineFeedback,Notice} from '../../../shared/ui/feedback'
import {operationId,readPending,savePending,notAccepted,isRecord,isOperationId,isPublicId} from '../../../shared/lib/operations'
import {go,withReturnDestination} from '../../../shared/lib/navigation'
import './recheck.css'
import {groupRepairComparisons} from '../model/repairComparisons'

type Pending={operation:string;fingerprint:string;command:ExternalRecheckCommand}

export function ExternalRecheck({projectId,contract,comparison,endpoint,onClose,returnTo}:{projectId:string;contract:RepairContract;comparison:RepairComparisonRow[];endpoint:string;onClose:()=>void;returnTo?:string}) {
  const cases=groupRepairComparisons(comparison)
  const key='jiejian.external-recheck:'+projectId+':'+contract.repair_fingerprint
  const draftKey=key+':statement'
  const acceptsPending=(value:unknown):value is Pending=>isRecord(value)&&isOperationId(value.operation)&&isPublicId(value.fingerprint)&&isRecord(value.command)&&isRecord(value.command.reference)&&value.command.reference.source_run_id===contract.source_run_id&&value.command.reference.source_case_id===contract.source_case_id&&value.command.reference.repair_fingerprint===contract.repair_fingerprint&&typeof value.command.deployment_statement==='string'&&Array.from(value.command.deployment_statement).length<=256
  const [pending,setPending]=useState(()=>readPending<Pending>(key,acceptsPending))
  const [statement,setStatement]=useState(()=>pending?.command.deployment_statement??readPending<string>(draftKey,(value):value is string=>typeof value==='string'&&value.length<=256)??'')
  const [preview,setPreview]=useState<CheckPreview>(),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[absent,setAbsent]=useState(false)
  const guard=useRef(false)
  const act=async(task:()=>Promise<void>)=>{if(guard.current)return;guard.current=true;setBusy(true);setError(undefined);try{await task()}catch(value){setError(value)}finally{guard.current=false;setBusy(false)}}
  const command=():ExternalRecheckCommand=>({reference:repairReference(contract),deployment_statement:pending?.command.deployment_statement??statement.trim()})
  const open=(run:string)=>{savePending(key,undefined);savePending(draftKey,undefined);setPending(undefined);const path='/reports?run_id='+encodeURIComponent(run);go(returnTo?withReturnDestination(path,returnTo):path);onClose()}
  const submit=async()=>{
    const current=await api.externalPreview(projectId,command())
    if(!current.can_execute||current.plan_fingerprint!==(pending?.fingerprint??preview?.plan_fingerprint)){
      setPreview(current);throw new Error('检查条件已变化，请重新核对原问题及当前材料。')
    }
    if((await api.list(projectId,true)).length)throw new Error('当前应用已有检查正在进行，请先查看并等待其完成。')
    const input=pending??{operation:operationId(),fingerprint:current.plan_fingerprint,command:command()}
    savePending(key,input);setPending(input)
    try{
      const result=await api.submit(projectId,input.fingerprint,input.operation,null,null,input.command)
      open(result.run.run_id)
    }catch(error){if(notAccepted(error,Boolean(pending))){savePending(key,undefined);setPending(undefined);setAbsent(false)}throw error}
  }
  const recover=async()=>{
    if(!pending)return
    const value=await api.receipt(projectId,pending.operation)
    if(value)open(value.run.run_id);else setAbsent(true)
  }
  return <Dialog title="再次验证原问题" size="wide" closeDisabled={busy} onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>返回问题</Button>{pending?<><Button busy={busy} onClick={()=>void act(recover)}>查看上次提交结果</Button>{absent&&<Button busy={busy} onClick={()=>void act(submit)}>恢复原提交</Button>}</>:preview?<Button kind="primary" busy={busy} disabled={!preview.can_execute} onClick={()=>void act(submit)}>确认范围并开始</Button>:<Button kind="primary" busy={busy} disabled={!statement.trim()} onClick={()=>void act(async()=>setPreview(await api.externalPreview(projectId,command())))}>预览原问题与正常对照</Button>}</>}>
    <PendingRecovery storageKey={key} projectId={projectId}/><p>本次应用连接：<strong>{endpoint}</strong></p>
    <Field label="本次部署或处理说明" hint="填写本次部署或处理的公开信息，请勿填写凭据。返回后可继续编辑。"><textarea maxLength={256} value={statement} disabled={busy||Boolean(pending)} onChange={event=>{setStatement(event.target.value);savePending(draftKey,event.target.value);setPreview(undefined)}}/></Field>
    <section className="jj-recheck-context"><h3>沿用的原问题与正常功能</h3><div className="jj-recheck-cases">{cases.map(({key,row,roles})=><article key={key}><h4>{roles.includes('DENY')?'禁止场景':roles.includes('SELECTED_ALLOW')?roles.includes('REGRESSION')?'正常对照与功能回归':'正常对照':'正常功能回归'}</h4><p>{row.subject_label} → {row.resource_owner_label}</p><p className="jj-small jj-muted">资源 {row.resource_id} · {row.effect_labels.join('、')}</p></article>)}</div></section>
    {preview&&(preview.can_execute?<InlineFeedback>本次执行 {preview.case_count} 项检查，沿用原问题、正常对照及原检查范围。材料已齐备，提交前会再次核对。</InlineFeedback>:<Notice tone="caution" title="仍有准备缺口">本次需要 {preview.case_count} 项检查，请返回测试场景补齐材料后再提交。</Notice>)}
    <ContextNote label="本次验证的适用范围"><p>本次验证应用当前的实际行为。确认源码修复有效，还需核对运行版本。规则、账号、测试数据或判断标准发生变化时，请先重新确认原问题的检查条件。</p></ContextNote>
    {pending&&<Notice tone="caution" title="原提交结果待确认">先查询原记录，再决定是否恢复同一请求。{Boolean(error)&&<p>{error instanceof Error?error.message:'查询未完成，请稍后重试。'}</p>}</Notice>}
    {!pending&&Boolean(error)&&<ErrorNote error={error}/>}
  </Dialog>
}
