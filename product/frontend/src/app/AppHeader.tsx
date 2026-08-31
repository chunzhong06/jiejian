/* 全局顶部栏：呈现当前应用、活动任务和结构化系统工具入口。 */

import { Button, Layout, Space, Typography } from 'antd'
import { ApiOutlined, LogoutOutlined, RobotOutlined, CloudServerOutlined } from '@ant-design/icons'
import type { LLMProfile, AIAssistanceSettings } from '../api/llm'
import type { MCPAccessView } from '../api/mcp'
import type { ProjectDto } from '../api/projects'
import type { SystemStatus } from '../api/system'
import { ApplicationSwitcher } from '../components/ApplicationSwitcher'

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

export function mcpStatusLabel(status: MCPAccessView | null, failed: boolean) {
  if (failed) return 'AI 工具 · 状态未知'
  if (!status) return 'AI 工具 · 正在读取'
  if (!status.paired) return 'AI 工具 · 未连接'
  if (status.client_connected) return `AI 工具 · ${status.client_name?.trim() || '已连接'}`
  if (status.accepting_connections) return 'AI 工具 · 等待连接'
  return 'AI 工具 · 已暂停'
}

type AppHeaderProps = {
  projects: ProjectDto[]
  selected: ProjectDto | null
  activeTask?: { kind?: string }
  profiles: LLMProfile[]
  aiSettings: AIAssistanceSettings
  profilesFailed: boolean
  settingsFailed: boolean
  mcpStatus: MCPAccessView | null
  mcpStatusFailed: boolean
  systemStatus: SystemStatus
  onSelectProject: (project: ProjectDto) => void
  onConnectNew: () => void
  onRemoveCurrent: () => void
  onNavigate: (path: string) => void
  onOpenAI: () => void
  onRequestShutdown: () => void
}

export function AppHeader({
  projects,
  selected,
  activeTask,
  profiles,
  aiSettings,
  profilesFailed,
  settingsFailed,
  mcpStatus,
  mcpStatusFailed,
  systemStatus,
  onSelectProject,
  onConnectNew,
  onRemoveCurrent,
  onNavigate,
  onOpenAI,
  onRequestShutdown,
}: AppHeaderProps) {
  return <Layout.Header className="topbar">
    <div className="topbar-left">
      <Typography.Text className="topbar-context">当前应用</Typography.Text>
      <ApplicationSwitcher projects={projects} selected={selected} onSelect={onSelectProject} onConnectNew={onConnectNew} onRemoveCurrent={onRemoveCurrent} />
      {activeTask && <Button type="link" onClick={() => onNavigate(activeTask.kind === 'RUN' ? '/validation' : '/flows')}>
        {activeTask.kind === 'RUN' ? '正在检查 · 查看' : '正在录制 · 查看'}
      </Button>}
    </div>
    <Space className="topbar-tools" size="small">
      <Button type="text" icon={<ApiOutlined />} aria-label="打开 AI 工具" onClick={() => onNavigate('/tools')}>{mcpStatusLabel(mcpStatus, mcpStatusFailed)}</Button>
      <Button type="text" icon={<RobotOutlined />} aria-label="打开 AI 辅助设置" onClick={onOpenAI}>{aiStatusLabel(profiles, aiSettings, profilesFailed, settingsFailed)}</Button>
      <Button type="text" icon={<CloudServerOutlined />} aria-label={systemStatusLabel(systemStatus)} onClick={() => onNavigate('/settings/system')}>{systemStatusLabel(systemStatus)}</Button>
      <Button type="text" aria-label="退出界鉴" icon={<LogoutOutlined />} onClick={onRequestShutdown}>退出界鉴</Button>
    </Space>
  </Layout.Header>
}
