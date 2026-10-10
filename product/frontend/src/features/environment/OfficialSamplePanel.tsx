// 官方环境只控制本机示例生命周期和源码条件；审批、材料与结果走普通产品页面。
import { Alert, Button, Modal, Space } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { experienceApi, type OfficialExperienceDto } from '../../api/applications/experience'
import { ApiError } from '../../api/http'
import { StatusBadge } from '../../shared/ui/StatusBadge'

export function OfficialSamplePanel({ value: externalValue, onChanged, onError, expanded = false, compact = false }: {
  expanded?: boolean; compact?: boolean
  value: OfficialExperienceDto | null; onChanged: (value: OfficialExperienceDto) => Promise<void>; onError: (error: ApiError) => void
}) {
  const [progress,setProgress]=useState<OfficialExperienceDto|null>(null)
  const value=progress??externalValue
  const observed=useRef<string|undefined>(undefined)
  const operationKey='jiejian.environment.operation'
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState<'start' | 'reset' | 'stop' | 'resume' | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const [syncFailed, setSyncFailed] = useState(false)
  const pendingOperation = useRef<{ action: 'start' | 'reset' | 'stop' | 'resume'; id: string } | undefined>(undefined)
  const inFlight = useRef(false)
  const [now,setNow]=useState(Date.now())
  useEffect(()=>{
    if(!busy&&progress?.operation_state!=='PENDING'&&!uncertain)setProgress(null)
  },[externalValue])
  useEffect(()=>{
    if(value?.operation_state!=='PENDING')return
    const timer=setInterval(()=>setNow(Date.now()),1000)
    return()=>clearInterval(timer)
  },[value?.operation_state])
  const elapsed=value?.operation_started_at_us?Math.max(0,((value.operation_finished_at_us??now*1000)-value.operation_started_at_us)/1000000):null
  const synchronize = async (next: OfficialExperienceDto) => {
    try { await onChanged(next); setSyncFailed(false) }
    catch (error) { setSyncFailed(true); onError(error as ApiError) }
  }
  const accept=async(next:OfficialExperienceDto)=>{
    setProgress(next)
    if(next.operation_state==='PENDING'){
      if(next.operation_id)sessionStorage.setItem(operationKey,next.operation_id)
      setUncertain(false);return
    }
    if(next.operation_state==='UNKNOWN'){setUncertain(true);return}
    sessionStorage.removeItem(operationKey);pendingOperation.current=undefined;setUncertain(false)
    if(!next.operation_id||observed.current!==next.operation_id){observed.current=next.operation_id??undefined;await synchronize(next)}
  }
  const pollOperation=sessionStorage.getItem(operationKey)??(value?.operation_state==='PENDING'?value.operation_id:null)
  useLiveRead(pollOperation?`official-operation:${pollOperation}`:undefined,async()=>{
    const next=await experienceApi.status(pollOperation??undefined,true)
    await accept(next.operation_state==='SUCCEEDED'?await experienceApi.status(pollOperation??undefined):next)
    return next.operation_state==='PENDING'
  },400,false)
  const reread = async () => {
    if(inFlight.current)return
    inFlight.current=true;setBusy(true)
    try{
      await accept(value?.operation_state==='PENDING'?await experienceApi.status(pollOperation??undefined):await experienceApi.reconcile())
      if(syncFailed)await synchronize(await experienceApi.status())
    }
    catch(error){onError(error as ApiError)}finally{inFlight.current=false;setBusy(false)}
  }
  const perform = async (operation: () => Promise<OfficialExperienceDto>) => {
    if(inFlight.current||uncertain)return
    inFlight.current=true;setBusy(true);setConfirm(null)
    if(pendingOperation.current)sessionStorage.setItem(operationKey,pendingOperation.current.id)
    try{await accept(await operation())}
    catch(error){
      onError(error as ApiError);setUncertain(true)
      // 未知写入只查同一个操作，不创建新的启动命令。
      try{await accept(await experienceApi.status(pendingOperation.current?.id))}catch{/* 保留原操作定位。 */}
    }finally{inFlight.current=false;setBusy(false)}
  }
  const phases:Record<string,string>={ACCEPTED:'已收到启动请求',CHECKING_PREVIOUS:'正在核对上次实例',CREATING_PROJECT:'正在准备示例项目',LOADING_APPLICATION:'正在启动数字展馆',WAITING_APPLICATION:'正在等待应用响应',CHECKING_CONNECTION:'正在核对应用连接',READING_SOURCE:'正在整理接入信息',COMPLETED:'示例已准备好',NEEDS_REVIEW:'需要核对本次启动状态'}
  const legacyOwnershipMissing = value?.lifecycle === 'UNKNOWN' && value.recovery_state === 'NONE'
  // 工作台保持同一个启动入口；旧实例已退出只是历史事实，详细归档说明留在环境页。
  const retainedExited = Boolean(value?.workspace_retained && value.recovery_state === 'EXITED')
  const environmentPending = busy || value?.operation_state==='PENDING' || value?.lifecycle === 'UNKNOWN' || value?.lifecycle === 'STARTING' || value?.lifecycle === 'STOPPING' || (value?.operation_state === 'UNKNOWN' && value?.recovery_state !== 'EXITED' && !(value?.active && value.recovery_state === 'OWNED_RUNNING'))
  const canResume=retainedExited&&value?.runtime_kind==='NODE_ESM'
  // 同一组动作在所有入口保持一致：重新开始会归档旧项目，继续是最右侧主操作。
  const startActions=<div className="sample-start-actions">
    {canResume&&<Button danger disabled={busy||uncertain||environmentPending} onClick={()=>setConfirm('start')}>重新开始示例</Button>}
    <Button type="primary" disabled={busy||uncertain||environmentPending} onClick={()=>setConfirm(canResume?'resume':'start')}>{canResume?'继续上次示例':'启动示例'}</Button>
  </div>
  return <section className="workbench-sample-entry" aria-label="官方环境控制">
    {environmentPending && !uncertain && <Alert className="flow-feedback" type="info" showIcon message={<>{busy&&value?.operation_state!=='PENDING'?'正在提交环境操作':value?.operation_phase&&value.operation_state==='PENDING'?phases[value.operation_phase]??'正在准备示例':value?.lifecycle === 'STARTING' ? '正在建立新实例' : value?.lifecycle === 'STOPPING' ? '正在停止实例' : '环境状态需要先核对'}{value?.operation_state==='PENDING'&&elapsed!==null&&<span className="editorial-muted"> · 已用时 {Math.floor(elapsed)} 秒</span>}</>}
      description={legacyOwnershipMissing ? '旧记录没有可核验的进程身份，重复核对无法补回依据。请在原启动终端确认旧实例已退出；原项目历史继续保留。如需全新隔离环境，可安全退出后使用新的运行目录启动界鉴。' : value?.lifecycle === 'UNKNOWN' ? value.workspace_retained ? '项目与材料已保留，但旧实例是否退出尚未确认。核对只检查受控实例身份，不会重启或终止未知进程。' : '历史环境缺少已确认的实例归属。先核对可用记录；无法确认时保留历史，不能自动接管。' : '等待这次操作的回执，无需重复启动、停止或切换。'}
      action={legacyOwnershipMissing ? undefined : <Button loading={busy} onClick={() => void reread()}>重新核对环境</Button>}/>}
    {(uncertain || syncFailed) && <Alert className="flow-feedback" type="warning" showIcon message={uncertain ? '环境操作回执尚未确认' : '环境操作已完成，页面尚未同步'} description="先重新读取状态，不重复启动、停止或切换。" action={<Button loading={busy} onClick={() => void reread()}>重新核对环境</Button>}/>}
    {!value ? <p>正在读取官方环境…</p> : !value.available ? <Alert className="flow-feedback" type="info" message={value.unavailable_reason ?? '当前环境无法启动官方示例。'} /> : !value.active ? <>
      {expanded && retainedExited ? <div className="environment-recovery">
        <StatusBadge kind="lifecycle">已确认旧实例退出</StatusBadge><h2>继续上次示例</h2><p>保留当前项目、代码与权限，重新核对登录状态和受实例变化影响的材料。</p>
        {startActions}<div className="environment-retained"><div><strong>旧项目归档保留</strong><p>检查结果与证据</p><p>原问题与修复记录</p><p>历史权限与源码记录</p></div><div><strong>新项目从零开始</strong><p>未修改的起始源码</p><p>尚未批准的权限提案</p><p>重新准备账号、资源与材料</p></div></div>
        <p className="editorial-muted">只有“重新开始示例”会归档旧项目。继续示例不会自动批准权限或执行检查。</p>
      </div> : <div className="sample-start-row">{!compact && <div className="sample-start-copy"><p>协作空间提供待确认的权限提案和测试材料，随后使用普通的验证与修复流程。</p>
      {retainedExited && <p className="editorial-muted">上次示例已退出，可以继续当前项目。登录状态需重新核对。</p>}
      </div>}{startActions}</div>}
    </> : <section className="sample-environment" aria-label="示例环境管理" data-expanded={expanded}><div className="sample-management-row"><div><h3>示例环境管理</h3>
      <p className="editorial-muted">修改代码后，到“源码改动”登记并检查。需要重新开始时，再重置示例。</p></div>
      <Space className="sample-management-actions" wrap>
        <Button danger disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('reset')}>重置官方环境</Button>
        <Button danger disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('stop')}>停止官方示例</Button>
      </Space></div>
      {value.runtime_kind!=='NODE_ESM'&&<details><summary>可选体验：证据不足时会怎样</summary><p>临时关闭决定性项目包观察，不改变应用代码。下一次检查应根据实际证据决定是否能够下结论，历史结果保持不变。</p><Button disabled={busy || uncertain || environmentPending} onClick={() => void perform(() => experienceApi.observation(Boolean(value.evidence_limited)))}>{value.evidence_limited ? '恢复完整观察条件' : '使用受限观察条件'}</Button></details>}
    </section>}
    <Modal open={confirm !== null} title={confirm === 'resume'?'继续上次示例？':confirm === 'start' ? '启动官方示例？' : confirm === 'reset' ? '重置官方环境？' : confirm === 'stop' ? '停止官方示例？' : '切换示例条件？'}
      okText={confirm === 'resume'?'继续示例':confirm === 'start' ? '启动示例' : confirm === 'reset' ? '确认重置' : '确认停止'} cancelText="取消" okButtonProps={{danger:confirm==='stop'||confirm==='reset'||(confirm==='start'&&Boolean(value?.workspace_retained))}} confirmLoading={busy} onCancel={() => { if (!busy) setConfirm(null) }}
      onOk={() => {
        if (confirm === 'start' || confirm === 'reset' || confirm === 'stop' || confirm === 'resume') {
          pendingOperation.current ??= { action: confirm, id: crypto.randomUUID() }
          const id = pendingOperation.current.id
          void perform(confirm === 'resume'?()=>experienceApi.resume(id):confirm === 'stop' ? () => experienceApi.stop(id) : confirm === 'reset' ? () => experienceApi.reset(id) : () => experienceApi.start(id))
        }
      }}>
      {confirm === 'resume'?'重新启动当前项目，保留代码、权限和可复用材料。登录状态与实例相关证明会重新核对。':confirm === 'start' ? value?.workspace_retained ? '旧项目将归档，历史检查与证据保留。新项目使用同步导出实现，权限、账号和材料从零准备，不继承旧源码修改。' : '在本机启动同步导出的起始项目。启动不会批准权限、开始检查或生成结论。' : confirm === 'reset' ? '停止并归档当前项目，重新从同步导出开始。旧权限、源码修改和材料不带入新项目，历史检查与证据保留。活动检查须先结束。' : '停止本次示例并清理临时账号状态，历史检查事实保留。下次可继续当前项目，或明确选择重新开始。活动检查须先结束。'}
    </Modal>
  </section>
}
