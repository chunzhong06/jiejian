/* =============================================================================
 * 真实观察与恢复确认卡
 *
 * 定位：把 Recording 产生的有限候选转换为用户明确确认的测试资源、观察和恢复事实。
 * 边界：只提交候选 ID 和可读名称；缺项显示覆盖缺口，不把候选或 HTTP 状态当作安全结论。
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Descriptions, Form, Input, Select, Space, Tag, Typography } from 'antd'
import type { ActionSafetySetupViewDto, ConfirmActionSafetySetupInput } from '../../api/recordings'

const gapLabels: Record<string, string> = {
  TEST_RESOURCE_UNCONFIRMED: '测试资源尚未确认',
  OBSERVATION_UNCONFIRMED: '缺少独立可信读取，检查不能证明真实结果',
  RECOVERY_UNCONFIRMED: '缺少安全恢复方式，状态变更动作不会自动执行',
  SECURITY_EFFECT_UNCONFIRMED: '尚未确认真正需要防止的安全影响',
}

function uniqueCandidatesById<T extends { candidate_id: string }>(items: T[]) {
  return [...new Map(items.map((item) => [item.candidate_id, item])).values()]
}

export function ActionSafetySetupCard({ setup, busy, onConfirm }: {
  setup: ActionSafetySetupViewDto
  busy: boolean
  onConfirm: (input: ConfirmActionSafetySetupInput) => void
}) {
  const resource = setup.resource_candidates[0]
  const confirmed = setup.confirmed_setup
  const [logicalName, setLogicalName] = useState('')
  const [resourceType, setResourceType] = useState('')
  const [observationId, setObservationId] = useState<string>()
  const [recoveryId, setRecoveryId] = useState<string>()
  const [effectId, setEffectId] = useState<string>()
  const [noRecoveryRequired, setNoRecoveryRequired] = useState(false)

  useEffect(() => {
    setLogicalName(confirmed?.resource.logical_name ?? `${setup.recording_identity.label}的测试资源`)
    setResourceType(confirmed?.resource.resource_type ?? resource?.suggested_resource_type ?? '业务资源')
    setObservationId(setup.observation_candidates.find((item) => item.source_step_id === confirmed?.observation?.source_step_id)?.candidate_id)
    setRecoveryId(setup.recovery_candidates.find((item) => item.source_step_id === confirmed?.recovery?.source_step_id)?.candidate_id)
    setEffectId(setup.security_effect_candidates.find((item) => item.kind === confirmed?.effect?.kind)?.candidate_id)
    setNoRecoveryRequired(confirmed?.recovery?.kind === 'NOT_REQUIRED')
  }, [setup.recording_id, setup.confirmed_setup?.resource.resource_id])

  const submit = () => {
    if (!resource) return
    onConfirm({
      resource_candidate_id: resource.candidate_id,
      logical_name: logicalName,
      resource_type: resourceType,
      owner_test_identity_id: setup.recording_identity.identity_id,
      observation_candidate_id: observationId ?? null,
      recovery_candidate_id: recoveryId ?? null,
      confirm_recovery_not_required: !setup.state_changing && noRecoveryRequired,
      security_effect_candidate_id: effectId ?? null,
    })
  }

  return <Card className="action-safety-card" title="确认真实结果与安全恢复" extra={setup.automatic_execution_allowed ? <Tag color="success">准备完成</Tag> : <Tag color="warning">存在覆盖缺口</Tag>}>
    <Space direction="vertical" size={24} className="full-width action-safety-content">
      <Typography.Paragraph type="secondary">下面的内容来自这次真实录制。只有你点击确认后才会成为检查事实；找不到可靠观察或恢复方式时会保留明确缺口，不会把请求表面结果当作安全通过。</Typography.Paragraph>
      {setup.gaps.length > 0 && <Alert type="warning" showIcon message="当前动作还不能安全自动检查" description={<ul>{setup.gaps.map((gap) => <li key={gap}>{gapLabels[gap] ?? gap}</li>)}</ul>} />}
      {setup.automatic_execution_allowed && <Alert type="success" showIcon message="资源、独立观察、安全恢复和真实影响已经确认" description="后续仍需由权限规则与执行配置完成最终编译；这里不会直接运行目标动作。" />}
      {resource ? <Descriptions bordered size="middle" column={1}>
        <Descriptions.Item label="测试资源来源">{resource.label}</Descriptions.Item>
        <Descriptions.Item label="录制中的有限标识"><Typography.Text code>{resource.actual_resource_id}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="资源所有者">{setup.recording_identity.label}（{setup.recording_identity.role_display_name}）</Descriptions.Item>
      </Descriptions> : <Alert type="error" showIcon message="录制中没有可确认的有限测试资源" />}
      <Form layout="vertical" className="action-safety-form">
        <div className="action-safety-resource-fields">
          <Form.Item label="资源名称" required><Input size="large" value={logicalName} maxLength={128} onChange={(event) => setLogicalName(event.target.value)} placeholder="例如：成员 A 的测试文档" /></Form.Item>
          <Form.Item label="资源类型" required><Input size="large" value={resourceType} maxLength={128} onChange={(event) => setResourceType(event.target.value)} placeholder="例如：文档" /></Form.Item>
        </div>
        <Form.Item className="action-safety-choice" label="怎样独立确认真实结果" extra="写、改、删动作不能把目标请求自己的响应作为唯一证据。">
          <Select size="large" allowClear aria-label="选择真实观察方式" placeholder="暂不确认，将形成覆盖缺口" value={observationId} onChange={setObservationId} options={uniqueCandidatesById(setup.observation_candidates).map((item) => ({ value: item.candidate_id, label: item.label }))} />
        </Form.Item>
        {setup.state_changing ? <Form.Item className="action-safety-choice" label="怎样恢复测试现场" extra="缺少恢复方式时，界鉴不会自动执行这个状态变更动作。">
          <Select size="large" allowClear aria-label="选择安全恢复方式" placeholder="暂不确认，将禁止自动执行" value={recoveryId} onChange={setRecoveryId} options={uniqueCandidatesById(setup.recovery_candidates).map((item) => ({ value: item.candidate_id, label: item.label }))} />
        </Form.Item> : <Form.Item><Checkbox checked={noRecoveryRequired} onChange={(event) => setNoRecoveryRequired(event.target.checked)}>我确认这是不会改变状态的读取动作，不需要恢复现场</Checkbox></Form.Item>}
        <Form.Item className="action-safety-choice" label="真正需要防止的影响" extra="这是用户确认的安全意图，不是系统或模型自动作出的漏洞结论。">
          <Select size="large" allowClear aria-label="选择安全影响" placeholder="暂不确认，将形成覆盖缺口" value={effectId} onChange={setEffectId} options={uniqueCandidatesById(setup.security_effect_candidates).map((item) => ({ value: item.candidate_id, label: item.label }))} />
        </Form.Item>
      </Form>
      {setup.security_effect_candidates.length === 0 && <Alert type="info" showIcon message="当前动作无法安全映射到受支持的真实影响" description="界鉴不会用“状态变更”兜底；该动作会保留覆盖缺口，后续可进入高级配置。" />}
      <Button type="primary" size="large" loading={busy} disabled={!resource || !logicalName.trim() || !resourceType.trim()} onClick={submit}>确认测试资源、观察与恢复</Button>
    </Space>
  </Card>
}
