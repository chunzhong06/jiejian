// 官方示例提示条只标明当前上下文和权威待办，不建立第二套线性步骤。

import { Button, Tag, Typography } from 'antd'
import type { OfficialExperienceDto } from '../api/experience'
import type { ProductStatusDto } from '../api/projects'

export function OfficialSampleSetupBar({
  status,
  experience,
  preparingIdentities,
  onPrepareIdentities,
  onOpenVerification,
}: {
  status: ProductStatusDto | null
  experience: OfficialExperienceDto | null
  preparingIdentities: boolean
  onPrepareIdentities: () => void
  onOpenVerification?: () => void
}) {
  if (!status?.project || !experience?.active || status.project.project_id !== experience.project_id) return null
  const attention = status.attention_items?.[0]
  return <aside className="official-sample-setup-bar" aria-label="官方示例状态">
    <div className="official-sample-setup-copy">
      <Tag color="blue">官方示例运行中</Tag>
      <Typography.Text strong>{attention?.label ?? '当前示例没有待处理事项'}</Typography.Text>
      <Typography.Text type="secondary">{attention?.description ?? '可以进入展示模式，查看同一份正式检查结果。'}</Typography.Text>
    </div>
    {!experience.identities_ready && <Button loading={preparingIdentities} onClick={onPrepareIdentities}>准备官方测试账号</Button>}
    {status.latest_result && onOpenVerification && <Button type="primary" onClick={onOpenVerification}>查看现场验证</Button>}
  </aside>
}
