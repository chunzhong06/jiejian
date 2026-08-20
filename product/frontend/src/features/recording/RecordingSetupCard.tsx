/* 录制准备卡：选择执行配置、单一身份和有界录制时长。 */

import { Alert, Button, Card, InputNumber, Select, Space, Typography } from 'antd'
import type { ExecutionProfileDto } from '../../api/executionProfiles'
import type { RecordingIdentityDto } from '../../api/recordings'
import { productTermLabel } from '../../app/presentation'

export function RecordingSetupCard({ profiles, identities, profileId, identityId, duration, busy, disabled, onProfileChange, onIdentityChange, onDurationChange, onCreate }: {
  profiles: ExecutionProfileDto[]
  identities: RecordingIdentityDto[]
  profileId?: string
  identityId?: string
  duration: number
  busy: boolean
  disabled: boolean
  onProfileChange: (value: string) => void
  onIdentityChange: (value: string) => void
  onDurationChange: (value: number) => void
  onCreate: () => void
}) {
  return <Card title="选择录制身份">
    {profiles.length === 0
      ? <Alert type="info" showIcon message="当前应用还没有已登记的执行配置" description="请先在权限规则中登记执行配置（ExecutionProfile），再回来选择录制身份。" />
      : <Space wrap size="middle">
        {profiles.length > 1 && <Select aria-label="选择执行配置" value={profileId} onChange={onProfileChange} style={{ minWidth: 220 }} options={profiles.map((item, index) => ({ value: item.profile_id, label: item.name ?? `执行配置 ${index + 1}` }))} />}
        <Select aria-label="选择录制身份" placeholder="选择一个身份" value={identityId} onChange={onIdentityChange} style={{ minWidth: 260 }} options={identities.map((item) => ({ value: item.identity_id, label: <Space><Typography.Text strong>{productTermLabel('role', item.role, false)}</Typography.Text><Typography.Text type="secondary">{productTermLabel('identity', item.identity_id, false)} · {item.identity_id}</Typography.Text></Space> }))} />
        <Space.Compact><InputNumber aria-label="最长录制时间（秒）" min={60} max={3600} value={duration} onChange={(value) => onDurationChange(value ?? 600)} /><Button disabled>秒</Button></Space.Compact>
        <Button type="primary" loading={busy} disabled={!profileId || !identityId || disabled} onClick={onCreate}>打开浏览器并准备登录</Button>
      </Space>}
  </Card>
}
