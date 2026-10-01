// 官方环境只控制本机示例生命周期和源码条件；审批、材料与结果走普通产品页面。
import { Alert, Button, Modal, Space } from 'antd'
import { useRef, useState } from 'react'
import { experienceApi, type OfficialExperienceDto } from '../../api/experience'
import { ApiError } from '../../api/http'

export function OfficialSamplePanel({ value, onChanged, onError, expanded = false }: {
  expanded?: boolean
  value: OfficialExperienceDto | null; onChanged: (value: OfficialExperienceDto) => Promise<void>; onError: (error: ApiError) => void
}) {
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState<'start' | 'reset' | 'stop' | null>(null)
  const [uncertain, setUncertain] = useState(false)
  const [syncFailed, setSyncFailed] = useState(false)
  const pendingOperation = useRef<{ action: 'start' | 'reset' | 'stop'; id: string } | undefined>(undefined)
  const inFlight = useRef(false)
  const synchronize = async (next: OfficialExperienceDto) => {
    try { await onChanged(next); setSyncFailed(false) }
    catch (error) { setSyncFailed(true); onError(error as ApiError) }
  }
  const reread = async () => {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true)
    try {
      const next = value?.lifecycle === 'UNKNOWN' ? await experienceApi.reconcile() : await experienceApi.status()
      await synchronize(next)
      if ((!next.active && next.recovery_state === 'EXITED') || (next.active && next.recovery_state === 'OWNED_RUNNING') || (pendingOperation.current ? next.operation_id === pendingOperation.current.id && ['SUCCEEDED','FAILED'].includes(next.operation_state ?? '') : next.lifecycle && next.lifecycle !== 'UNKNOWN')) {
        setUncertain(false); pendingOperation.current = undefined
      }
    } catch (error) { onError(error as ApiError) }
    finally { inFlight.current = false; setBusy(false) }
  }
  const perform = async (operation: () => Promise<OfficialExperienceDto>) => {
    if (inFlight.current || uncertain) return
    inFlight.current = true; setBusy(true)
    try { const next = await operation(); setConfirm(null); pendingOperation.current = undefined; setUncertain(false); await synchronize(next) }
    catch (error) {
      onError(error as ApiError)
      setConfirm(null); setUncertain(true)
      // 可能已经生效的环境动作只回读，不能用重复切换或重置试探回执。
      try {
        const next = await experienceApi.status(); await synchronize(next)
        if (pendingOperation.current && next.operation_id === pendingOperation.current.id && ['SUCCEEDED','FAILED'].includes(next.operation_state ?? '')) { setUncertain(false); pendingOperation.current = undefined }
      } catch { /* 原错误保留，写入口继续关闭。 */ }
    } finally { inFlight.current = false; setBusy(false) }
  }
  const legacyOwnershipMissing = value?.lifecycle === 'UNKNOWN' && value.recovery_state === 'NONE'
  // 工作台保持同一个启动入口；旧实例已退出只是历史事实，详细归档说明留在环境页。
  const retainedExited = Boolean(value?.workspace_retained && value.recovery_state === 'EXITED')
  const environmentPending = value?.lifecycle === 'UNKNOWN' || value?.lifecycle === 'STARTING' || value?.lifecycle === 'STOPPING' || ((value?.operation_state === 'PENDING' || value?.operation_state === 'UNKNOWN') && value?.recovery_state !== 'EXITED' && !(value?.active && value.recovery_state === 'OWNED_RUNNING'))
  return <section className="workbench-sample-entry" aria-label="官方环境控制">
    {environmentPending && !uncertain && <Alert className="flow-feedback" type="info" showIcon message={value?.lifecycle === 'STARTING' ? '正在建立新实例' : value?.lifecycle === 'STOPPING' ? '正在停止实例' : '环境状态需要先核对'}
      description={legacyOwnershipMissing ? '旧记录没有可核验的进程身份，重复核对无法补回依据。请在原启动终端确认旧实例已退出；原项目历史继续保留。如需全新隔离环境，可安全退出后使用新的运行目录启动界鉴。' : value?.lifecycle === 'UNKNOWN' ? value.workspace_retained ? '项目与材料已保留，但旧实例是否退出尚未确认。核对只检查受控实例身份，不会重启或终止未知进程。' : '历史环境缺少已确认的实例归属。先核对可用记录；无法确认时保留历史，不能自动接管。' : '等待这次操作的回执，无需重复启动、停止或切换。'}
      action={legacyOwnershipMissing ? undefined : <Button loading={busy} onClick={() => void reread()}>重新核对环境</Button>}/>}
    {(uncertain || syncFailed) && <Alert className="flow-feedback" type="warning" showIcon message={uncertain ? '环境操作回执尚未确认' : '环境操作已完成，页面尚未同步'} description="先重新读取状态，不重复启动、停止或切换。" action={<Button loading={busy} onClick={() => void reread()}>重新核对环境</Button>}/>}
    {!value ? <p>正在读取官方环境…</p> : !value.available ? <Alert className="flow-feedback" type="info" message={value.unavailable_reason ?? '当前环境无法启动官方示例。'} /> : !value.active ? <>
      {expanded && retainedExited ? <div className="environment-recovery">
        <span className="material-badge">已确认旧实例退出</span><h2>从全新示例开始</h2><p>每次启动都从同步导出开始，创建独立的新项目。确认权限后检查起始实现，再体验一次异步优化与复验。</p>
        <Button type="primary" disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('start')}>启动示例</Button>
        <div className="environment-retained"><div><strong>旧项目归档保留</strong><p>检查结果与证据</p><p>原问题与修复记录</p><p>历史权限与源码记录</p></div><div><strong>新项目从零开始</strong><p>同步导出的起始源码</p><p>尚未批准的权限提案</p><p>重新准备账号、资源与材料</p></div></div>
        <p className="editorial-muted">旧源码修改、登录状态和材料不带入新实例。启动不会自动批准权限或执行检查。</p>
      </div> : <div className="sample-start-row"><div className="sample-start-copy"><p>协作空间提供待确认的权限提案和测试材料，随后使用普通的验证与修复流程。</p>
      {retainedExited && <p className="editorial-muted">上次示例已退出，历史记录保留。本次启动将创建全新示例。</p>}
      </div><Button type="primary" disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('start')}>启动示例</Button></div>}
    </> : <section className="sample-environment" aria-label="示例环境管理" data-expanded={expanded}><h3>示例环境管理</h3>
      <p className="editorial-muted">在 Agent 协作中继续开发与验证。这里仅管理实例和可选观察条件，检查结束不会重置项目。</p>
      <Space wrap>
        <Button disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('reset')}>重置官方环境</Button>
        <Button disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('stop')}>停止官方示例</Button>
      </Space>
      <details><summary>可选体验：证据不足时会怎样</summary><p>临时关闭决定性项目包观察，不改变应用代码。下一次检查应根据实际证据决定是否能够下结论，历史结果保持不变。</p><Button disabled={busy || uncertain || environmentPending} onClick={() => void perform(() => experienceApi.observation(Boolean(value.evidence_limited)))}>{value.evidence_limited ? '恢复完整观察条件' : '使用受限观察条件'}</Button></details>
    </section>}
    <Modal open={confirm !== null} title={confirm === 'start' ? '启动官方示例？' : confirm === 'reset' ? '重置官方环境？' : confirm === 'stop' ? '停止官方示例？' : '切换示例条件？'}
      okText={confirm === 'start' ? '启动示例' : confirm === 'reset' ? '确认重置' : '确认停止'} cancelText="取消" confirmLoading={busy} onCancel={() => { if (!busy) setConfirm(null) }}
      onOk={() => {
        if (confirm === 'start' || confirm === 'reset' || confirm === 'stop') {
          pendingOperation.current ??= { action: confirm, id: crypto.randomUUID() }
          const id = pendingOperation.current.id
          void perform(confirm === 'stop' ? () => experienceApi.stop(id) : confirm === 'reset' ? () => experienceApi.reset(id) : () => experienceApi.start(id))
        }
      }}>
      {confirm === 'start' ? value?.workspace_retained ? '旧项目将归档，历史检查与证据保留。新项目使用同步导出实现，权限、账号和材料从零准备，不继承旧源码修改。' : '在本机启动同步导出的起始项目。启动不会批准权限、开始检查或生成结论。' : confirm === 'reset' ? '停止并归档当前项目，重新从同步导出开始。旧权限、源码修改和材料不带入新项目，历史检查与证据保留。活动检查须先结束。' : '停止本次示例并清理临时账号状态，历史检查事实保留。下次启动将创建全新项目。活动检查须先结束。'}
    </Modal>
  </section>
}
