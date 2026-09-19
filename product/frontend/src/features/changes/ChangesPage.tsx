// 当前变化与原题修复：只展示服务端事实，显式提交声明并保留精确复验关联。
import { Alert, Button, Empty, Form, Input, Select, Space, Spin, Typography } from 'antd'
import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { sourceChangesApi, type SourceChangeViewDto } from '../../api/sourceChanges'
import { repairsApi, repairLabels, repairReference, type ProjectRepair } from '../../api/repairs'
import { formatTimestamp } from '../../app/presentation'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { RepairComparison } from './RepairComparison'
import '../testing/testing.css'
import './changes.css'

const revalidationLabels = { READY: '源码与权限仍有效', NO_BASELINE: '缺少可比较的源码基线', SOURCE_STALE: '源码再次变化，请重新登记', POLICY_STALE: '权限已变化，需要重新核对', MAPPING_REVIEW_REQUIRED: '请重新确认代码实现映射' }
export function ChangesPage({ project, onError, onNavigate, onStateChanged, requestedRepair }: {
  project: ProjectDto; onError: (error: ApiError) => void; onNavigate: (path: string) => void; onStateChanged: () => unknown; requestedRepair?: string | null
}) {
  const [selectedChangeId, setSelectedChangeId] = useState<string>()
  const [changes, setChanges] = useState<SourceChangeViewDto[]>([])
  const [repair, setRepair] = useState<ProjectRepair | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [receipt, setReceipt] = useState<string>()
  const [selectedRepair, setSelectedRepair] = useState<string | undefined>(requestedRepair ?? undefined)
  const [form] = Form.useForm<{ reason: string; paths?: string }>()
  const visible = useContext(WorkPageVisible)
  const epoch = useRef(0)
  const submitting = useRef(false)
  const refresh = useCallback(async () => {
    const current = ++epoch.current
    setLoading(true)
    try {
      const [items, state] = await Promise.all([sourceChangesApi.list(project.project_id), repairsApi.project(project.project_id)])
      if (state.project_id !== project.project_id || items.some(item => item.manifest.project_id !== project.project_id)) throw new ApiError('STATE_PRECONDITION', '变化记录所属应用不一致。')
      if (epoch.current === current) { setChanges(items); setRepair(state); setFailed(false) }
    } catch (error) { if (epoch.current === current) { setChanges([]); setRepair(null); setFailed(true); onError(error as ApiError) } }
    finally { if (epoch.current === current) setLoading(false) }
  }, [project.project_id, onError])
  useEffect(() => { if (visible) void refresh(); return () => { epoch.current += 1 } }, [refresh, visible])
  useEffect(() => { setSelectedRepair(requestedRepair ?? undefined); setSelectedChangeId(undefined) }, [requestedRepair])
  useEffect(() => {
    if (!visible || busy) return
    let reads = 0, pending = false
    const timer = window.setInterval(async () => {
      if (pending || document.visibilityState !== 'visible') return
      if (reads >= 60) { window.clearInterval(timer); return }
      reads += 1; pending = true
      try { await refresh() } finally { pending = false }
    }, 5_000)
    return () => window.clearInterval(timer)
  }, [visible, busy, refresh])
  const submit = async (values: { reason: string; paths?: string }) => {
    if (submitting.current || failed || uncertain) return
    const task = repair?.tasks.find(item => item.contract.repair_fingerprint === selectedRepair)
    if (selectedRepair && (!task || task.status === 'STALE')) { onError(new ApiError('STATE_PRECONDITION', '原题引用不可用，请刷新后核对。')); return }
    const paths = (values.paths ?? '').split(/\r?\n/).map(value => value.trim()).filter(Boolean)
    if (paths.length > 128) { onError(new ApiError('INPUT_INVALID', '最多填写 128 个相对路径。')); return }
    submitting.current = true; setBusy(true)
    const current = epoch.current
    try {
      const result = await sourceChangesApi.submit(project.project_id, values.reason.trim(), paths, task ? repairReference(task.contract) : null)
      if (epoch.current !== current) return
      if (result.manifest.project_id !== project.project_id) throw new ApiError('STATE_PRECONDITION', '登记结果所属应用不一致。')
      // 登记已经确认；后续只读同步失败不能撤销回执或诱导再次登记。
      form.resetFields(); setReceipt('代码变化已登记，界鉴将按实际源码继续核对。'); await refresh()
      try { await onStateChanged() } catch (error) { onError(error as ApiError) }
    } catch (error) {
      if (epoch.current === current) { setUncertain(true); onError(error as ApiError); await refresh() }
    } finally { submitting.current = false; setBusy(false) }
  }
  const focusedTask = selectedRepair ? repair?.tasks.find((task) => task.contract.repair_fingerprint === selectedRepair) : repair?.tasks.find((task) => task.task_reference === repair.primary_task_reference)
  const repairSection = (task: NonNullable<ProjectRepair['tasks']>[number]) => <section key={task.task_reference} className="repair-flow-entry" aria-label="原题修复状态">
    <h3>{task.status === 'VERIFIED' ? '原问题已经通过复验，要求保留的合法能力未受影响' : repairLabels[task.status]}</h3>
    <p>沿用原权限、测试账号、资源与证据标准；新的检查单独保存，原问题不会被覆盖。</p>
    <RepairComparison rows={task.comparison ?? []} sourceRunId={task.contract.source_run_id} onNavigate={onNavigate}/>
    <Space wrap><Button onClick={() => onNavigate(`/tests?run_id=${encodeURIComponent(task.contract.source_run_id)}`)}>查看原问题</Button>
      {task.run_id && <Button onClick={() => onNavigate(`/tests?run_id=${encodeURIComponent(task.run_id!)}`)}>查看复验结果</Button>}
      {task.status === 'READY_TO_VERIFY' && task.change_id && task.task_reference !== focusedTask?.task_reference && <Button onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(task.change_id!)}`)}>复验这条原题</Button>}
    </Space>
  </section>
  const registration = <section className="change-registration" aria-label="登记代码变化">
      <Typography.Title level={3}>登记代码变化</Typography.Title>
      <Typography.Paragraph type="secondary">修改说明与文件路径只是线索，实际变化和完整检查范围由界鉴重新计算。</Typography.Paragraph>
      {uncertain && <Alert showIcon type="warning" message="上次登记回执未确认。请先查看下方变化记录，避免重复登记。" action={<Button disabled={loading || failed} onClick={() => setUncertain(false)}>已核对记录</Button>} />}
      <Form form={form} layout="vertical" onFinish={values => void submit(values)} disabled={busy || loading || failed || uncertain}>
        <Form.Item name="reason" label="修改说明" rules={[{ required: true, whitespace: true, message: '请说明这次修改。' }, { max: 512 }]}><Input.TextArea maxLength={512} autoSize={{ minRows: 2, maxRows: 5 }} /></Form.Item>
        <Form.Item label="关联原题（可选）"><Select allowClear value={selectedRepair} onChange={setSelectedRepair} placeholder="普通代码变化" options={repair?.tasks.filter(task => task.status !== 'STALE').map((task, index) => ({ value: task.contract.repair_fingerprint, label: `原问题 ${index + 1} · ${repairLabels[task.status]}` }))} /></Form.Item>
        <Form.Item name="paths" label="涉及文件（可选，每行一个相对路径）"><Input.TextArea maxLength={32768} autoSize={{ minRows: 2, maxRows: 5 }} /></Form.Item>
        <Button type={focusedTask?.status === 'READY_TO_VERIFY' ? 'default' : 'primary'} htmlType="submit" loading={busy}>登记并核对实际变化</Button>
      </Form>
    </section>
  const selectedChange = changes.find(item => item.manifest.change_id === selectedChangeId)
    ?? changes.find(item => item.manifest.change_id === focusedTask?.change_id) ?? changes[0]
  const selectedRepairs = repair?.tasks.filter(item => item.change_id === selectedChange?.manifest.change_id) ?? []
  return <EditorialPage label="变化与原题复验时间流">
    <EditorialHeader eyebrow="协作与验证" title="代码变化"><p className="editorial-muted">Coding Agent 通过 MCP 登记修改，界鉴核对实际变化。</p></EditorialHeader>
    {receipt && <p className="work-receipt" role="status">{receipt}</p>}
    {!loading && selectedRepair && !focusedTask && <p role="alert">未找到指定的原题修复要求。请回到原问题重新进入，当前不会替换成另一条原题。</p>}
    {failed && <p role="alert">无法完整读取变化与原题，暂不能登记或发起复验。</p>}
    <div className="changes-toolbar"><span className="editorial-muted">修改声明、实际源码与复验结论分别保留。</span><Button disabled={busy} loading={loading} onClick={() => void refresh()}>刷新变化与修复</Button></div>
    {!loading && !failed && !changes.length && <Empty description="尚无代码变化记录" />}
    {selectedChange && <section className="changes-workspace" aria-label="代码变化记录">
      <nav className="change-record-index" aria-label="修改记录"><h2>修改记录</h2>{changes.map(change => <button key={change.manifest.change_id} aria-current={change.manifest.change_id === selectedChange.manifest.change_id ? 'true' : undefined} onClick={() => setSelectedChangeId(change.manifest.change_id)}><time>{formatTimestamp(change.manifest.created_at_us)}</time><strong>{change.manifest.reason}</strong><small>{change.manifest.submitted_by || '来源未提供'}</small><span>{repair?.tasks.find(item => item.change_id === change.manifest.change_id)?.status === 'VERIFIED' ? '原题复验已通过' : change.revalidation.can_execute ? '可继续检查' : revalidationLabels[change.revalidation.status]}</span></button>)}</nav>
      <article className="change-detail" aria-label="所选代码变化">
        <header><h2>{selectedChange.manifest.reason}</h2><p className="editorial-muted">登记来源：{selectedChange.manifest.submitted_by || '来源未提供'} · {formatTimestamp(selectedChange.manifest.created_at_us)}</p></header>
        <section className="change-detail-section"><span className="change-section-number" aria-hidden="true">1</span><div><h3>Agent 登记的修改</h3><p>{selectedChange.manifest.reason}</p><p className="editorial-muted">这段说明是登记声明，实际修改以下方源码核对为准。</p></div></section>
        <section className="change-detail-section"><span className="change-section-number" aria-hidden="true">2</span><div><h3>界鉴核对的实际变化</h3><p>{selectedChange.change_set.added_paths.length + selectedChange.change_set.modified_paths.length + selectedChange.change_set.removed_paths.length} 个文件发生变化 · {selectedChange.assessment.payload.action_impacts.filter(item => item.classification === 'DIRECTLY_AFFECTED').length} 项业务动作受到直接影响。</p><p>{revalidationLabels[selectedChange.revalidation.status]}</p><details className="change-paths"><summary>查看实际文件变化</summary>{(['added_paths','modified_paths','removed_paths'] as const).map((key,index) => <section key={key}><h4>{['新增','修改','删除'][index]}</h4>{selectedChange.change_set[key].length ? <ul>{selectedChange.change_set[key].map(path => <li key={path}><code>{path}</code></li>)}</ul> : <p>无</p>}</section>)}</details></div></section>
        <section className="change-detail-section"><span className="change-section-number" aria-hidden="true">3</span><div><h3>{selectedRepairs.length ? '关联的原问题与复验' : '检查这次变化'}</h3>
          {selectedRepairs.length ? selectedRepairs.map(task => <section className="change-repair-item" key={task.task_reference}><p><strong>{task.comparison?.find(row => row.role === 'DENY')?.action_label ?? '原题合同中的权限问题'}</strong></p><p>{repairLabels[task.status]}</p><p className="editorial-muted">原权限、测试账号、资源与证据标准保持不变。</p><Space wrap>{task.status === 'READY_TO_VERIFY' && task.change_id && <Button type="primary" onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(task.change_id!)}`)}>复验原题</Button>}<Button type="link" onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(task.contract.source_run_id)}`)}>回看原问题</Button>{task.run_id && <Button type="link" onClick={() => onNavigate(`/history?run_id=${encodeURIComponent(task.run_id!)}`)}>查看复验结果</Button>}</Space><details><summary>查看原题要求与全部合法能力</summary>{repairSection(task)}</details></section>) : <><p>本次修改未关联原题修复，按当前权限检查实际变化。</p>{selectedChange.revalidation.can_execute && <Button type="primary" onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(selectedChange.manifest.change_id)}`)}>检查这次变化</Button>}</>}
          {!selectedChange.revalidation.can_execute && <Button onClick={() => onNavigate(selectedChange.revalidation.status === 'MAPPING_REVIEW_REQUIRED' || selectedChange.revalidation.status === 'POLICY_STALE' ? '/permissions' : '/tests')}>处理准备条件</Button>}
        </div></section>
      </article>
    </section>}
    <details className="change-manual-entry"><summary>Agent 连接与手动接管</summary><p>Agent 通过 MCP 登记后无需重复填写。连接本身不代表正在修改代码。</p><Button onClick={() => onNavigate('/tools')}>Agent 连接与授权</Button>{registration}</details>
    {repair?.tasks.filter(task => !task.change_id || !changes.some(change => change.manifest.change_id === task.change_id)).map(repairSection)}
  </EditorialPage>
}
