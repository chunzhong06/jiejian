/* 录制准备卡：选择已确认业务动作、已准备测试身份和有界录制时长。 */

import { Alert, Card, Select, Space, Typography } from 'antd'
import type { RecordingActionDto, RecordingTestIdentityDto } from '../../api/recordings'

export function RecordingSetupCard({ actions, identities, actionId, testIdentityId, duration, disabled, onActionChange, onIdentityChange, onDurationChange }: {
  actions: RecordingActionDto[]
  identities: RecordingTestIdentityDto[]
  actionId?: string
  testIdentityId?: string
  duration: number
  disabled: boolean
  onActionChange: (value: string) => void
  onIdentityChange: (value: string) => void
  onDurationChange: (value: number) => void
}) {
  return <Card className="recording-setup-card" title="选择业务动作和测试账号">
    {actions.length === 0 || identities.length === 0
      ? <Alert type="info" showIcon message="还不能开始录制" description={actions.length === 0 ? '请先在应用接入中确认至少一个业务动作。' : '请先准备一个通常能够成功完成该动作的测试账号。'} />
      : <div className="recording-setup-grid">
        <label><Typography.Text strong>要录制的业务动作</Typography.Text><Select aria-label="选择业务动作" value={actionId} disabled={disabled} onChange={onActionChange} options={actions.map((item) => ({ value: item.action_candidate_id, label: item.display_name }))} /></label>
        <label><Typography.Text strong>用于录制的测试账号</Typography.Text><Select aria-label="选择测试账号" placeholder="选择一个已准备账号" value={testIdentityId} disabled={disabled} onChange={onIdentityChange} options={identities.map((item) => ({ value: item.test_identity_id, label: <Space><Typography.Text strong>{item.label}</Typography.Text><Typography.Text type="secondary">{item.role_display_name}</Typography.Text></Space> }))} /></label>
      </div>}
  </Card>
}
