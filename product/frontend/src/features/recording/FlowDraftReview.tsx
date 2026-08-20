/* FlowDraft 审阅：以业务步骤、资源映射和动态变量呈现，只提交显式审阅命令。 */

import { Alert, Button, Card, Descriptions, Divider, Input, List, Popconfirm, Radio, Select, Space, Tag, Typography } from 'antd'
import type { FlowDraftDto, RecordingIdentityDto, RecordingReviewCommand } from '../../api/recordings'
import { productTermLabel } from '../../app/presentation'

export type RecordingBinding = { alternate_identity_id: string; resource_id: string; alternate_resource_id: string }

export function FlowDraftReview({ draft, identities, bindings, sources, renamingStep, renameValue, busy, canFinalize, bindingsReady, hasLooseActions, onBindingsChange, onSourcesChange, onRenameStart, onRenameValueChange, onRenameCancel, onReview, onFinalize }: {
  draft: FlowDraftDto
  identities: RecordingIdentityDto[]
  bindings: Record<string, RecordingBinding>
  sources: Record<string, string>
  renamingStep?: string
  renameValue: string
  busy: boolean
  canFinalize: boolean
  bindingsReady: boolean
  hasLooseActions: boolean
  onBindingsChange: (value: Record<string, RecordingBinding>) => void
  onSourcesChange: (value: Record<string, string>) => void
  onRenameStart: (stepId: string, value: string) => void
  onRenameValueChange: (value: string) => void
  onRenameCancel: () => void
  onReview: (command: RecordingReviewCommand) => void
  onFinalize: () => void
}) {
  const steps = draft.steps
  const variables = draft.variables ?? []
  return <Card title="确认录制流程">
    <Typography.Paragraph>按实际业务含义检查步骤名称、执行身份、资源映射和动态变量。普通流程无需编辑 JSON。</Typography.Paragraph>
    <List split={false} dataSource={steps} renderItem={(step, index) => {
      const id = step.id
      const binding = bindings[id] ?? { alternate_identity_id: '', resource_id: '', alternate_resource_id: '' }
      return <List.Item style={{ display: 'block' }}><Card size="small" title={<Space wrap><Typography.Text strong>步骤 {index + 1}：{step.name}</Typography.Text>{step.method ? <Tag color="blue">{step.method}</Tag> : <Tag color="gold">需要合并</Tag>}</Space>} extra={<Space><Button size="small" onClick={() => onRenameStart(id, step.name)}>重命名</Button><Popconfirm title="删除这个步骤？" description="仍被其他步骤或变量引用时，界鉴会拒绝删除。" onConfirm={() => onReview({ schema_version: '1', operation: 'DELETE_STEP', step_id: id })}><Button aria-label={`删除步骤 ${index + 1}`} size="small" danger disabled={steps.length === 1}>删除</Button></Popconfirm></Space>}>
        {renamingStep === id && <Space.Compact block><Input aria-label={`步骤 ${index + 1} 名称`} value={renameValue} maxLength={128} onChange={(event) => onRenameValueChange(event.target.value)} /><Button type="primary" disabled={!renameValue.trim()} onClick={() => onReview({ schema_version: '1', operation: 'RENAME_STEP', step_id: id, name: renameValue.trim() })}>保存名称</Button><Button onClick={onRenameCancel}>取消</Button></Space.Compact>}
        <Descriptions size="small" column={{ xs: 1, md: 2 }}><Descriptions.Item label="当前身份">{productTermLabel('role', identities.find((item) => item.identity_id === step.identity_id)?.role, false)} · {productTermLabel('identity', step.identity_id, false)}（{step.identity_id}）</Descriptions.Item><Descriptions.Item label="操作">{step.method ? `${step.method} ${step.path}` : '浏览器界面操作，需与相邻请求合并'}</Descriptions.Item></Descriptions>
        {step.method && <><Divider orientation="left" plain>检查对象映射</Divider><Space wrap align="start"><Select aria-label={`步骤 ${index + 1} 对照身份`} placeholder="选择对照身份" value={binding.alternate_identity_id || undefined} onChange={(value) => onBindingsChange({ ...bindings, [id]: { ...binding, alternate_identity_id: value } })} style={{ minWidth: 190 }} options={identities.filter((item) => item.identity_id !== step.identity_id).map((item) => ({ value: item.identity_id, label: `${productTermLabel('role', item.role, false)} · ${productTermLabel('identity', item.identity_id, false)}（${item.identity_id}）` }))} /><Input aria-label={`步骤 ${index + 1} 当前资源`} placeholder="当前身份的资源名称" value={binding.resource_id} onChange={(event) => onBindingsChange({ ...bindings, [id]: { ...binding, resource_id: event.target.value } })} style={{ width: 210 }} /><Input aria-label={`步骤 ${index + 1} 对照资源`} placeholder="对照身份的资源名称" value={binding.alternate_resource_id} onChange={(event) => onBindingsChange({ ...bindings, [id]: { ...binding, alternate_resource_id: event.target.value } })} style={{ width: 210 }} /></Space></>}
      </Card>{index < steps.length - 1 && <div className="recording-merge-action"><Button size="small" disabled={busy} onClick={() => onReview({ schema_version: '1', operation: 'MERGE_ADJACENT_STEPS', left_step_id: id, right_step_id: steps[index + 1].id })}>与下一步合并</Button></div>}</List.Item>
    }} />
    {variables.length > 0 && <><Divider orientation="left">动态变量</Divider><Space direction="vertical" className="full-width">{variables.map((variable) => <Card size="small" key={variable.name} title={<Space><Typography.Text strong>{variable.name}</Typography.Text><Tag color={variable.status === 'CONFIRMED' ? 'green' : 'gold'}>{variable.status === 'CONFIRMED' ? '已确认' : '请选择来源'}</Tag></Space>}><Typography.Paragraph type="secondary">后续步骤会使用这个值。请选择它来自哪个步骤的响应。</Typography.Paragraph><Radio.Group value={sources[variable.name]} onChange={(event) => onSourcesChange({ ...sources, [variable.name]: event.target.value })}><Space direction="vertical">{variable.candidate_sources.map((source) => { const sourceStep = steps.find((step) => step.id === source.source_step_id); const value = `${source.source_event_sequence}|${source.json_path}`; return <Radio key={value} value={value}>来自“{sourceStep?.name ?? '前序步骤'}”响应中的 {source.json_path.replace(/^\$\./, '')}</Radio> })}</Space></Radio.Group></Card>)}</Space></>}
    {!canFinalize && <Alert className="recording-review-warning" type="warning" showIcon message="还有内容需要确认" description={hasLooseActions ? '请把只含界面动作的步骤与相邻请求合并，或删除无关步骤。' : !bindingsReady ? '请补全每个请求步骤的对照身份和资源映射。' : '请为每个动态变量选择来源。'} />}
    <div className="recording-finalize-action"><Button type="primary" size="large" loading={busy} disabled={!canFinalize} onClick={onFinalize}>确认并保存流程</Button></div>
  </Card>
}
