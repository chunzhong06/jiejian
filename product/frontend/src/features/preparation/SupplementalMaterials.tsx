// 用户提供的材料只供补充阅读；校验、保存和版本事实由服务端形成，不用于安全判断。
import { Alert, Button, Empty, Input, Popconfirm, Spin } from 'antd'
import { ArrowLeftOutlined, CheckCircleOutlined, FileTextOutlined, UploadOutlined } from '@ant-design/icons'
import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/http'
import { supplementalMaterialsApi as api, type SupplementalDocument, type SupplementalMaterial, type MaterialPreview } from '../../api/supplementalMaterials'
import { formatTimestamp } from '../../app/presentation'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { useTaskGuard } from '../../components/TaskContinuity'
import './supplemental-materials.css'

export function SupplementalMaterials({ projectId, actionId, actionRevision, actionLabel, onBack }: {
  projectId: string; actionId: string; actionRevision: number; actionLabel: string; onBack: () => void
}) {
  const [items, setItems] = useState<SupplementalMaterial[]>([]), [more, setMore] = useState(false)
  const [preview, setPreview] = useState<MaterialPreview | null>(null), [selected, setSelected] = useState<SupplementalMaterial | null>(null)
  const [history, setHistory] = useState<SupplementalMaterial[] | null>(null)
  const [historyMore, setHistoryMore] = useState(false)
  const [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [issue, setIssue] = useState<string>(), [receipt, setReceipt] = useState<string>()
  const [editing, setEditing] = useState(false), [edit, setEdit] = useState({ title: '', source_label: '', claimed_resource_label: '' })
  const [uncertain, setUncertain] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null), generation = useRef(0), sending = useRef(false)
  const pending = useRef<{ kind: 'create' | 'revise' | 'withdraw'; key: string; fingerprint: string } | undefined>(undefined)
  useTaskGuard(Boolean(preview) || editing || busy || uncertain)
  const validate = (value: { project_id: string; action_id: string }) => {
    if (value.project_id !== projectId || value.action_id !== actionId) throw new ApiError('STATE_PRECONDITION', '材料所属应用或动作不一致。')
  }
  const load = async () => {
    const epoch = generation.current
    try {
      const next = await api.list(projectId, actionId); validate(next); next.items.forEach(validate)
      if (epoch === generation.current) { setItems(next.items); setMore(next.has_more) }
    } catch { if (epoch === generation.current) { setItems([]); setIssue('材料列表暂时无法读取。请重新读取，避免重复登记。') } }
    finally { if (epoch === generation.current) setLoading(false) }
  }
  useEffect(() => {
    generation.current += 1; setItems([]); setPreview(null); setSelected(null); setHistory(null); setLoading(true); setIssue(undefined)
    setEditing(false); setUncertain(false); pending.current = undefined
    void load()
    return () => { generation.current += 1 }
  }, [projectId, actionId])
  useEffect(() => {
    if (!preview && !editing && !uncertain) return
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = '' }
    window.addEventListener('beforeunload', warn)
    return () => window.removeEventListener('beforeunload', warn)
  }, [preview, editing, uncertain])
  const readFile = async (file: File) => {
    if (sending.current || uncertain) return
    const epoch = generation.current
    sending.current = true; setBusy(true); setIssue(undefined); setReceipt(undefined); setPreview(null); setSelected(null); setHistory(null)
    try {
      if (file.size > 65536) throw new Error('size')
      const document: unknown = JSON.parse(await file.text())
      const next = await api.preview(projectId, actionId, document); validate(next); validate(next.document)
      if (next.document.action_revision !== actionRevision || next.usage !== 'SUPPLEMENTAL_ONLY') throw new Error('scope')
      if (epoch === generation.current) setPreview(next)
    } catch (error) { if (epoch === generation.current) setIssue(error instanceof ApiError ? error.message : '文件无法作为当前动作的补充材料读取。请核对格式、动作版本和 64 KiB 大小限制。') }
    finally { sending.current = false; if (epoch === generation.current) setBusy(false); if (fileInput.current) fileInput.current.value = '' }
  }
  const write = async (kind: 'create' | 'revise' | 'withdraw') => {
    if (sending.current || (kind === 'create' ? !preview : !selected)) return
    const data = kind === 'create' ? preview!.document : { material: selected!.material_id, revision: selected!.revision, ...(kind === 'revise' ? edit : {}) }
    const fingerprint = JSON.stringify(data)
    if (pending.current && (pending.current.kind !== kind || pending.current.fingerprint !== fingerprint)) { setIssue('上次保存回执尚未确认，不能更换内容再次提交。'); return }
    // 丢失回执后仍绑定原内容与请求标识；用户确认重试也不能产生另一笔登记。
    pending.current ??= { kind, key: crypto.randomUUID(), fingerprint }
    const epoch = generation.current
    sending.current = true; setBusy(true); setUncertain(true); setIssue(undefined)
    try {
      const result = kind === 'create' ? await api.create(projectId, actionId, preview!.document, preview!.fingerprint, pending.current.key)
        : kind === 'revise' ? await api.revise(projectId, actionId, selected!.material_id, { expected_revision: selected!.revision, ...edit, claimed_resource_label: edit.claimed_resource_label.trim() || null, request_id: pending.current.key })
          : await api.withdraw(projectId, actionId, selected!.material_id, selected!.revision, pending.current.key)
      validate(result)
      if (kind !== 'create' && result.material_id !== selected!.material_id) throw new Error('material mismatch')
      if (epoch !== generation.current) return
      pending.current = undefined; setUncertain(false); setPreview(null); setEditing(false); setSelected(result); setHistory(null)
      setReceipt(kind === 'withdraw' ? '已撤下当前引用，原材料及其修订仍保留。' : '补充材料已保存，不会改变准备状态或检查结论。')
      await load()
    } catch (error) { if (epoch === generation.current) {
      if (error instanceof ApiError && ['INPUT_INVALID', 'STATE_PRECONDITION', 'RECORD_NOT_FOUND', 'STORAGE_SECRET'].includes(error.code)) {
        // 这些服务端拒绝发生在事务提交前；保留输入供修正，不把确定拒绝当作丢失回执。
        pending.current = undefined; setUncertain(false); setIssue(`本次保存未被接受：${error.message}`)
      } else setIssue('保存回执尚未确认。请先核对已保存材料；确认同次保存只复用原请求，不会创建另一份。')
      await load()
    } }
    finally { sending.current = false; if (epoch === generation.current) setBusy(false) }
  }
  const inspectHistory = async (older = false) => {
    if (!selected || sending.current) return
    const epoch = generation.current, material = selected.material_id
    const before = older && history?.length ? Math.min(...history.map(item => item.revision)) : undefined
    setBusy(true); if (!older) { setHistory(null); setHistoryMore(false) }
    try {
      const result = await api.revisions(projectId, actionId, material, before); validate(result)
      if (result.items.some(item => item.material_id !== material || item.project_id !== projectId || item.action_id !== actionId)) throw new Error('scope')
      if ((before && result.items.some(item => item.revision >= before)) || (result.has_more && !result.items.length)) throw new Error('cursor')
      if (epoch === generation.current) { setHistory(previous => older ? [...(previous ?? []), ...result.items] : result.items); setHistoryMore(Boolean(result.has_more)) }
    } catch { if (epoch === generation.current) setIssue('修订记录读取失败，未展示旧快照。') }
    finally { if (epoch === generation.current) setBusy(false) }
  }
  const template = () => {
    const templateDocument: SupplementalDocument = { schema_version: '1', project_id: projectId, action_id: actionId, action_revision: actionRevision, title: '请填写材料名称', source_label: '请填写真实来源', claimed_resource_label: null, records: [{ recorded_at_us: 0, resource_label: '请填写业务对象', event_label: '请填写真实记录，不要填写密码或令牌' }] }
    const url = URL.createObjectURL(new Blob([JSON.stringify(templateDocument, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a'); link.href = url; link.download = '补充材料格式模板.json'; link.click(); URL.revokeObjectURL(url)
  }
  const current = preview?.document ?? selected
  return <EditorialPage label="补充材料登记与审阅">
    <div className="supplemental-toolbar"><Button type="link" icon={<ArrowLeftOutlined aria-hidden/>} disabled={busy || uncertain || editing} onClick={onBack}>返回证明材料</Button><Button disabled={busy} onClick={() => { setLoading(true); void load() }}>重新读取材料</Button></div>
    <EditorialHeader eyebrow={`${actionLabel} / 补充材料`} title={preview ? '这份材料能说明什么' : '管理已提供的业务记录'}><p className="editorial-muted">登记已有业务记录，先核对来源与适用范围。</p></EditorialHeader>
    {issue && <Alert type="warning" showIcon message={issue}/>}{receipt && <p className="work-receipt" role="status">{receipt}</p>}
    <input ref={fileInput} type="file" accept="application/json,.json" aria-label="选择补充材料文件" hidden onChange={event => { const file = event.currentTarget.files?.[0]; if (file) void readFile(file) }}/>
    {!current && <section className="supplemental-empty"><FileTextOutlined aria-hidden/><h2>添加一份已有材料</h2><p>只接受界鉴补充材料格式的 JSON 文件。材料最多 100 条记录、64 KiB。</p><Button type="primary" size="large" icon={<UploadOutlined aria-hidden/>} loading={busy} onClick={() => fileInput.current?.click()}>选择材料文件</Button><Button type="link" onClick={template}>下载空白格式模板</Button><p className="editorial-muted">模板里的示例占位需要替换为真实记录；读取成功不代表记录已获独立验证。</p></section>}
    {current && <div className="supplemental-review"><section className="supplemental-main"><header><h2>{current.title}</h2><span className="source-tag">{preview ? '待审阅' : selected?.withdrawn ? '已撤下引用' : `已保存 · 修订 ${selected?.revision}`}</span></header>
      <dl className="supplemental-facts"><dt>材料来源</dt><dd>{current.source_label}</dd><dt>业务动作</dt><dd>{actionLabel}</dd><dt>对应资源</dt><dd>{current.claimed_resource_label || '尚待确认'}</dd></dl>
      <h3>材料内容核对</h3><ul className="supplemental-checks"><li><span>文件格式</span><strong><CheckCircleOutlined/> 可以读取</strong></li><li><span>业务对象</span><strong className="needs-review">{current.claimed_resource_label ? '由提供者声明，尚非独立验证' : '需要确认对应关系'}</strong></li><li><span>记录范围</span><strong>{preview?.record_count ?? selected?.record_count} 条用户提供的记录</strong></li></ul>
      {editing && <section className="supplemental-edit" aria-label="修改材料说明"><label>材料名称<Input value={edit.title} maxLength={128} disabled={busy || uncertain} onChange={e => setEdit({ ...edit, title: e.target.value })}/></label><label>来源说明<Input value={edit.source_label} maxLength={128} disabled={busy || uncertain} onChange={e => setEdit({ ...edit, source_label: e.target.value })}/></label><label>声明对应资源<Input value={edit.claimed_resource_label} maxLength={128} disabled={busy || uncertain} onChange={e => setEdit({ ...edit, claimed_resource_label: e.target.value })}/></label><p className="editorial-muted">保存产生新修订，原文件内容保持不变。</p></section>}
    </section><aside className="supplemental-usage"><h2>使用范围</h2><FileTextOutlined aria-hidden/><h3>目前只能作为补充材料</h3><p>不能单独证明业务后果未发生。<br/>不会改变已有检查结论。</p>
      {preview ? <Button type="primary" size="large" block loading={busy} onClick={() => void write('create')}>{uncertain ? '确认同次保存' : '保存为补充材料'}</Button> : editing ? <Button type="primary" size="large" block loading={busy} disabled={!edit.title.trim() || !edit.source_label.trim()} onClick={() => void write('revise')}>{uncertain ? '确认同次保存' : '保存说明新修订'}</Button> : uncertain ? <Button loading={busy} onClick={() => { if (pending.current) void write(pending.current.kind) }}>确认同次保存</Button> : <Button type="primary" size="large" block disabled={busy} onClick={() => { setPreview(null); setSelected(null); setHistory(null); fileInput.current?.click() }}>登记另一份材料</Button>}
      {preview && <Button type="link" disabled={busy || uncertain} onClick={() => setPreview(null)}>取消本次登记</Button>}
      {selected && !editing && !uncertain && <><Button type="link" disabled={busy || selected.withdrawn} onClick={() => { setEdit({ title: selected.title, source_label: selected.source_label, claimed_resource_label: selected.claimed_resource_label ?? '' }); setEditing(true) }}>修改材料说明</Button><Button type="link" disabled={busy} onClick={() => void inspectHistory()}>查看全部修订</Button>{!selected.withdrawn && <Popconfirm title="撤下当前材料引用？" description="保留原文件和历史修订，不会删除已发布结果。" onConfirm={() => void write('withdraw')} okText="撤下引用" cancelText="取消"><Button type="text" disabled={busy}>撤下当前引用</Button></Popconfirm>}</>}
      {editing && <Button type="link" disabled={busy || uncertain} onClick={() => setEditing(false)}>取消修改</Button>}
    </aside></div>}
    {current && <details className="supplemental-details"><summary>查看材料摘要与限制</summary><p>以下内容由材料提供者提交，不代表界鉴独立观察到的事实。</p><ul>{current.records.map((record, index) => <li key={index}><time>{formatTimestamp(record.recorded_at_us)}</time><strong>{record.resource_label}</strong><span>{record.event_label}</span></li>)}</ul></details>}
    {history && <section className="supplemental-history" aria-label="材料修订历史"><h2>修订记录</h2>{[...history].sort((a,b) => b.revision-a.revision).map(item => <article key={item.revision}><strong>修订 {item.revision} · {item.title}</strong><p>{formatTimestamp(item.updated_at_us)} · {item.withdrawn ? '引用已撤下' : '说明已保存'}</p><p>{item.source_label}</p><p>声明对应资源：{item.claimed_resource_label || '尚待确认'}</p></article>)}{historyMore && <Button loading={busy} onClick={() => void inspectHistory(true)}>读取更早修订</Button>}</section>}
    {!preview && !editing && <section className="supplemental-list" aria-label="已保存补充材料"><h2>已保存材料</h2>{loading ? <Spin/> : !items.length ? <Empty description="尚无已保存的补充材料"/> : items.map(item => <button key={item.material_id} disabled={busy || uncertain} aria-pressed={selected?.material_id === item.material_id} onClick={() => { setSelected(item); setHistory(null); setReceipt(undefined) }}><FileTextOutlined aria-hidden/><span><strong>{item.title}</strong><small>{item.source_label} · 修订 {item.revision} · {item.withdrawn ? '已撤下引用' : '仅作补充材料'}</small></span></button>)}{more && <p>当前显示近期 100 份材料，列表不是全部历史。</p>}</section>}
  </EditorialPage>
}
