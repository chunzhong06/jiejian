// 权限文本建议面板：显式生成、逐条审阅；异步结果与当前本地草稿及正式边界同时核对。
import { useEffect, useRef, useState } from 'react'
import { Alert, Button, Checkbox, Input, Space, Tag, Typography } from 'antd'
import { businessBoundariesApi } from '../../api/businessBoundaries'
import { permissionDraftsApi, type PermissionDraftSuggestion, type PermissionDraftView } from '../../api/permissionDrafts'
import { relationLabels } from './boundaryLabels'

export function PermissionDraftAssist({ projectId, boundaryFingerprint, draftKey, disabled, onApply }: {
  projectId: string; boundaryFingerprint: string; draftKey: string; disabled: boolean
  onApply: (suggestions: PermissionDraftSuggestion[]) => void
}) {
  const [text, setText] = useState('')
  const [view, setView] = useState<PermissionDraftView>()
  const [selected, setSelected] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string>()
  const key = JSON.stringify([projectId, boundaryFingerprint, draftKey, text])
  const current = useRef<string | null>(key)
  current.current = key
  const resultKey = useRef<string | undefined>(undefined)
  useEffect(() => () => { current.current = null }, [])
  const unchanged = async (expected: string) => {
    const latest = await businessBoundariesApi.maintenanceDraft(projectId)
    return current.current === expected && latest.boundary_state_fingerprint === boundaryFingerprint
  }
  const generate = async () => {
    const expected = key
    setBusy(true); setMessage(undefined); setView(undefined)
    try {
      if (!await unchanged(expected)) { if (current.current === expected) setMessage('业务边界已变化，请刷新后重新整理。'); return }
      const next = await permissionDraftsApi.generate(projectId, text.trim())
      if (current.current !== expected) return
      if (!await unchanged(expected)) { if (current.current === expected) setMessage('业务边界已变化，本次建议已丢弃。'); return }
      setView(next); setSelected([]); resultKey.current = expected
    } catch { if (current.current === expected) setMessage('AI 辅助暂时无法整理，请继续手工填写权限规则。') }
    finally { if (current.current !== null) setBusy(false) }
  }
  const apply = async () => {
    const expected = key
    if (!view || resultKey.current !== expected) return
    setBusy(true)
    try {
      if (!await unchanged(expected)) { if (current.current === expected) setMessage('业务边界已变化，请刷新后重新整理。'); return }
      onApply(selected.map((index) => view.suggestions[index]))
      setView(undefined); setSelected([])
    } catch { if (current.current === expected) setMessage('未能核对当前边界，建议尚未填入，请重试。') }
    finally { if (current.current !== null) setBusy(false) }
  }
  const stale = Boolean(view && resultKey.current !== key)
  return <section className="boundary-permission-assist" aria-label="用文字整理权限草稿">
    <Space wrap><Tag color="purple">[AI辅助]</Tag><Typography.Text strong>用文字整理权限草稿</Typography.Text></Space>
    <Typography.Paragraph type="secondary">描述谁可以或不可以对谁的资源执行什么动作。建议只填入当前草稿，仍需生成提案并由你批准。</Typography.Paragraph>
    <Input.TextArea aria-label="权限要求原文" value={text} maxLength={2000} autoSize={{ minRows: 3, maxRows: 8 }} onChange={(event) => setText(event.target.value)} />
    <Button disabled={disabled || !text.trim()} loading={busy} onClick={() => void generate()}>AI 辅助整理</Button>
    {message && <Alert type="warning" showIcon message={message} />}
    {stale && <Alert type="info" showIcon message="草稿或原文已经修改，请重新生成建议。" />}
    {view && !stale && <div>
      <Typography.Title level={5}>待你确认的建议</Typography.Title>
      {view.suggestions.map((item, index) => <div key={item.option_ids.join(':')} className="boundary-editor-card">
        <Checkbox checked={selected.includes(index)} onChange={(event) => setSelected((items) => event.target.checked ? [...items, index] : items.filter((value) => value !== index))}>
          {item.subject_display_name}对{item.resource_owner_display_name}的资源（{relationLabels[item.relation]}），{item.suggested_expectation === 'ALLOW' ? '允许' : '拒绝'}“{item.action_display_name}”
        </Checkbox>
        <p>业务结果：{item.effect_display_names.join('、')}</p>
        {item.source_quotes.map((quote) => <Typography.Paragraph key={quote}>原文：“{quote}”</Typography.Paragraph>)}
      </div>)}
      {view.issues.map((issue, index) => <Alert key={index} type="warning" showIcon message={issue.message} description={issue.source_quote ? `待确认原文：“${issue.source_quote}”` : undefined} />)}
      {!view.suggestions.length && !view.issues.length && <Typography.Paragraph>当前没有可采用的建议，请继续手工填写。</Typography.Paragraph>}
      <Button disabled={disabled || !selected.length} loading={busy} onClick={() => void apply()}>将选中建议填入草稿</Button>
    </div>}
  </section>
}
