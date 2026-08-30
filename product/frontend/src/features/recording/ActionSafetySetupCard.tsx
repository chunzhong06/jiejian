/* 真实结果与恢复行动卡：展示业务事实和缺口，不在 Recording 中审批权限意图。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Descriptions, Form, Radio, Space, Tag, Typography } from 'antd'
import type { ActionSafetySetupViewDto, ConfirmActionSafetySetupInput } from '../../api/recordings'

export function ActionSafetySetupCard({ setup, busy, onConfirm, onSupplement }: {
  setup: ActionSafetySetupViewDto
  busy: boolean
  onConfirm: (input: ConfirmActionSafetySetupInput) => void
  onSupplement: (purpose: 'OBSERVATION' | 'RECOVERY') => void
}) {
  const [observationId, setObservationId] = useState<string>()
  const [recoveryId, setRecoveryId] = useState<string>()

  useEffect(() => {
    setObservationId(setup.observation_candidates.length === 1 ? setup.observation_candidates[0].candidate_id : undefined)
    setRecoveryId(setup.recovery_candidates.length === 1 ? setup.recovery_candidates[0].candidate_id : undefined)
  }, [setup.recording_id, setup.observation_candidates.length, setup.recovery_candidates.length])

  const resource = setup.resource_candidates[0]
  const submit = () => onConfirm({
    resource_candidate_id: resource?.candidate_id,
    observation_candidate_id: observationId ?? null,
    recovery_candidate_id: recoveryId ?? null,
  })

  return <Card className="action-safety-card" title="真实结果与恢复" extra={setup.ready ? <Tag color="success">准备完成</Tag> : <Tag color="warning">还需补充</Tag>}>
    <Space direction="vertical" size={20} className="full-width action-safety-content">
      <Typography.Paragraph type="secondary">界鉴只整理这次操作真实影响什么、如何独立确认以及怎样恢复现场；谁应该允许或拒绝仍由权限审批决定。</Typography.Paragraph>
      <Descriptions bordered size="middle" column={1}>
        <Descriptions.Item label="影响什么业务对象">{resource?.label ?? '尚未识别，请重新演示'}</Descriptions.Item>
        <Descriptions.Item label="真实会发生什么">{setup.business_result ?? '尚未形成唯一业务结果'}</Descriptions.Item>
        <Descriptions.Item label="如何独立确认">{setup.observation_status === 'READY' ? '已准备独立验证方式' : '还缺独立验证方式'}</Descriptions.Item>
        <Descriptions.Item label="如何恢复现场">{setup.recovery_status === 'NOT_REQUIRED' ? '只读操作，不需要恢复' : setup.recovery_status === 'READY' ? '已准备恢复方法' : '还缺恢复测试现场的方法'}</Descriptions.Item>
      </Descriptions>
      {setup.observation_status === 'MISSING' && setup.observation_candidates.length === 0 && <Alert type="warning" showIcon message="还缺独立验证方式" action={<Button loading={busy} onClick={() => onSupplement('OBSERVATION')}>补录验证操作</Button>} />}
      {setup.observation_candidates.length > 1 && <section><Typography.Text strong>选择真实验证方式</Typography.Text><Radio.Group value={observationId} onChange={(event) => setObservationId(event.target.value)}><Space direction="vertical">{setup.observation_candidates.map((item) => <Radio key={item.candidate_id} value={item.candidate_id}>{item.label}</Radio>)}</Space></Radio.Group></section>}
      {setup.state_changing && setup.recovery_status === 'MISSING' && setup.recovery_candidates.length === 0 && <Alert type="warning" showIcon message="还缺恢复测试现场的方法" action={<Button loading={busy} onClick={() => onSupplement('RECOVERY')}>补录恢复操作</Button>} />}
      {setup.recovery_candidates.length > 1 && <section><Typography.Text strong>选择恢复测试现场的方法</Typography.Text><Radio.Group value={recoveryId} onChange={(event) => setRecoveryId(event.target.value)}><Space direction="vertical">{setup.recovery_candidates.map((item) => <Radio key={item.candidate_id} value={item.candidate_id}>{item.label}</Radio>)}</Space></Radio.Group></section>}
      <Form id="recording-safety-setup" onFinish={submit} />
      {setup.ready && <Alert type="success" showIcon message="业务流程已经准备完成" description="现在可以进入权限页，由人确认哪些账号应该允许或拒绝。" />}
    </Space>
  </Card>
}
