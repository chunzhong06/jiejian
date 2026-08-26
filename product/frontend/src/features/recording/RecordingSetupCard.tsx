/* 录制准备卡：选择已确认业务动作、已准备测试身份和有界录制时长。 */

import { Alert, Button, Card, InputNumber, Select, Space, Typography } from 'antd'
import type { RecordingActionDto, RecordingTestIdentityDto } from '../../api/recordings'

export function RecordingSetupCard({ actions, identities, actionId, testIdentityId, duration, busy, disabled, onActionChange, onIdentityChange, onDurationChange, onCreate }: {
  actions: RecordingActionDto[]
  identities: RecordingTestIdentityDto[]
  actionId?: string
  testIdentityId?: string
  duration: number
  busy: boolean
  disabled: boolean
  onActionChange: (value: string) => void
  onIdentityChange: (value: string) => void
  onDurationChange: (value: number) => void
  onCreate: () => void
}) {
  return <Card title="选择要录制的业务动作">
    {actions.length === 0 || identities.length === 0
      ? <Alert type="info" showIcon message="还不能开始录制" description={actions.length === 0 ? '请先在应用理解中确认至少一个业务动作。' : '请先准备一个通常能够成功执行该动作的测试身份。'} />
      : <Space wrap size="middle">
        <Select aria-label="选择业务动作" value={actionId} onChange={onActionChange} style={{ minWidth: 260 }} options={actions.map((item) => ({ value: item.action_candidate_id, label: item.display_name }))} />
        <Select aria-label="选择测试身份" placeholder="选择一个已准备身份" value={testIdentityId} onChange={onIdentityChange} style={{ minWidth: 280 }} options={identities.map((item) => ({ value: item.test_identity_id, label: <Space><Typography.Text strong>{item.label}</Typography.Text><Typography.Text type="secondary">{item.role_display_name}</Typography.Text></Space> }))} />
        <Space.Compact><InputNumber aria-label="最长录制时间（秒）" min={60} max={3600} value={duration} onChange={(value) => onDurationChange(value ?? 600)} /><Button disabled>秒</Button></Space.Compact>
        <Button type="primary" loading={busy} disabled={!actionId || !testIdentityId || disabled} onClick={onCreate}>打开浏览器并开始准备</Button>
      </Space>}
  </Card>
}
