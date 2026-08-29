// 评委导览条：只从当前 ProductStatus 与活跃体验推导七个用户决定中的当前一项。

import { Button, Tag, Typography } from 'antd'
import type { OfficialExperienceDto } from '../api/experience'
import type { ProductStatusDto } from '../api/projects'

const decisions = [
  '开始官方示例并确认本机运行',
  '确认两个权限组与“导出完整项目资料包”',
  '准备 Alice、Bob 官方测试账号；主演示比较负责人 Alice 与成员 Bob',
  '用正常有权限的 Alice 作为控制组真实录制，并告诉界鉴怎样确认结果和恢复现场',
  '明确确认 Alice 应允许、Bob 应拒绝',
  '核对真实检查范围并明确开始检查',
  '检查完成后进入查看结果',
] as const

function currentDecision(status: ProductStatusDto, experience: OfficialExperienceDto) {
  const action = status.next_action.action
  if (['CONNECT_APPLICATION', 'CONFIRM_TARGET', 'AUTHORIZE_SOURCE_ANALYSIS', 'REVIEW_DISCOVERY'].includes(action)) return 2
  if (!experience.identities_ready || status.next_action.route === '/identities') return 3
  if (status.next_action.route === '/flows') return 4
  if (action === 'REVIEW_PERMISSION') return 5
  if (action === 'RUN_CHECK') return 6
  return 7
}

export function JudgeGuideBar({
  status,
  experience,
  preparingIdentities,
  onPrepareIdentities,
}: {
  status: ProductStatusDto | null
  experience: OfficialExperienceDto | null
  preparingIdentities: boolean
  onPrepareIdentities: () => void
}) {
  if (
    !status?.project
    || !experience?.active
    || experience.experience_mode !== 'GUIDED'
    || status.project.project_id !== experience.project_id
  ) return null
  const step = currentDecision(status, experience)
  return <aside className="judge-guide-bar" aria-label="评委导览">
    <div className="judge-guide-copy">
      <Tag color="blue">评委导览 · {step}/7</Tag>
      <Typography.Text strong>{decisions[step - 1]}</Typography.Text>
      <Typography.Text type="secondary">当前提示来自应用真实准备状态；导览不会代替确认、录制或开始检查。</Typography.Text>
    </div>
    {step === 3 && <Button loading={preparingIdentities} onClick={onPrepareIdentities}>准备官方测试账号</Button>}
  </aside>
}
