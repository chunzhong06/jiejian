// 官方示例仅提供明确用户动作；批准、准备和检查分别经过普通产品流程。
import { Alert, Button, Modal, Select, Space, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { experienceApi, type OfficialExperienceDto, type OfficialScenarioVersion } from '../../api/experience'
import { ApiError } from '../../api/http'
import { repairsApi, repairReference, type ProjectRepair } from '../../api/repairs'

const versions = { VULNERABLE: '问题版', EVIDENCE_LIMITED: '观察受限版', FIXED: '修复版' }
const pendingLabels: Record<string, string> = {
  HUMAN_BOUNDARY_APPROVAL_REQUIRED: '请先审阅并批准示例权限。', HUMAN_IMPLEMENTATION_REBIND_REQUIRED: '代码已变化，请在业务边界中重新确认实现映射。',
  REGISTER_SOURCE_CHANGE: '请先登记当前代码变化。', TEST_IDENTITY_SELECTION_REQUIRED: '存在多个测试账号，请先确认使用的账号。',
  PREPARATION_INCOMPLETE: '测试材料尚未齐备，请查看准备条件。', PREPARE_CURRENT_MATERIALS: '请确认当前代码实现，再准备这一版本的测试材料。',
}
export function OfficialSamplePanel({ value, onChanged, onError, onNavigate }: {
  value: OfficialExperienceDto | null; onChanged: (value: OfficialExperienceDto) => Promise<void>; onError: (error: ApiError) => void; onNavigate: (path: string) => void
}) {
  const [busy, setBusy] = useState(false)
  const [confirm, setConfirm] = useState<'start' | 'stop' | OfficialScenarioVersion | null>(null)
  const [repair, setRepair] = useState<ProjectRepair | null>(null)
  const [referenceId, setReferenceId] = useState<string>()
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
  const perform = async (operation: () => Promise<OfficialExperienceDto>) => {
    if (inFlight.current) return
    inFlight.current = true; setBusy(true)
    try { await onChanged(await operation()); setConfirm(null) }
    catch (error) {
      onError(error as ApiError)
      // 操作可能已经生效，只回读状态；不自动再次启动、切换或准备。
      try { await onChanged(await experienceApi.status()) } catch { /* 原错误保持为主要提示。 */ }
    } finally { inFlight.current = false; setBusy(false) }
  }
  const task = repair?.tasks.find(item => item.contract.repair_fingerprint === referenceId && item.status !== 'STALE')
  const changeId = value?.scenario_version === 'FIXED' ? value.repair_change_id : value?.vulnerable_change_id
  return <section className="workbench-sample-entry" aria-label="官方示例">
    <Typography.Title level={3}>{value?.display_name ?? '协作空间'}</Typography.Title>
    <Typography.Paragraph>用项目负责人和普通成员的权限差异，观察后台导出、证据不足和修复后的真实结果。</Typography.Paragraph>
    {!value ? <Typography.Text type="secondary">正在读取示例状态</Typography.Text> : !value.available ? <Alert type="info" message={value.unavailable_reason ?? '当前环境无法启动官方示例。'} /> : !value.active ?
      <Button type="primary" onClick={() => setConfirm('start')}>启动官方示例</Button> : <>
        <Typography.Paragraph role="status">当前为{value.scenario_version ? versions[value.scenario_version] : '待准备版本'} · {value.scenario_prepared ? '材料已准备' : '材料待确认'}</Typography.Paragraph>
        {(value.pending_tasks ?? []).map(code => <Alert key={code} type="info" showIcon message={pendingLabels[code] ?? '请查看当前准备待办。'} />)}
        <Space wrap>
          <Button disabled={busy} onClick={() => void perform(async () => { await experienceApi.boundaryProposal(); onNavigate('/permissions'); return experienceApi.status() })}>审阅示例权限</Button>
          <Button loading={busy} onClick={() => void perform(experienceApi.prepare)}>准备示例材料</Button>
          <Button disabled={busy} onClick={() => onNavigate('/permissions')}>确认实现映射</Button>
          <Button type="primary" disabled={busy || !value.scenario_prepared} onClick={() => onNavigate(`/tests${changeId ? `?change_id=${encodeURIComponent(changeId)}` : ''}`)}>进入示例检查</Button>
        </Space>
        <details><summary>观察条件与示例修复</summary>
          <Typography.Paragraph type="secondary">每次切换都会登记真实变化，需确认映射并重新准备；已有检查结果保持不变。</Typography.Paragraph>
          <Space wrap>
            <Button disabled={busy || value.scenario_version === 'EVIDENCE_LIMITED'} onClick={() => setConfirm('EVIDENCE_LIMITED')}>切换到观察受限版</Button>
            <Button disabled={busy || value.scenario_version === 'VULNERABLE'} onClick={() => setConfirm('VULNERABLE')}>切换到问题版</Button>
            {repair && repair.tasks.length > 1 && <Select aria-label="选择待修复原题" value={referenceId} onChange={setReferenceId} style={{ minWidth: 180 }} options={repair.tasks.filter(item => item.status !== 'STALE').map((item, index) => ({ value: item.contract.repair_fingerprint, label: `原问题 ${index + 1}` }))} />}
            <Button disabled={busy || !task || value.scenario_version === 'FIXED'} onClick={() => setConfirm('FIXED')}>应用示例修复</Button>
          </Space>
          <Typography.Paragraph type="secondary">示例修复只切换受控示例代码，不会调用外部 Coding Agent，也不会预先写入修复结论。</Typography.Paragraph>
        </details>
        <Button disabled={busy} onClick={() => setConfirm('stop')}>停止官方示例</Button>
      </>}
    <Modal open={confirm !== null} title={confirm === 'start' ? '启动官方示例？' : confirm === 'stop' ? '停止官方示例？' : confirm === 'FIXED' ? '应用示例修复？' : '切换示例条件？'}
      okText={confirm === 'start' ? '启动问题版' : confirm === 'stop' ? '确认停止' : '确认切换'} cancelText="取消" confirmLoading={busy} onCancel={() => { if (!busy) setConfirm(null) }}
      onOk={() => {
        if (confirm === 'start') void perform(experienceApi.start)
        else if (confirm === 'stop') void perform(experienceApi.stop)
        else if (confirm && (confirm !== 'FIXED' || task)) void perform(() => experienceApi.switchVersion(confirm, confirm === 'FIXED' && task ? repairReference(task.contract) : undefined))
      }}>
      {confirm === 'start' ? '界鉴将在本机启动隔离示例。启动不会批准权限、开始检查或生成结论。' : confirm === 'stop' ? '停止本次示例并清理其临时账号状态，历史检查事实保留。活动检查必须先结束。' : '只改变当前示例条件并登记变化。重新确认准备后，需要发起新的完整检查。'}
    </Modal>
  </section>
}
