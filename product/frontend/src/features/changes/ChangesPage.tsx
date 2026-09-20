// 当前变化与原题修复：只展示服务端事实，显式提交声明并保留精确复验关联。
import { Alert, Button, Empty, Form, Input, Select, Space, Spin, Typography } from 'antd'
import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { WorkPageVisible } from '../../app/RetainedWorkPages'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { sourceChangesApi, type SourceChangeViewDto } from '../../api/sourceChanges'
import { repairsApi, repairLabels, repairReference, type ProjectRepair } from '../../api/repairs'
import { formatTimestamp } from '../../app/presentation'
import { workspaceApi } from '../../api/workspace'
import { taskDestination } from '../../app/taskDestination'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { RepairDelivery } from './RepairDelivery'
import { CheckOutlined, FileTextOutlined, CodeOutlined } from '@ant-design/icons'
import { SourceIdentityPanel } from './SourceIdentityPanel'
import './delivery.css'
import '../testing/testing.css'
import './changes.css'

const revalidationLabels = { READY: '源码与权限仍有效', NO_BASELINE: '缺少可比较的源码基线', SOURCE_STALE: '源码再次变化，请重新登记', POLICY_STALE: '权限已变化，需要重新核对', MAPPING_REVIEW_REQUIRED: '请重新确认代码实现映射' }
export function ChangesPage({ project, onError, onNavigate, onStateChanged, requestedRepair }: {
  project: ProjectDto; onError: (error: ApiError) => void; onNavigate: (path: string) => void; onStateChanged: () => unknown; requestedRepair?: string | null
}) {
  const [selectedChangeId, setSelectedChangeId] = useState<string>()
  const [detailReference, setDetailReference] = useState<string | undefined>(requestedRepair ?? undefined)
  const detailReferenceRef = useRef(detailReference)
  detailReferenceRef.current = detailReference
  const [sourceOpen, setSourceOpen] = useState(false)
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
  const continueWork = async () => {
    if (submitting.current) return
    submitting.current = true; setBusy(true)
    const current = epoch.current
    try {
      const next = await workspaceApi.current(project.project_id)
      if (epoch.current !== current) return
      if (next.project.project_id !== project.project_id) throw new ApiError('STATE_PRECONDITION', '任务所属应用不一致。')
      onNavigate(next.primary_task ? taskDestination(next.primary_task) : '/workspace')
    } catch (error) { if (epoch.current === current) onError(error as ApiError) }
    finally { submitting.current = false; setBusy(false) }
  }
  const refresh = useCallback(async () => {
    const current = ++epoch.current
    setLoading(true)
    try {
      const [items, state] = await Promise.all([sourceChangesApi.list(project.project_id), repairsApi.project(project.project_id)])
      if (selectedChangeId && !items.some(item => item.manifest.change_id === selectedChangeId)) {
        const selected = await sourceChangesApi.show(project.project_id, selectedChangeId)
        if (selected.manifest.change_id !== selectedChangeId) throw new ApiError('STATE_PRECONDITION', '所选变化记录关联不一致。')
        items.push(selected)
      }
      if (state.project_id !== project.project_id || items.some(item => item.manifest.project_id !== project.project_id)) throw new ApiError('STATE_PRECONDITION', '变化记录所属应用不一致。')
      if (epoch.current === current) { setChanges(items); setRepair(state); setFailed(false) }
    } catch (error) { if (epoch.current === current) { setChanges([]); setRepair(null); setFailed(true); onError(error as ApiError) } }
    finally { if (epoch.current === current) setLoading(false) }
  }, [project.project_id, onError, selectedChangeId])
  useEffect(() => { if (visible) void refresh(); return () => { epoch.current += 1 } }, [refresh, visible])
  useEffect(() => { setSelectedRepair(requestedRepair ?? undefined); setDetailReference(requestedRepair ?? undefined); setSelectedChangeId(undefined) }, [requestedRepair])
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
  const detailTask = repair?.tasks.find(task => task.contract.repair_fingerprint === detailReference)
  const showChange = async (changeId: string) => {
    if (submitting.current) return
    if (changes.some(item => item.manifest.change_id === changeId)) { setSelectedChangeId(changeId); setSourceOpen(false); setDetailReference(undefined); return }
    // 原题可以关联分页窗口外的批次；按精确 ID 补读，失败时留在原题，不能退到最新修改。
    const current = epoch.current
    const requestedDetail = detailReference
    submitting.current = true; setBusy(true)
    try {
      const value = await sourceChangesApi.show(project.project_id, changeId)
      if (current !== epoch.current || requestedDetail !== detailReferenceRef.current) return
      if (value.manifest.project_id !== project.project_id || value.manifest.change_id !== changeId) throw new ApiError('STATE_PRECONDITION', '变化记录关联不一致。')
      setChanges(items => [...items.filter(item => item.manifest.change_id !== changeId), value])
      setSelectedChangeId(changeId); setSourceOpen(false); setDetailReference(undefined)
    } catch (error) { if (current === epoch.current) onError(error as ApiError) }
    finally { submitting.current = false; setBusy(false) }
  }
  if (detailTask && !failed) return <RepairDelivery task={detailTask} change={changes.find(change => change.manifest.change_id === detailTask.change_id)} onNavigate={onNavigate}
    loadingChange={busy} onBack={() => { setSourceOpen(false); setDetailReference(undefined) }} onViewChange={() => { if (detailTask.change_id) void showChange(detailTask.change_id) }}/>
  const selectedStatus = selectedRepairs.length && selectedRepairs.every(task => task.status === 'VERIFIED') ? 'VERIFIED' : selectedRepairs.find(task => task.status === 'NOT_VERIFIED' || task.status === 'STALE')?.status
  const headline = failed ? '暂时无法读取代码变化' : !selectedChange ? '代码变化' : !selectedRepairs.length ? '代码变化已登记，等待检查' : selectedStatus === 'VERIFIED' ? '本批修改的原题复验已通过' : selectedStatus === 'NOT_VERIFIED' ? '修改已登记，原问题仍然存在' : selectedStatus === 'STALE' ? '修改已登记，原题依据需要重新确认' : '修改已登记，修复状态尚待确认'
  return <EditorialPage label="变化与原题复验时间流">
    <EditorialHeader eyebrow="代码变化 / 协作与验证" title={headline}><p className="editorial-muted">Coding Agent 登记修改，界鉴核对源码；独立复验后才确认修复。</p></EditorialHeader>
    {receipt && <p className="work-receipt" role="status">{receipt}</p>}
    {!loading && selectedRepair && !focusedTask && <p role="alert">未找到指定的原题修复要求。请回到原问题重新进入，当前不会替换成另一条原题。</p>}
    {failed && <p role="alert">无法完整读取变化与原题，暂不能登记或发起复验。</p>}
    <div className="change-topline">{selectedChange && <ol className="change-milestones" aria-label="本批修改的事实进展"><li className="is-complete"><span aria-hidden><CheckOutlined/></span>修改已登记</li><li className="is-complete"><span aria-hidden><CheckOutlined/></span>{selectedChange.change_set.status === 'COMPARABLE' ? '本批差异已核对' : '首次源码已记录'}</li><li className={selectedStatus === 'VERIFIED' ? 'is-complete' : ''}><span aria-hidden>{selectedStatus === 'VERIFIED' ? <CheckOutlined/> : '3'}</span>{selectedStatus === 'VERIFIED' ? '原题复验已通过' : '修复结论待确认'}</li></ol>}
    <div className="changes-toolbar"><Button disabled={busy} loading={loading} onClick={() => void refresh()}>刷新变化与修复</Button></div></div>
    {!loading && !failed && !changes.length && <Empty description="尚无代码变化记录" />}
    {selectedChange && <section className="changes-workspace" aria-label="代码变化记录">
      <nav className="change-record-index" aria-label="修改记录"><h2>修改记录</h2>{changes.map(change => <button key={change.manifest.change_id} aria-current={change.manifest.change_id === selectedChange.manifest.change_id ? 'true' : undefined} onClick={() => setSelectedChangeId(change.manifest.change_id)}><time>{formatTimestamp(change.manifest.created_at_us)}</time><strong>{change.manifest.reason}</strong><small>{change.manifest.submitted_by || '来源未提供'}</small><span>{repair?.tasks.some(item => item.change_id === change.manifest.change_id) && repair.tasks.filter(item => item.change_id === change.manifest.change_id).every(item => item.status === 'VERIFIED') ? '原题复验已通过' : change.revalidation.can_execute ? '可继续检查' : revalidationLabels[change.revalidation.status]}</span></button>)}</nav>
      <article className="change-detail" aria-label="所选代码变化">
        <header><p className="editorial-eyebrow">本批修改</p><h2>{selectedChange.manifest.reason}</h2><p className="editorial-muted">登记来源：{selectedChange.manifest.submitted_by || '来源未提供'} · {formatTimestamp(selectedChange.manifest.created_at_us)}</p></header>
        <div className="change-fact-pair">
          <section><FileTextOutlined className="change-fact-icon" aria-hidden/><div><h3>Agent 的修改说明</h3><p>{selectedChange.manifest.reason}</p><p className="editorial-muted">说明只是线索，不能替代实际源码或修复结论。</p></div></section>
          <section><CodeOutlined className="change-fact-icon" aria-hidden/><div><h3>界鉴核对的实际变化</h3><p>{selectedChange.change_set.status === 'NO_BASELINE' ? '尚无可比较的基线；本次只记录源码，不推算增删改。' : `${selectedChange.change_set.added_paths.length + selectedChange.change_set.modified_paths.length + selectedChange.change_set.removed_paths.length} 个文件发生变化 · ${selectedChange.assessment.payload.action_impacts.filter(item => item.classification === 'DIRECTLY_AFFECTED').length} 项业务动作存在直接关联。`}</p><p className="editorial-muted">{revalidationLabels[selectedChange.revalidation.status]}</p></div></section>
        </div>

        <section className="change-detail-section"><span className="change-section-number" aria-hidden="true">3</span><div>
          {selectedRepairs.length ? selectedRepairs.map(task => <section className="change-repair-item" key={task.task_reference}><div className="change-association"><div><span>原问题</span><strong>{task.comparison?.find(row => row.role === 'DENY')?.action_label ?? '原题中的权限问题'}</strong></div><div><span>本批变化</span><strong>修改已登记</strong></div><div><span>原题复验</span><strong>{repairLabels[task.status]}</strong></div></div><Space wrap><Button type="primary" size="large" onClick={() => setDetailReference(task.contract.repair_fingerprint)}>查看修复要求与进展</Button>{task.status === 'READY_TO_VERIFY' && task.change_id && <Button onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(task.change_id!)}`)}>复验原题</Button>}</Space></section>) : <><p>本次修改未关联原题修复，不能推断任何原问题已经解决。</p>{selectedChange.revalidation.can_execute && <Button type="primary" onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(selectedChange.manifest.change_id)}`)}>检查这次变化</Button>}</>}
          <Button type="link" loading={busy} onClick={() => void continueWork()}>核对现有材料</Button>
        </div></section>
        <details className="change-paths delivery-technical"><summary>查看实际文件变化</summary>{selectedChange.change_set.status === 'NO_BASELINE' ? <p>缺少基线，本次不展示差异清单。</p> : (['added_paths','modified_paths','removed_paths'] as const).map((key,index) => <section key={key}><h4>{['新增','修改','删除'][index]}</h4>{selectedChange.change_set[key].length ? <ul>{selectedChange.change_set[key].map(path => <li key={path}><code>{path}</code></li>)}</ul> : <p>无</p>}</section>)}</details>
        <details className="delivery-technical" onToggle={event => setSourceOpen(event.currentTarget.open)}><summary>查看本批源码与当前源码的对应</summary>{sourceOpen && <SourceIdentityPanel key={selectedChange.manifest.change_id} projectId={project.project_id} recordId={selectedChange.manifest.change_id} kind="source-changes" onNavigate={onNavigate}/>}</details>
        <p className="delivery-footer">这批修改已登记，无需重复填写。登记说明、实际变化和复验结果分别保留。</p>
      </article>
    </section>}
    <details className="change-manual-entry"><summary>Agent 连接与手动接管</summary><p>Agent 通过 MCP 登记后无需重复填写。连接本身不代表正在修改代码。</p><Button onClick={() => onNavigate('/tools')}>Agent 连接与授权</Button>{registration}</details>
    {repair?.tasks.filter(task => !task.change_id || !changes.some(change => change.manifest.change_id === task.change_id)).map(task => <section key={task.task_reference} className="repair-context"><div><strong>{task.comparison?.find(row => row.role === 'DENY')?.action_label ?? '原题修复要求'}</strong><p>{repairLabels[task.status]}</p></div><Button onClick={() => setDetailReference(task.contract.repair_fingerprint)}>查看修复要求与进展</Button></section>)}
  </EditorialPage>
}
