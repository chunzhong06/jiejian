// 官方环境只控制本机示例生命周期和源码条件；审批、材料与结果走普通产品页面。
import { Alert, Button, Modal, Select, Space } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { experienceApi, type OfficialExperienceDto, type OfficialScenarioVersion } from '../../api/experience'
import { ApiError } from '../../api/http'
import { repairsApi, repairReference, type ProjectRepair } from '../../api/repairs'

const versions = { VULNERABLE: '问题版', EVIDENCE_LIMITED: '证据受限版', FIXED: '修复版' }
export function OfficialSamplePanel({ value, onChanged, onError }: {
  value: OfficialExperienceDto | null; onChanged: (value: OfficialExperienceDto) => Promise<void>; onError: (error: ApiError) => void
}) {
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState<'start' | 'reset' | 'stop' | OfficialScenarioVersion | null>(null)
  const [repair, setRepair] = useState<ProjectRepair | null>(null)
  const [referenceId, setReferenceId] = useState<string>()
  const [uncertain, setUncertain] = useState(false)
  const [syncFailed, setSyncFailed] = useState(false)
  const pendingOperation = useRef<{ action: 'start' | 'reset' | 'stop'; id: string } | undefined>(undefined)
  const inFlight = useRef(false)
  useEffect(() => {
    let active = true
    setRepair(null); setReferenceId(undefined)
    if (value?.active && value.project_id) void repairsApi.project(value.project_id).then(state => {
      if (active && state.project_id === value.project_id) {
        setRepair(state)
        if (state.tasks.length === 1) setReferenceId(state.tasks[0].contract.repair_fingerprint)
      }
    }).catch(error => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [value, onError])
  const synchronize = async (next: OfficialExperienceDto) => {
    try { await onChanged(next); setSyncFailed(false) }
    catch (error) { setSyncFailed(true); onError(error as ApiError) }
  }
  const reread = async () => {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true)
    try {
      const next = await experienceApi.status()
      await synchronize(next)
      if (pendingOperation.current ? next.operation_id === pendingOperation.current.id && ['SUCCEEDED','FAILED'].includes(next.operation_state ?? '') : next.lifecycle && next.lifecycle !== 'UNKNOWN') {
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
  const task = repair?.tasks.find(item => item.contract.repair_fingerprint === referenceId && item.status !== 'STALE')
  const environmentPending = value?.lifecycle === 'UNKNOWN' || value?.lifecycle === 'STARTING' || value?.lifecycle === 'STOPPING' || value?.operation_state === 'PENDING' || value?.operation_state === 'UNKNOWN'
  return <section className="workbench-sample-entry" aria-label="官方环境控制">
    {environmentPending && !uncertain && <Alert type="info" showIcon message="环境状态需要先核对" description="当前不重复启动、停止或切换。" action={<Button loading={busy} onClick={() => void reread()}>重新核对环境</Button>}/>}
    {(uncertain || syncFailed) && <Alert type="warning" showIcon message={uncertain ? '环境操作回执尚未确认' : '环境操作已完成，页面尚未同步'} description="先重新读取状态，不重复启动、停止或切换。" action={<Button loading={busy} onClick={() => void reread()}>重新核对环境</Button>}/>}
    {!value ? <p>正在读取官方环境…</p> : !value.available ? <Alert type="info" message={value.unavailable_reason ?? '当前环境无法启动官方示例。'} /> : !value.active ? <>
      <p>协作空间提供待确认的权限提案和测试材料，随后使用普通的验证与修复流程。</p>
      <Button disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('start')}>{value.lifecycle === 'STOPPED' ? '重新启动示例' : '启动官方示例'}</Button>
    </> : <details className="sample-environment"><summary>示例环境 · {value.scenario_version ? versions[value.scenario_version] : '待准备'}</summary>
      <p className="editorial-muted">这里仅控制本机示例条件。权限在权限页确认，材料在验证页准备；每次切换后都需要新的检查，已有事实保持不变。</p>
      <Space wrap>
        <Button disabled={busy || uncertain || environmentPending || value.scenario_version === 'VULNERABLE'} onClick={() => setConfirm('VULNERABLE')}>切换到问题版</Button>
        <Button disabled={busy || uncertain || environmentPending || value.scenario_version === 'EVIDENCE_LIMITED'} onClick={() => setConfirm('EVIDENCE_LIMITED')}>切换到证据受限版</Button>
        {repair && repair.tasks.length > 1 && <Select aria-label="选择待修复原题" value={referenceId} onChange={setReferenceId} style={{ minWidth: 180, maxWidth: '100%' }} options={repair.tasks.filter(item => item.status !== 'STALE').map((item, index) => ({ value: item.contract.repair_fingerprint, label: `原问题 ${index + 1}` }))} />}
        <Button disabled={busy || uncertain || environmentPending || !task || value.scenario_version === 'FIXED'} onClick={() => setConfirm('FIXED')}>切换到修复版</Button>
        <Button disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('reset')}>重置官方环境</Button>
        <Button disabled={busy || uncertain || environmentPending} onClick={() => setConfirm('stop')}>停止官方示例</Button>
      </Space>
      <p className="editorial-muted">修复版只改变受控源码；是否修好由普通 Changes、原题复验和新检查的事实决定。</p>
    </details>}
    <Modal open={confirm !== null} title={confirm === 'start' ? '启动官方示例？' : confirm === 'reset' ? '重置官方环境？' : confirm === 'stop' ? '停止官方示例？' : '切换示例条件？'}
      okText={confirm === 'start' ? '启动问题版' : confirm === 'reset' ? '确认重置' : confirm === 'stop' ? '确认停止' : '确认切换'} cancelText="取消" confirmLoading={busy} onCancel={() => { if (!busy) setConfirm(null) }}
      onOk={() => {
        if (confirm === 'start' || confirm === 'reset' || confirm === 'stop') {
          pendingOperation.current ??= { action: confirm, id: crypto.randomUUID() }
          const id = pendingOperation.current.id
          void perform(confirm === 'stop' ? () => experienceApi.stop(id) : () => experienceApi.start(id))
        }
        else if (confirm && (confirm !== 'FIXED' || task)) void perform(() => experienceApi.switchVersion(confirm, confirm === 'FIXED' && task ? repairReference(task.contract) : undefined))
      }}>
      {confirm === 'start' ? '在本机启动隔离示例。启动不会批准权限、开始检查或生成结论。' : confirm === 'reset' ? '停止当前示例并创建新的隔离项目，临时账号状态随旧环境清理，历史检查事实保留。活动检查须先结束。' : confirm === 'stop' ? '停止本次示例并清理临时账号状态，历史检查事实保留。活动检查须先结束。' : '只改变当前示例条件并登记真实变化，不创建检查或写入结论。请通过普通变化与修复流程复核实现、准备材料并开始新的检查。'}
    </Modal>
  </section>
}
