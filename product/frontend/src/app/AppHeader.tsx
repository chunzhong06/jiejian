/* 全局顶部栏：呈现当前应用、活动任务和结构化系统工具入口。 */

import { Button, Dropdown, Layout, Space, Typography } from 'antd'
import { DownOutlined, LogoutOutlined, SettingOutlined, RobotOutlined, CloudServerOutlined } from '@ant-design/icons'
import type { LLMProfile, AIAssistanceSettings } from '../api/llm'
import type { SystemStatus } from '../api/system'

export function aiStatusLabel(
  profiles: LLMProfile[],
  settings: AIAssistanceSettings,
  profilesFailed: boolean,
  settingsFailed: boolean,
) {
  if (profilesFailed || settingsFailed) return 'AI辅助 · 状态未知'
  if (!settings.enabled) return 'AI辅助 · 未开启'
  if (!settings.default_profile_name) return 'AI辅助 · 待配置'
  const profile = profiles.find((item) => item.profile_name === settings.default_profile_name)
  if (!profile) return 'AI辅助 · 待配置'
  if (profile.model) return `AI辅助 · ${profile.model}`
  return 'AI辅助 · 已配置'
}

export function systemStatusLabel(status: SystemStatus) {
  return status.api === 'available' && status.worker === 'running' && status.browser === 'available'
    ? '系统正常'
    : '系统需处理'
}

type AppHeaderProps = {
  projectName?: string | null
  activeTask?: { kind?: string }
  profiles: LLMProfile[]
  aiSettings: AIAssistanceSettings
  profilesFailed: boolean
  settingsFailed: boolean
  systemStatus: SystemStatus
  onNavigate: (path: string) => void
  onOpenAI: () => void
  onRequestShutdown: () => void
}

export function AppHeader({
  projectName,
  activeTask,
  profiles,
  aiSettings,
  profilesFailed,
  settingsFailed,
  systemStatus,
  onNavigate,
  onOpenAI,
  onRequestShutdown,
}: AppHeaderProps) {
  const applicationLabel = projectName?.trim() ? `当前应用：${projectName.trim()}` : projectName === undefined || projectName === null ? '尚未选择应用' : '当前应用：未命名应用'
  const settingsMenu = {
    items: [
      { key: '/settings/models', icon: <RobotOutlined />, label: '模型服务' },
      { key: '/settings/system', icon: <CloudServerOutlined />, label: '运行环境' },
    ],
    onClick: ({ key }: { key: string }) => onNavigate(key),
  }
  return <Layout.Header className="topbar">
    <div className="topbar-left">
      <Typography.Text className="topbar-context" title={applicationLabel}>{applicationLabel}</Typography.Text>
      {activeTask && <Button type="link" onClick={() => onNavigate(activeTask.kind === 'RUN' ? '/checks/start' : '/apps/flows')}>
        {activeTask.kind === 'RUN' ? '正在检查 · 查看' : '正在录制 · 查看'}
      </Button>}
    </div>
    <Space className="topbar-tools" size="small">
      <Button type="text" icon={<RobotOutlined />} aria-label="打开 AI 辅助设置" onClick={onOpenAI}>{aiStatusLabel(profiles, aiSettings, profilesFailed, settingsFailed)}</Button>
      <Button type="text" icon={<CloudServerOutlined />} aria-label={systemStatusLabel(systemStatus)} onClick={() => onNavigate('/settings/system')}>{systemStatusLabel(systemStatus)}</Button>
      <Dropdown menu={settingsMenu} trigger={['click']}>
        <Button type="text" aria-label="设置与更多" icon={<SettingOutlined />}>设置与更多 <DownOutlined /></Button>
      </Dropdown>
      <Button type="text" aria-label="退出界鉴" icon={<LogoutOutlined />} onClick={onRequestShutdown}>退出界鉴</Button>
    </Space>
  </Layout.Header>
}
