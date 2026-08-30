/* Recording 业务解释确认：只呈现真正无法自动消解的业务选择。 */

import { Alert, Card, Divider, Radio, Space, Tag, Typography } from 'antd'
import type { FlowDraftDto, RecordingReviewCommand } from '../../api/recordings'

export function FlowDraftReview({ draft, actionName, sources, canFinalize, onSourcesChange, onReview }: {
  draft: FlowDraftDto
  actionName: string
  sources: Record<string, string>
  canFinalize: boolean
  onSourcesChange: (value: Record<string, string>) => void
  onReview: (command: RecordingReviewCommand) => void
}) {
  const executableSteps = draft.steps.filter((step) => step.method)
  const target = draft.steps.find((step) => step.id === draft.target_step_id)
  const variables = draft.variables ?? []

  return <Card title="界鉴正在整理这次演示的业务含义">
    <Typography.Paragraph>这次演示用于“{actionName}”。唯一含义已经自动采用，只有真正存在歧义时才需要你的选择。</Typography.Paragraph>
    {!draft.target_step_id && <section>
      <Typography.Text strong>哪一步真正完成了“{actionName}”？</Typography.Text>
      <Radio.Group onChange={(event) => onReview({ schema_version: '1', operation: 'CONFIRM_TARGET_STEP', step_id: event.target.value })}>
        <Space direction="vertical">{executableSteps.map((step) => <Radio key={step.id} value={step.id}>{step.name}</Radio>)}</Space>
      </Radio.Group>
    </section>}
    {target && !draft.resource_candidate_id && <section>
      <Divider orientation="left">这次操作影响哪个业务对象？</Divider>
      {target.resource_candidates.length > 0
        ? <Radio.Group onChange={(event) => onReview({ schema_version: '1', operation: 'CONFIRM_RESOURCE_SLOT', candidate_id: event.target.value })}><Space direction="vertical">{target.resource_candidates.map((candidate) => <Radio key={candidate.candidate_id} value={candidate.candidate_id}>{candidate.label}</Radio>)}</Space></Radio.Group>
        : <Alert type="warning" showIcon message="无法唯一识别业务对象" description="请重新演示一次，并在操作中使用一个明确的测试对象。" />}
    </section>}
    {variables.some((variable) => variable.status !== 'CONFIRMED') && <>
      <Divider orientation="left">动态业务信息来自哪里？</Divider>
      <Space direction="vertical" className="full-width">{variables.filter((variable) => variable.status !== 'CONFIRMED').map((variable) => <Card size="small" key={variable.name} title={<Space><Typography.Text strong>{variable.name}</Typography.Text><Tag color="gold">请选择业务来源</Tag></Space>}>
        <Radio.Group value={sources[variable.name]} onChange={(event) => onSourcesChange({ ...sources, [variable.name]: event.target.value })}>
          <Space direction="vertical">{variable.candidate_sources.map((source, index) => { const sourceStep = draft.steps.find((step) => step.id === source.source_step_id); const value = `${source.source_step_id}|${source.source_event_sequence}|${source.json_path}`; return <Radio key={value} value={value}>来自“{sourceStep?.name ?? `前序业务步骤 ${index + 1}`}”</Radio> })}</Space>
        </Radio.Group>
      </Card>)}</Space>
    </>}
    {!canFinalize && <Alert className="recording-review-warning" type="warning" showIcon message="还需要一个业务选择" description="完成上面的选择即可保存；界鉴不会要求你编辑请求路径或数据位置。" />}
    {canFinalize && <Alert type="success" showIcon message="业务含义已经整理完成" description="可以保存这次演示并继续确认真实结果。" />}
  </Card>
}
