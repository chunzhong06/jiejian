// 任务目标、接收事实与交付入口就地组织；复制仅复制说明，不伪造派发或接收。
import { Alert, Button, Form, Input, Popconfirm, Tag } from 'antd'
import { useMemo, useRef, useState } from 'react'
import { ApiError } from '../../api/http'
import { developmentApi, newOperationId, type DevelopmentView, type OperationKind } from '../../api/development'
import { formatTimestamp } from '../../app/presentation'
import './development.css'
import { clearPendingOperation, readPendingOperation, savePendingOperation } from './pendingOperations'

export function DevelopmentTaskPanel({ projectId, value, disabled, onChanged, onError, onSelectChange, onNavigate }: {
  projectId: string; value: DevelopmentView | null; disabled: boolean; onChanged: () => Promise<unknown>
  onError: (error: ApiError) => void; onSelectChange: (change: string) => void
  onNavigate: (path: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const restored = useMemo(() => readPendingOperation(projectId, 'task'), [projectId])
  const restoredRuntime = useMemo(() => readPendingOperation(projectId, 'runtime'), [projectId])
  const [uncertain, setUncertain] = useState(!!restored)
  const pending = useRef<{ kind: OperationKind; id: string; body?: string } | undefined>(restored ? { kind: restored.kind as OperationKind, id: restored.operation_id } : undefined)
  const [form] = Form.useForm<{ title: string; goal: string }>()
  const locked = useRef(false)
  const runtimePending = useRef<{ id: string; delivery: string; version: number } | null>(restoredRuntime?.delivery_id && restoredRuntime.expected_version ? { id: restoredRuntime.operation_id, delivery: restoredRuntime.delivery_id, version: restoredRuntime.expected_version } : null)
  const [runtimeUncertain, setRuntimeUncertain] = useState(!!runtimePending.current)
  const transact = async (kind: 'CREATE' | 'REVISE' | 'CLOSE' | 'CANCEL', body: object, submit: (id: string) => Promise<{ project_id: string; operation_id: string }>) => {
    if (locked.current || disabled) return
    const serialized = JSON.stringify(body)
    if (pending.current && (pending.current.kind !== kind || pending.current.body !== undefined && pending.current.body !== serialized)) {
      onError(new ApiError('STATE_PRECONDITION', '请先核对上一次操作回执。')); return
    }
    pending.current ??= { kind, id: newOperationId(), body: serialized }
    if (!savePendingOperation(projectId, 'task', { kind, operation_id: pending.current.id })) { onError(new ApiError('BROWSER_STORAGE_UNAVAILABLE', '浏览器无法保存操作定位，请允许本页会话存储后重试。')); return }
    locked.current = true; setBusy(true)
    let replied = false
    try {
      const receipt = await submit(pending.current.id)
      replied = true
      if (receipt.project_id !== projectId || receipt.operation_id !== pending.current.id) throw new ApiError('STATE_PRECONDITION', '任务回执关联不一致。')
      clearPendingOperation(projectId, 'task', pending.current.id)
      pending.current = undefined; setUncertain(false); setEditing(false); setMessage('任务记录已保存。')
      await onChanged()
    } catch (error) {
      if (!replied && pending.current && error instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID', 'APPLICATION_ANALYSIS_NOT_AUTHORIZED', 'PROJECT_NOT_FOUND'].includes(error.code)) { clearPendingOperation(projectId, 'task', pending.current.id); pending.current = undefined }
      setUncertain(!!pending.current)
      onError(error as ApiError)
    } finally { locked.current = false; setBusy(false) }
  }
  const queryReceipt = async () => {
    const operation = pending.current
    if (!operation || locked.current) return
    locked.current = true; setBusy(true)
    try {
      const receipt = await developmentApi.receipt(projectId, operation.kind, operation.id)
      if (!receipt) { setMessage('尚未读到成功回执。可继续查询，或重新填写后沿用同一操作标识提交。'); setEditing(true); return }
      if (receipt.operation_id !== operation.id || receipt.project_id !== projectId) throw new ApiError('STATE_PRECONDITION', '任务回执关联不一致。')
      clearPendingOperation(projectId, 'task', operation.id)
      pending.current = undefined; setUncertain(false); setEditing(false); setMessage('已找回本次操作回执。'); await onChanged()
    } catch (error) { onError(error as ApiError) } finally { locked.current = false; setBusy(false) }
  }
  const save = (fields: { title: string; goal: string }) => {
    const clean = { title: fields.title.trim(), goal: fields.goal.trim() }
    if (value && pending.current?.kind !== 'CREATE') void transact('REVISE', { ...clean, version: value.task.version }, id => developmentApi.revise(projectId, value.task.task_id, { ...clean, operation_id: id, expected_version: value.task.version }))
    else void transact('CREATE', clean, id => developmentApi.create(projectId, { ...clean, operation_id: id }))
  }
  const copy = async () => {
    if (!value) return
    try {
      await navigator.clipboard.writeText(`请通过界鉴 jiejian MCP 完成这项任务。\n应用：${projectId}\n任务：${value.task.task_id}\n上下文：${value.context.context_id}\n标题：${value.context.title}\n目标：${value.context.goal}\n先调用 jiejian_task_show、jiejian_task_context，按其中的已批准权限引用读取要求；仅在当前上下文没有接收回执时，用稳定 operation_id 调用 jiejian_task_accept。已有接收回执时直接继续，不重复接收。读取或复制不等于接收。\n整批修改完成后调用 jiejian_change_submit，携带 task_id、context_id、最新 expected_version 和稳定 operation_id。响应不明确先调用 jiejian_receipt_show 查询原键。\n检查必须保留全部权限要求。不要自行批准权限，不把客户端自测当作界鉴结论。普通功能目标仍需另行验证。`)
      setMessage('任务说明已复制。尚未发送给客户端，也不会自动标为接收。')
    } catch { onError(new ApiError('CLIPBOARD_UNAVAILABLE', '复制失败，请确认浏览器允许访问剪贴板。')) }
  }
  const loadRuntime = async () => {
    const delivery = value?.deliveries[0]
    if (!value || !delivery || locked.current) return
    runtimePending.current ??= { id: newOperationId(), delivery: delivery.delivery_id, version: value.task.version }
    const operation = runtimePending.current
    if (!savePendingOperation(projectId, 'runtime', { kind: 'LOAD_RUNTIME', operation_id: operation.id, delivery_id: operation.delivery, expected_version: operation.version })) { onError(new ApiError('BROWSER_STORAGE_UNAVAILABLE', '浏览器无法保存操作定位，请允许本页会话存储后重试。')); return }
    locked.current = true; setBusy(true)
    try {
      const result = await developmentApi.loadRuntime(projectId, operation.delivery, { operation_id: operation.id, expected_version: operation.version })
      if (result.project_id !== projectId || result.operation_id !== operation.id || result.delivery_id !== operation.delivery) throw new ApiError('STATE_PRECONDITION', '运行加载回执关联不一致。')
      if (result.status === 'SUCCEEDED') { clearPendingOperation(projectId, 'runtime', operation.id); runtimePending.current = null; setRuntimeUncertain(false); setMessage('这批代码已加载到受控运行实例。检查结果仍需独立形成。'); await onChanged() }
      else if (result.status === 'FAILED') { clearPendingOperation(projectId, 'runtime', operation.id); runtimePending.current = null; setRuntimeUncertain(false); setMessage('这次加载未完成，请在应用与环境中核对运行状态。'); await onChanged() }
      else { setRuntimeUncertain(true); setMessage('运行加载尚未确认，核对原回执不会重复启动实例。') }
    } catch (error) { setRuntimeUncertain(!!runtimePending.current); onError(error as ApiError) }
    finally { locked.current = false; setBusy(false) }
  }
  const latest = value?.deliveries[0]
  const verification = value?.latest_verification
  const nextAction = runtimeUncertain ? <Button type="primary" loading={busy} onClick={() => void loadRuntime()}>核对加载回执</Button>
    : !latest ? <Button type="primary" disabled={disabled || busy || uncertain} onClick={() => void copy()}>复制任务说明</Button>
    : verification?.run_id ? <Button type="primary" disabled={disabled || busy} onClick={() => onNavigate((verification.verdict ? '/history' : '/tests') + '?run_id=' + encodeURIComponent(verification.run_id!))}>{verification.verdict ? '查看本批检查结果' : '查看检查进度'}</Button>
    : value?.runtime_state === 'NOT_LOADED' ? <Button type="primary" loading={busy} disabled={disabled || uncertain} onClick={() => void loadRuntime()}>加载这批代码运行</Button>
    : <Button type="primary" disabled={disabled || busy || uncertain} onClick={() => onNavigate('/tests?change_id=' + encodeURIComponent(latest.change_id))}>准备与检查这批交付</Button>
  return <section className="development-task" aria-label="当前开发任务">
    <header className="development-task-heading"><div><p className="editorial-eyebrow">当前开发任务</p><h2>{value?.context.title ?? '接下来，准备修改什么？'}</h2></div>
      <div className="development-task-actions">{value && !editing && nextAction}
        {!value && !editing && <Button type="primary" disabled={disabled || busy} onClick={() => { form.resetFields(); setEditing(true) }}>创建开发任务</Button>}</div></header>
    {value ? <><p className="development-goal">{value.context.goal}</p><div className="development-context-line"><Tag>{value.acceptance ? '已有接收回执' : '等待客户端接收'}</Tag><span>沿用 {value.context.permission_refs.length} 条已批准权限</span><span>目标修订 {value.task.revision}</span>{value.acceptance && <span>{value.acceptance.client_name} · {formatTimestamp(value.acceptance.accepted_at_us)}</span>}</div>
      {latest && <p className="development-runtime-note">{value.runtime_state === 'MATCHED' ? '当前运行已对应这批源码。' : value.runtime_state === 'NOT_LOADED' ? '修改已登记，当前进程还未加载这批代码。加载时会重启受控示例进程，保留本应用的权限与历史。' : value.runtime_state === 'UNCONFIRMED' ? '暂时无法确认当前运行实例，请先核对应用与环境。' : '当前应用的运行版本尚未独立对应，检查记录不能冒充这批交付已被验证。'}</p>}
      <p className="editorial-muted">任务说明中的普通功能目标需要另行验证。界鉴检查已确认的权限要求。</p></> : <p className="editorial-muted">明确这次开发目标，沿用已批准权限，让每批修改、检查和修复都能回到同一项任务。</p>}
    {uncertain && <Alert className="flow-feedback" type="warning" showIcon message="本次操作回执尚未确认" description="先查询原回执；如需重试，将沿用同一操作标识和内容。" action={<Button loading={busy} onClick={() => void queryReceipt()}>查询原回执</Button>}/>}
    {message && <p role="status" className="development-feedback">{message}</p>}
    {editing && <Form form={form} layout="vertical" onFinish={save} disabled={disabled || busy} className="development-task-form">
      <Form.Item name="title" label="任务名称" rules={[{ required: true, whitespace: true }, { max: 120 }]}><Input maxLength={120} placeholder="例如：将项目导出改为后台任务"/></Form.Item>
      <Form.Item name="goal" label="这次希望完成什么" rules={[{ required: true, whitespace: true }, { max: 4000 }]}><Input.TextArea rows={3} maxLength={4000} placeholder="说明预期行为。权限要求沿用已批准记录，无需重复填写。"/></Form.Item>
      <div className="confirmation-actions"><Button disabled={uncertain} onClick={() => setEditing(false)}>取消</Button><Button type="primary" htmlType="submit" loading={busy}>{value ? '保存任务修订' : '创建任务'}</Button></div>
    </Form>}
    {value && !editing && <footer className="development-task-footer"><div>{value.deliveries[0] ? <Button onClick={() => onSelectChange(value.deliveries[0].change_id)}>查看第 {value.deliveries[0].ordinal} 批交付</Button> : <span className="editorial-muted">尚无已登记交付</span>}</div>
      <div className="development-task-actions">{latest && <Button disabled={disabled || busy} onClick={() => void copy()}>复制任务说明</Button>}<Button disabled={disabled || busy || uncertain} onClick={() => { form.setFieldsValue({ title: value.context.title, goal: value.context.goal }); setEditing(true) }}>修改任务</Button>
        <Popconfirm title="结束这项开发任务？" description="保留全部交付和检查记录。结束任务不会将未验证的修改标为通过。" okText="结束任务" cancelText="返回" onConfirm={() => transact('CLOSE', { version: value.task.version }, id => developmentApi.finish(projectId, value.task.task_id, { operation_id: id, expected_version: value.task.version, action: 'CLOSE' }))}><Button disabled={disabled || busy || uncertain}>结束任务</Button></Popconfirm>
        <Popconfirm title="取消这项开发任务？" description="停止继续推进此目标，已登记的交付和检查历史仍然保留。" okText="取消任务" cancelText="返回" onConfirm={() => transact('CANCEL', { version: value.task.version }, id => developmentApi.finish(projectId, value.task.task_id, { operation_id: id, expected_version: value.task.version, action: 'CANCEL' }))}><Button danger type="text" disabled={disabled || busy || uncertain}>取消任务</Button></Popconfirm>
      </div></footer>}
  </section>
}
