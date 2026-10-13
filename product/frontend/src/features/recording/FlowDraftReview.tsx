/* Recording 业务解释确认：只呈现真正无法自动消解的业务选择。 */

import { Alert, Button, Divider, Radio, Space, Typography } from 'antd'
import { useEffect, useState } from 'react'
import type { FlowDraftDto, RecordingReviewCommand } from '../../api/preparation/recordings'

// 只核对目标及其前置步骤真正要消费的变量；目标后的页面刷新不形成额外确认任务。
export function requiredDraftVariables(draft?: FlowDraftDto | null) {
  if(!draft?.target_step_id)return []
  const retained=new Set<string>(),pending=[draft.target_step_id]
  while(pending.length){const id=pending.pop()!;if(retained.has(id))continue;retained.add(id);pending.push(...(draft.steps.find(step=>step.id===id)?.depends_on_step_ids??[]))}
  return (draft.variables??[]).filter(variable=>!variable.consumer_step_ids||variable.consumer_step_ids.some(id=>retained.has(id)))
}

export function FlowDraftReview({ draft, actionName, sources, canFinalize, busy=false, onSourcesChange, onReview }: {
  draft: FlowDraftDto
  actionName: string
  sources: Record<string, string>
  canFinalize: boolean
  busy?: boolean
  onSourcesChange: (value: Record<string, string>) => void
  onReview: (command: RecordingReviewCommand) => void
}) {
  const executableSteps = draft.steps.filter((step) => step.method)
  const target = draft.steps.find((step) => step.id === draft.target_step_id)
  const variables = requiredDraftVariables(draft)
  const created = target?.resource_candidates.some(item=>item.consumer.startsWith('RESPONSE_'))
  const selected = target?.resource_candidates.find(item=>item.candidate_id===draft.resource_candidate_id)
  const [choosing,setChoosing]=useState(false)
  useEffect(()=>setChoosing(false),[draft.revision])

  return <section className="recording-review"><h2>{created?'确认这次新建的对象':'核对这次操作的业务对象'}</h2>
    <Typography.Paragraph>{created?`“${actionName}”的对象编号在操作成功后返回。确认哪个对象是这次创建的，界鉴会保存它的识别方式。`:`这次演示用于“${actionName}”。先确认业务对象，再保存操作流程。`}</Typography.Paragraph>
    {!draft.target_step_id && <section>
      <Typography.Text strong>哪一步真正完成了“{actionName}”？</Typography.Text>
      <Radio.Group disabled={busy} onChange={(event) => onReview({ schema_version: '1', operation: 'CONFIRM_TARGET_STEP', step_id: event.target.value })}>
        <Space direction="vertical">{executableSteps.map((step) => <Radio key={step.id} value={step.id}>{step.name}</Radio>)}</Space>
      </Radio.Group>
    </section>}
    {target && (!draft.resource_candidate_id||choosing) && <section>
      <Divider orientation="left">{created?'哪个是刚才创建的对象？':'这次操作影响哪个业务对象？'}</Divider>
      {target.resource_candidates.length > 0
        ? <Radio.Group className="recording-object-options" value={draft.resource_candidate_id} disabled={busy} onChange={(event) => onReview({ schema_version: '1', operation: 'CONFIRM_RESOURCE_SLOT', candidate_id: event.target.value, expected_revision:draft.revision })}>{target.resource_candidates.map((candidate) => <Radio key={candidate.candidate_id} value={candidate.candidate_id}><strong>{candidate.label}</strong><span>{candidate.consumer.startsWith('RESPONSE_')?'来自本次操作的真实响应':'来自本次操作的请求'}</span></Radio>)}</Radio.Group>
        : <Alert type="warning" showIcon message="尚未找到可确认的对象" description="可以从已保存的录制重新识别，无需再次创建。若响应缺失、被截断或没有对象编号，需要补齐响应依据；原业务要求继续保留。" />}
      <div className="recording-object-refresh"><span>旧录制可重新读取对象依据，不会再次操作应用。</span><Button loading={busy} onClick={()=>onReview({schema_version:'1',operation:'REFRESH_RESOURCE_CANDIDATES',expected_revision:draft.revision})}>重新识别已有录制</Button></div>
    </section>}
    {selected&&!choosing&&<section className="recording-object-confirmed"><div><span>已确认的对象</span><strong>{selected.label}</strong><Button type="link" disabled={busy} onClick={()=>setChoosing(true)}>更换对象</Button></div><p>{created?'本次编号用于保存演示对象及准备证明、恢复材料；创建操作保持原请求，不把旧编号塞进下一次创建请求。':'按已确认的位置保存操作和业务对象。'}</p></section>}
    {variables.some((variable) => variable.status !== 'CONFIRMED') && <>
      <Divider orientation="left">动态业务信息来自哪里？</Divider>
      <Space direction="vertical" className="full-width">{variables.filter((variable) => variable.status !== 'CONFIRMED').map((variable) => <section key={variable.name}><h3>{variable.name} · 请选择业务来源</h3>
        <Radio.Group value={sources[variable.name]} onChange={(event) => onSourcesChange({ ...sources, [variable.name]: event.target.value })}>
          <Space direction="vertical">{variable.candidate_sources.map((source, index) => { const sourceStep = draft.steps.find((step) => step.id === source.source_step_id); const value = `${source.source_step_id}|${source.source_event_sequence}|${source.json_path}`; return <Radio key={value} value={value}>来自“{sourceStep?.name ?? `前序业务步骤 ${index + 1}`}”</Radio> })}</Space>
        </Radio.Group>
      </section>)}</Space>
    </>}
    {!canFinalize && !(target && !target.resource_candidates.length) && <Alert className="recording-review-warning" type="warning" showIcon message={target&&!target.resource_candidates.length?"当前演示还不能保存":"还需要一个业务选择"} description={target&&!target.resource_candidates.length?"缺少业务对象绑定，已保留草稿；不能通过删除权限或编造对象放行。":"完成上面的选择即可保存；界鉴不会要求你编辑请求路径或数据位置。"} />}
    {canFinalize && <Alert type="success" showIcon message="业务含义已经整理完成" description="可以保存这次演示并继续确认真实结果。" />}
  </section>
}
