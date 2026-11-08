import {useRef,useState} from 'react'
import {currentChecksApi as api,type CheckPreview,type ExternalRecheckCommand} from '../api/currentChecks'
import {repairReference,type RepairContract,type RepairComparisonRow} from '../api/repairs'
import {Dialog} from '../../../shared/ui/Dialog'
import {Field} from '../../../shared/ui/layout'
import {Button} from '../../../shared/ui/actions'
import {ErrorNote,Notice} from '../../../shared/ui/feedback'
import {operationId,readPending,savePending} from '../../../shared/lib/operations'
import {go,withReturnDestination} from '../../../shared/lib/navigation'
import './recheck.css'

type Pending={operation:string;fingerprint:string;command:ExternalRecheckCommand}

export function ExternalRecheck({projectId,contract,comparison,endpoint,onClose,returnTo}:{projectId:string;contract:RepairContract;comparison:RepairComparisonRow[];endpoint:string;onClose:()=>void;returnTo?:string}) {
  const key='jiejian.external-recheck:'+projectId+':'+contract.repair_fingerprint
  const [pending,setPending]=useState(()=>readPending<Pending>(key))
  const [statement,setStatement]=useState(pending?.command.deployment_statement??'')
  const [preview,setPreview]=useState<CheckPreview>(),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[absent,setAbsent]=useState(false)
  const guard=useRef(false)
  const act=async(task:()=>Promise<void>)=>{if(guard.current)return;guard.current=true;setBusy(true);setError(undefined);try{await task()}catch(value){setError(value)}finally{guard.current=false;setBusy(false)}}
  const command=():ExternalRecheckCommand=>pending?.command??{reference:repairReference(contract),deployment_statement:statement.trim()}
  const open=(run:string)=>{savePending(key,undefined);setPending(undefined);const path='/reports?run_id='+encodeURIComponent(run);go(returnTo?withReturnDestination(path,returnTo):path);onClose()}
  const submit=async()=>{
    const current=await api.externalPreview(projectId,command())
    if(!current.can_execute||current.plan_fingerprint!==(pending?.fingerprint??preview?.plan_fingerprint)){
      setPreview(current);throw new Error('检查条件已变化，请重新核对原问题及当前材料。')
    }
    if((await api.list(projectId,true)).length)throw new Error('当前应用已有检查正在进行，请先查看并等待其完成。')
    const input=pending??{operation:operationId(),fingerprint:current.plan_fingerprint,command:command()}
    savePending(key,input);setPending(input)
    const result=await api.submit(projectId,input.fingerprint,input.operation,null,null,input.command)
    open(result.run.run_id)
  }
  const recover=async()=>{
    if(!pending)return
    const value=await api.receipt(projectId,pending.operation)
    if(value)open(value.run.run_id);else setAbsent(true)
  }
  return <Dialog title="再次验证原问题" size="wide" closeDisabled={busy} onClose={onClose} actions={dismiss=><><Button disabled={busy} onClick={dismiss}>返回问题</Button>{pending?<><Button busy={busy} onClick={()=>void act(recover)}>查看上次提交结果</Button>{absent&&<Button busy={busy} onClick={()=>void act(submit)}>恢复原提交</Button>}</>:preview?<Button kind="primary" busy={busy} disabled={!preview.can_execute} onClick={()=>void act(submit)}>确认范围并开始</Button>:<Button kind="primary" busy={busy} disabled={!statement.trim()} onClick={()=>void act(async()=>setPreview(await api.externalPreview(projectId,command())))}>预览原问题与正常对照</Button>}</>}>
    <p>本次应用连接：<strong>{endpoint}</strong></p>
    <Field label="本次部署或处理说明" hint="保存公开说明，不填写任何凭据；部署版本仍未独立核对。"><textarea maxLength={256} value={statement} disabled={busy||Boolean(pending)} onChange={event=>{setStatement(event.target.value);setPreview(undefined)}}/></Field>
    <section className="jj-recheck-context"><h3>沿用的原问题与正常功能</h3><div className="jj-recheck-cases">{comparison.map(row=><article key={row.source_case_id}><h4>{row.role==='DENY'?'禁止场景':'正常对照'}</h4><p>{row.subject_label} → {row.resource_owner_label}</p><p className="jj-small jj-muted">资源 {row.resource_id} · {row.effect_labels.join('、')}</p></article>)}</div></section>
    {preview&&<Notice tone={preview.can_execute?'neutral':'caution'}>本次执行 {preview.case_count} 项检查，保留原问题、正常对照及原检查范围。{preview.can_execute?'材料具备，提交前仍会重新核对。':'仍有准备缺口，请返回测试场景处理。'}</Notice>}
    <Notice tone="caution">这次验证会核对应用当前的实际行为。源码修复及部署版本尚未核对；规则、账号、测试数据或判断标准变化时，需要先重新确认原问题的检查条件。</Notice>
    {pending&&<Notice tone="caution">原提交的结果尚待查询。先查回原记录，再决定是否恢复同一请求。</Notice>}
    {Boolean(error)&&<ErrorNote error={error}/>}
  </Dialog>
}
