// 当前变化与原题修复：只展示服务端事实，显式提交声明并保留精确复验关联。
import { Alert, Button, Empty, Form, Input, Select, Space, Spin, Typography } from 'antd'
import { useCallback, useEffect, useRef, useState } from 'react'
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
  const [changes, setChanges] = useState<SourceChangeViewDto[]>([])
  const [repair, setRepair] = useState<ProjectRepair | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [busy, setBusy] = useState(false)
  const [uncertain, setUncertain] = useState(false)
  const [selectedRepair, setSelectedRepair] = useState<string | undefined>(requestedRepair ?? undefined)
  const [form] = Form.useForm<{ reason: string; paths?: string }>()
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
  useEffect(() => { void refresh(); return () => { epoch.current += 1 } }, [refresh])
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
      form.resetFields(); await refresh(); void onStateChanged()
    } catch (error) {
      if (epoch.current === current) { setUncertain(true); onError(error as ApiError); await refresh() }
    } finally { submitting.current = false; setBusy(false) }
  }
  const focusedTask = repair?.tasks.find((task) => task.contract.repair_fingerprint === selectedRepair) ?? repair?.tasks.find((task) => task.task_reference === repair.primary_task_reference)
  const repairSection = (task: NonNullable<ProjectRepair['tasks']>[number]) => <section key={task.task_reference} className="repair-flow-entry" aria-label="原题修复状态">
    <h3>{task.status === 'VERIFIED' ? '原问题已经通过复验，要求保留的合法能力未受影响' : repairLabels[task.status]}</h3>
    <p>沿用原权限、测试账号、资源与证据标准；新的检查单独保存，原问题不会被覆盖。</p>
    <RepairComparison rows={task.comparison ?? []}/>
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
  return <EditorialPage label="变化与原题复验时间流">
    <EditorialHeader eyebrow="变化与修复" title={focusedTask ? repairLabels[focusedTask.status] : '代码改过以后，继续检查原来的权限'}><p className="editorial-muted">Agent 的说明是线索。界鉴重新核对源码，沿原题验证修改。</p></EditorialHeader>
    {failed && <p role="alert">无法完整读取变化与原题，暂不能登记或发起复验。</p>}
    <Space wrap><Button disabled={busy} onClick={() => void refresh()}>刷新变化与修复</Button>{loading && <Spin />}</Space>
    {focusedTask && <section className="repair-origin-context"><h2>这次要解决的原问题</h2><p>{focusedTask.comparison?.find((row) => row.role === 'DENY')?.action_label ?? '原题合同中的权限问题'} · {repairLabels[focusedTask.status]}</p><Button onClick={() => onNavigate(`/tests?run_id=${encodeURIComponent(focusedTask.contract.source_run_id)}`)}>回看原问题与证据</Button>{focusedTask.status === 'READY_TO_VERIFY' && focusedTask.change_id && <Button type="primary" onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(focusedTask.change_id!)}`)}>复验原题</Button>}</section>}
    {focusedTask?.status !== 'VERIFIED' && registration}
    {!loading && !failed && !changes.length && <Empty description="尚无代码变化记录" />}
    <ol className="change-timeline">{changes.map(change => <li key={change.manifest.change_id} className="change-event">
      <div className="change-event-time"><time>{formatTimestamp(change.manifest.created_at_us)}</time><span>{change.manifest.submitted_by}</span></div><div className="change-event-rail" aria-hidden="true"><i /></div>
      <article className="change-event-content"><p className="editorial-eyebrow">修改声明 → 真实源码核对</p><Typography.Title level={4}>{change.manifest.reason}</Typography.Title>
        <Typography.Paragraph>{revalidationLabels[change.revalidation.status]}</Typography.Paragraph>
        <p>界鉴实际核对：{change.change_set.added_paths.length + change.change_set.modified_paths.length + change.change_set.removed_paths.length} 个文件发生变化；{change.assessment.payload.action_impacts.filter(item => item.classification === 'DIRECTLY_AFFECTED').length} 项业务动作受到直接影响。</p>
        <Space wrap>
          {change.revalidation.can_execute ? <Button onClick={() => onNavigate(`/tests?change_id=${encodeURIComponent(change.manifest.change_id)}`)}>检查这次变化</Button>
            : <Button onClick={() => onNavigate(change.revalidation.status === 'MAPPING_REVIEW_REQUIRED' || change.revalidation.status === 'POLICY_STALE' ? '/permissions' : '/tests')}>处理准备条件</Button>}
        </Space>
        <details><summary>Agent 声明的线索（不等于实际变化）</summary><p>修改说明：{change.manifest.reason}</p></details>
        <details className="change-paths"><summary>查看实际文件变化</summary>{(['added_paths', 'modified_paths', 'removed_paths'] as const).map((key, index) => <section key={key}><Typography.Text strong>{['新增', '修改', '删除'][index]}</Typography.Text><ul>{change.change_set[key].map(path => <li key={path}><Typography.Text code>{path}</Typography.Text></li>)}</ul></section>)}</details>
        {repair?.tasks.filter((task) => task.change_id === change.manifest.change_id).map(repairSection)}
      </article>
    </li>)}</ol>
    {focusedTask?.status === 'VERIFIED' && <details><summary>登记新的代码变化</summary>{registration}</details>}
    {repair?.tasks.filter((task) => !task.change_id || !changes.some((change) => change.manifest.change_id === task.change_id)).map(repairSection)}
  </EditorialPage>
}
