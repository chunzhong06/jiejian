// 材料编辑只选择已核对来源；保存前先预览，回执不明时回读同一操作，不重复提交。
import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Radio, Select, Spin } from 'antd'
import { preparationApi, type MaterialChange, type MaterialDetails, type MaterialPreview, type MaterialReference, type MaterialRecordingContext, type PreparationDraft } from '../../api/preparation'
import { ApiError } from '../../api/http'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import { useTaskGuard } from '../../app/tasks/TaskContinuity'
import './materials.css'

const names = { execution: '动作录制', resource: '测试资源', evidence: '结果证明', recovery: '恢复方式' }
export const materialName = (ref: MaterialReference) => names[ref.kind]
const sameMaterial = (left: MaterialReference | null, right: MaterialReference) => left?.action_id === right.action_id && left.action_revision === right.action_revision && left.kind === right.kind && left.member_id === right.member_id
const time = (value: number | null) => value ? new Date(value / 1000).toLocaleString('zh-CN', { hour12: false }) : '尚未确认'
const reasons: Record<string, string> = {
  TEST_IDENTITY_LOGIN_REQUIRED: '账号登录状态已不可用。重新登录后，界鉴会核对是否可以继续使用原材料。',
  TEST_IDENTITY_REQUIRED: '所需测试账号已缺失。请先补齐当前业务角色的账号。',
  RESOURCE_OWNER_SOURCE_STALE: '资源所有者的账号或角色依据已变化，请先核对资源所属账号。',
  TEST_ACTOR_SOURCE_STALE: '操作账号的业务角色或实现依据已变化，请先核对账号与角色。',
  REGISTERED_OBSERVER_UNAVAILABLE: '原受控证明来源当前不可用。请核对来源能力，或录制新的观察材料。',
  RECORDING_SOURCE_STALE: '原录制及其审阅来源已无法匹配。原记录保留，请重新录制这项材料。',
  SUPPLEMENT_RESOURCE_STALE: '这项补录依赖的资源已变化。先核对测试资源，再更新证明或恢复方式。',
  RESOURCE_INJECTION_STALE: '动作录制和资源参数不再匹配，请先核对动作使用的具体资源。',
  ACTION_BINDING_SOURCE_STALE: '材料的业务来源与当前配置不一致。请先核对应用、业务修订与实现，再更新这项材料。',
}

export function MaterialEditor({ projectId, reference, actionLabel, effectLabel, onBack, onSaved, onRecord, onRecordCandidate, onEvidence, focusSourceEntry, onError, onDraftChange, labelForMaterial = materialName }: {
  projectId: string; reference: MaterialReference; actionLabel: string; effectLabel?: string
  onBack: () => void; onSaved: () => Promise<unknown>; onRecord?: () => void; onError: (error: ApiError) => void
  onDraftChange?: (draft: PreparationDraft) => void
  labelForMaterial?: (reference: MaterialReference) => string
  onRecordCandidate?: (context: MaterialRecordingContext) => void
  onEvidence?: () => void
  focusSourceEntry?: boolean
}) {
  const [details, setDetails] = useState<MaterialDetails>()
  const [draft, setDraft] = useState<PreparationDraft>()
  const [selected, setSelected] = useState<string | null>(null)
  const [preview, setPreview] = useState<MaterialPreview>()
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string>()
  const [pending, setPending] = useState<string>()
  const [error, setError] = useState<string>()
  const [inputMode, setInputMode] = useState<'existing' | 'record'>('existing')
  const command = useRef<MaterialChange | undefined>(undefined)
  const draftPointer = useRef<PreparationDraft | undefined>(undefined)
  const active = useRef(true)
  const sourceEntry = useRef<HTMLElement | null>(null)
  const restoredSourceFocus = useRef(false)
  useEffect(() => {
    if (focusSourceEntry && details && draft && !restoredSourceFocus.current) {
      restoredSourceFocus.current = true; sourceEntry.current?.focus()
    }
  }, [focusSourceEntry, details, draft])
  useTaskGuard(busy || Boolean(pending))
  useEffect(() => {
    active.current = true
    void Promise.all([preparationApi.material(projectId, reference), preparationApi.draft(projectId)]).then(([value, saved]) => {
      if (!active.current) return
      setDetails(value); setDraft(saved); draftPointer.current = saved; onDraftChange?.(saved)
      if (value.recording_context?.recording_id) setInputMode('record')
      const same = sameMaterial(saved.material, reference)
      if (same && saved.pending_operation_id) setPending(saved.pending_operation_id)
      if (same && saved.base_fingerprint === value.expected_fingerprint && value.candidates.some(item => item.recording_id === saved.candidate_recording_id)) setSelected(saved.candidate_recording_id)
      else if (same && saved.candidate_recording_id) setMessage('上次选择已保留，但依赖发生变化。请重新选择并核对。')
    }).catch(value => { if (active.current) setError((value as Error).message) })
    return () => { active.current = false }
  }, [projectId, reference])

  const storeChoice = async (candidate: string | null, operationId: string | null = null) => {
    if (!draft || !details) throw new Error('准备位置尚未读取')
    const next = await preparationApi.saveDraft(projectId, { ...draft, action_id: reference.action_id,
      action_revision: reference.action_revision, material: reference, candidate_recording_id: candidate,
      base_fingerprint: details.expected_fingerprint, pending_operation_id: operationId })
    if (active.current) { setDraft(next); draftPointer.current = next; onDraftChange?.(next) }
    return next
  }
  const choose = async (value: string) => {
    setBusy(true); setPreview(undefined); command.current = undefined; setMessage(undefined)
    try { await storeChoice(value); if (active.current) setSelected(value) }
    catch (value) { onError(value as ApiError); setError('选择未保存，请返回材料重新读取，避免覆盖另一页面。') }
    finally { if (active.current) setBusy(false) }
  }
  const inspect = async () => {
    if (!details) return
    setBusy(true)
    const value: MaterialChange = { schema_version: '1', material: reference, operation_id: crypto.randomUUID().replaceAll('-', ''),
      expected_fingerprint: details.expected_fingerprint, candidate_recording_id: selected }
    try { const next = await preparationApi.previewMaterial(projectId, value); if (active.current) { command.current = value; setPreview(next) } }
    catch (value) { onError(value as ApiError); setError('材料已变化或暂不符合条件，请返回材料重新核对。') }
    finally { if (active.current) setBusy(false) }
  }
  const saved = async () => {
    setPending(undefined); setPreview(undefined); command.current = undefined
    setMessage('材料已保存并重新核对。已有检查与证据保持原样。')
    const currentDraft = draftPointer.current
    if (currentDraft) {
      const currentDetails = await preparationApi.material(projectId, reference)
      const next = await preparationApi.saveDraft(projectId, { ...currentDraft, pending_operation_id: null, candidate_recording_id: null,
        base_fingerprint: currentDetails.expected_fingerprint })
      if (active.current) { setDraft(next); draftPointer.current = next; onDraftChange?.(next); setDetails(currentDetails); setSelected(null) }
    }
    await onSaved()
  }
  const readReceipt = async () => {
    if (!pending) return
    setBusy(true)
    try {
      await preparationApi.materialReceipt(projectId, pending)
      try { await saved() } catch (reason) { onError(reason as ApiError); setMessage('保存回执已确认，准备位置尚未同步。可以返回材料重新读取。') }
    }
    catch (value) { onError(value as ApiError); setMessage('尚未确认保存回执。选择仍保留，请先核对，避免重复操作。') }
    finally { if (active.current) setBusy(false) }
  }
  const submit = async () => {
    const value = command.current
    if (!value || busy || pending) return
    setBusy(true)
    let receiptReceived = false
    try {
      await storeChoice(selected, value.operation_id)
      setPending(value.operation_id)
      await preparationApi.saveMaterial(projectId, value)
      receiptReceived = true
      await saved()
    } catch (reason) {
      onError(reason as ApiError)
      // 明确的前置拒绝与响应丢失不同；前者可撤下待回读标记，后者必须保留。
      if (!receiptReceived && reason instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID', 'RECORD_STATE_PRECONDITION', 'RECORD_DRAFT_REFERENCE'].includes(reason.code)) {
        const current = draftPointer.current
        if (current) {
          try {
            const next = await preparationApi.saveDraft(projectId, { ...current, pending_operation_id: null })
            draftPointer.current = next; setDraft(next); onDraftChange?.(next); setPending(undefined)
          } catch { /* 不覆盖另一页面；其草稿仍由自己的修订保护。 */ }
        }
        setError('本次保存已被拒绝，现有材料保持原样。请返回材料重新核对。')
      } else if (receiptReceived) setMessage('材料已保存，准备位置尚未同步。请返回材料重新读取。')
    }
    finally { if (active.current) setBusy(false) }
  }
  return <EditorialPage label="更新单项材料">
    <EditorialHeader eyebrow="检查材料 / 材料详情" title={`更新${names[reference.kind]}`}><p className="editorial-muted">{actionLabel}</p></EditorialHeader>
    {error && <Alert className="flow-feedback" type="warning" message={error} />}
    {message && <Alert className="flow-feedback" type="info" message={message} />}
    {details && ['STALE', 'BLOCKED'].includes(details.status) && <Alert className="flow-feedback" type="warning" message="原材料已保留，当前还不能复用"
      description={[...new Set(details.reason_codes.map(code => reasons[code] ?? '当前依据未通过核对，请返回检查材料处理当前缺口。'))].join(' ')} />}
    {pending && <Alert className="flow-feedback" type="warning" message="正在等待保存回执" description="重新打开页面后仍可核对这次操作，不会自动再次提交。" action={<Button loading={busy} onClick={() => void readReceipt()}>核对保存回执</Button>} />}
    {!details || !draft ? !error && <Spin /> : <section className="material-editor">
      <div className="material-editor-main">
        <p className="material-section-label">{reference.kind === 'evidence' ? '需要证明什么' : '本次处理的材料'}</p>
        <h2 className="material-purpose">{effectLabel ?? names[reference.kind]}</h2>
        {reference.kind === 'evidence' && onEvidence && <Button ref={node => { sourceEntry.current = node }} data-source-details type="link" disabled={busy || Boolean(pending)} onClick={onEvidence}>查看证明要求与来源能力</Button>}
        <section className="material-selection"><h3>选择替换材料</h3>
          <Radio.Group className="material-input-mode" aria-label="材料准备方式" value={inputMode} disabled={busy || Boolean(pending)} onChange={event => setInputMode(event.target.value)}>
            <Radio.Button value="existing">选择已有材料</Radio.Button><Radio.Button value="record">录制新的材料</Radio.Button>
          </Radio.Group>
          {inputMode === 'record' ? <div className="material-empty"><p>先录制并审阅，再确认替换</p><p className="editorial-muted">新录制会保存为候选。现有材料继续保留，不会在审阅时提前替换。</p>
            {details.recording_context && onRecordCandidate ? <Button type="primary" disabled={busy || Boolean(pending) || Boolean(error)} onClick={() => onRecordCandidate(details.recording_context!)}>{details.recording_context.recording_id ? '继续录制与审阅' : '准备新的录制'}</Button> : onRecord ? <Button onClick={onRecord}>处理当前录制缺口</Button> : <p>请先完成当前账号、动作实现与资源的核对，再录制这项材料。</p>}
          </div> : details.candidates.length ? <><label htmlFor="material-candidate">已完成并通过来源核对的录制</label><Select id="material-candidate" value={selected} disabled={busy || Boolean(pending) || Boolean(error)} placeholder="选择本次使用的材料" onChange={value => void choose(value)}
            options={details.candidates.map((item, index) => ({ value: item.recording_id, label: `${names[reference.kind]} ${index + 1} · ${time(item.captured_at_us)}${item.current ? ' · 当前材料' : ''}` }))} />
            <p className="editorial-muted">仅列出同一应用、业务修订和用途的候选；资源所有者必须一致。</p></> : <div className="material-empty"><p>尚无其他已确认录制</p>{details.status !== 'SATISFIED' && <p className="editorial-muted">完成录制并审阅后，再回到这里查看材料。</p>}{onRecord && <Button onClick={onRecord}>录制这项材料</Button>}</div>}
          {inputMode === 'existing' && !selected && details.status === 'SATISFIED' && <p>现有材料符合当前要求，可以直接重新核对后继续使用；更换来源时才需要准备其他录制。</p>}
        </section>
        <div className="material-comparison"><div><h3>现有材料</h3><p>{details.retained ? details.status === 'SATISFIED' ? '符合当前要求' : '已保存，需复核' : '尚未准备'}</p><small>最近确认：{time(details.confirmed_at_us)}</small></div><span aria-hidden="true">→</span><div><h3>确认后</h3><p>{selected ? '使用所选录制作为材料' : '保留现有材料'}</p><small>{preview ? '候选已核对，待确认保存' : '先核对本次影响'}</small></div></div>
        {!!details.reason_codes.length && <details className="material-dependencies"><summary>查看核对详情</summary><code>{details.reason_codes.join(' / ')}</code></details>}
      </div>
      <aside className="material-impact"><h2>本次影响</h2>{preview ? <><p className="material-impact-current">{preview.updates.length ? '更新' : '复核'}　{preview.updates.map(labelForMaterial).join('、') || names[reference.kind]}</p>
        <p>✓　真实账号继续保留</p>{preview.retained.filter(item => !sameMaterial(item, reference)).map(item => <p key={JSON.stringify(item)}>✓　保留{labelForMaterial(item)}</p>)}
        {!!preview.recheck.length && <p>需重新核对：{preview.recheck.map(labelForMaterial).join('、')}</p>}</> : <p className="editorial-muted">选择材料后核对影响。界鉴会列出更新、保留和需要重新检查的部分。</p>}
        <p className="material-history-note">已有检查与证据保留。材料保存不会修改历史结论。</p></aside>
      <footer className="material-editor-footer"><p className="editorial-muted">保存后重新核对材料，不会开始检查。</p><div><Button disabled={busy} onClick={onBack}>返回材料</Button>{inputMode === 'existing' && (preview ? <Button type="primary" loading={busy} disabled={Boolean(pending) || Boolean(error)} onClick={() => void submit()}>确认{selected ? '替换此项' : '沿用材料'}</Button> : <Button type="primary" loading={busy} disabled={Boolean(pending) || Boolean(error) || (!selected && details.status !== 'SATISFIED')} onClick={() => void inspect()}>核对本次影响</Button>)}</div></footer>
    </section>}
    {error && <Button onClick={onBack}>返回材料重新核对</Button>}
  </EditorialPage>
}
