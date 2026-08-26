/* FlowDraft 审阅：以业务步骤、资源映射和动态变量呈现，只提交显式审阅命令。 */

import { Alert, Button, Card, Descriptions, Divider, Input, List, Popconfirm, Radio, Space, Tag, Typography } from 'antd'
import type { FlowDraftDto, FlowDraftStepDto, RecordingReviewCommand } from '../../api/recordings'

function readableRequest(step: FlowDraftStepDto, resourceCandidateId?: string | null) {
  if (!step.method || !step.path) return '浏览器界面操作，需与相邻请求合并'
  const candidate = step.resource_candidates.find((item) => item.candidate_id === resourceCandidateId)
  let path = step.path
  if (candidate?.consumer === 'PATH') {
    const index = Number(candidate.location.replace(/^path\[/, '').replace(/\]$/, ''))
    const parts = path.split('/')
    const positions = parts.flatMap((value, position) => value ? [position] : [])
    const position = positions[index]
    if (Number.isInteger(index) && position !== undefined) parts[position] = '{测试资源}'
    path = parts.join('/')
  } else if (candidate?.consumer === 'QUERY') {
    const [pathname, query] = path.split('?')
    const items = (query ?? '').split('&').filter(Boolean).map((item) => {
      const [key, ...rest] = item.split('=')
      return decodeURIComponent(key) === candidate.location.replace(/^query\./, '') ? `${key}={测试资源}` : [key, ...rest].join('=')
    })
    path = pathname + (items.length ? `?${items.join('&')}` : '')
  }
  return `${step.method} ${path}`
}

export function FlowDraftReview({ draft, actionName, sources, renamingStep, renameValue, busy, canFinalize, hasLooseActions, onSourcesChange, onRenameStart, onRenameValueChange, onRenameCancel, onReview, onFinalize }: {
  draft: FlowDraftDto
  actionName: string
  sources: Record<string, string>
  renamingStep?: string
  renameValue: string
  busy: boolean
  canFinalize: boolean
  hasLooseActions: boolean
  onSourcesChange: (value: Record<string, string>) => void
  onRenameStart: (stepId: string, value: string) => void
  onRenameValueChange: (value: string) => void
  onRenameCancel: () => void
  onReview: (command: RecordingReviewCommand) => void
  onFinalize: () => void
}) {
  const steps = draft.steps
  const variables = draft.variables ?? []
  return <Card title={`界鉴认为下面这一步真正执行了“${actionName}”，请确认`}>
    <Typography.Paragraph>请从这次录制得到的有限步骤中确认真正执行该业务动作的请求，再确认业务资源位置。普通流程无需编辑 JSON。</Typography.Paragraph>
    <List split={false} dataSource={steps} renderItem={(step, index) => {
      const id = step.id
      const target = draft.target_step_id === id
      const recommended = draft.recommended_target_step_id === id
      return <List.Item style={{ display: 'block' }}><Card size="small" title={<Space wrap><Typography.Text strong>步骤 {index + 1}：{step.name}</Typography.Text>{step.method ? <Tag color="blue">{step.method}</Tag> : <Tag color="gold">需要合并</Tag>}{recommended && <Tag color="cyan">推荐目标</Tag>}{target && <Tag color="green">已确认目标</Tag>}</Space>} extra={<Space>{step.method && !target && <Button aria-label={`将“${step.name}”确认为目标请求`} size="small" type={recommended ? 'primary' : 'default'} onClick={() => onReview({ schema_version: '1', operation: 'CONFIRM_TARGET_STEP', step_id: id })}>确认为目标请求</Button>}<Button size="small" onClick={() => onRenameStart(id, step.name)}>重命名</Button><Popconfirm title="删除这个步骤？" description="仍被其他步骤或变量引用时，界鉴会拒绝删除。" onConfirm={() => onReview({ schema_version: '1', operation: 'DELETE_STEP', step_id: id })}><Button aria-label={`删除步骤 ${index + 1}`} size="small" danger disabled={steps.length === 1}>删除</Button></Popconfirm></Space>}>
        {renamingStep === id && <Space.Compact block><Input aria-label={`步骤 ${index + 1} 名称`} value={renameValue} maxLength={128} onChange={(event) => onRenameValueChange(event.target.value)} /><Button type="primary" disabled={!renameValue.trim()} onClick={() => onReview({ schema_version: '1', operation: 'RENAME_STEP', step_id: id, name: renameValue.trim() })}>保存名称</Button><Button onClick={onRenameCancel}>取消</Button></Space.Compact>}
        <Descriptions size="small" column={1}><Descriptions.Item label="技术请求">{readableRequest(step, target ? draft.resource_candidate_id : null)}</Descriptions.Item></Descriptions>
        {target && <><Divider orientation="left" plain>业务资源位置</Divider>{step.resource_candidates.length > 0 ? <Radio.Group value={draft.resource_candidate_id} onChange={(event) => onReview({ schema_version: '1', operation: 'CONFIRM_RESOURCE_SLOT', candidate_id: event.target.value })}><Space direction="vertical">{step.resource_candidates.map((candidate) => <Radio key={candidate.candidate_id} value={candidate.candidate_id}>{candidate.label}</Radio>)}</Space></Radio.Group> : <Alert type="warning" showIcon message="目标请求中没有可确认的业务资源字段" description="请重新录制包含资源标识的动作，或选择另一条目标请求。" />}</>}
      </Card>{index < steps.length - 1 && <div className="recording-merge-action"><Button size="small" disabled={busy} onClick={() => onReview({ schema_version: '1', operation: 'MERGE_ADJACENT_STEPS', left_step_id: id, right_step_id: steps[index + 1].id })}>与下一步合并</Button></div>}</List.Item>
    }} />
    {variables.length > 0 && <><Divider orientation="left">动态变量</Divider><Space direction="vertical" className="full-width">{variables.map((variable) => <Card size="small" key={variable.name} title={<Space><Typography.Text strong>{variable.name}</Typography.Text><Tag color={variable.status === 'CONFIRMED' ? 'green' : 'gold'}>{variable.status === 'CONFIRMED' ? '已确认' : '请选择来源'}</Tag></Space>}><Typography.Paragraph type="secondary">后续步骤会使用这个值。请选择它来自哪个步骤的响应。</Typography.Paragraph><Radio.Group value={sources[variable.name]} onChange={(event) => onSourcesChange({ ...sources, [variable.name]: event.target.value })}><Space direction="vertical">{variable.candidate_sources.map((source) => { const sourceStep = steps.find((step) => step.id === source.source_step_id); const value = `${source.source_event_sequence}|${source.json_path}`; return <Radio key={value} value={value}>来自“{sourceStep?.name ?? '前序步骤'}”响应中的 {source.json_path.replace(/^\$\./, '')}</Radio> })}</Space></Radio.Group></Card>)}</Space></>}
    {!canFinalize && <Alert className="recording-review-warning" type="warning" showIcon message="还有内容需要确认" description={hasLooseActions ? '请把只含界面动作的步骤与相邻请求合并，或删除无关步骤。' : !draft.target_step_id ? '请明确确认一条目标请求。' : !draft.resource_candidate_id ? '请从目标请求的已录制字段中确认业务资源位置。' : '请为每个动态变量选择来源。'} />}
    <div className="recording-finalize-action"><Button type="primary" size="large" loading={busy} disabled={!canFinalize} onClick={onFinalize}>确认并保存流程</Button></div>
  </Card>
}
