/* 全局顶部栏：呈现当前应用、活动任务和结构化系统工具入口。 */

import { Button, Dropdown, Layout, Space } from 'antd'
import { ApiOutlined, BgColorsOutlined, CloudServerOutlined, LogoutOutlined, MoreOutlined, RobotOutlined } from '@ant-design/icons'
import type { LLMProfile, AIAssistanceSettings } from '../api/llm'
import type { MCPAccessView } from '../api/mcp'
import type { ProjectDto } from '../api/projects'
import type { SystemStatus } from '../api/system'
import { ApplicationSwitcher } from '../components/ApplicationSwitcher'
import { useThemeMode, type ThemeMode } from './ThemeContext'

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
  const state = status.connection_state
    ?? (!status.paired ? 'DISABLED' : !status.accepting_connections ? 'PAUSED' : status.client_connected ? 'CONNECTED' : 'CREDENTIAL_READY')
  if (state === 'DISABLED') return 'AI 工具 · 未准备'
  if (state === 'CREDENTIAL_READY') return 'AI 工具 · 等待连接'
  if (state === 'AUTHENTICATED') return 'AI 工具 · 正在确认连接'
  if (state === 'CREDENTIAL_REJECTED') return 'AI 工具 · 凭据需更新'
  if (state === 'CONNECTED') return `AI 工具 · ${status.client_name?.trim() || '已连接'}`
  return 'AI 工具 · 已暂停'
}

type AppHeaderProps = {
  projects: ProjectDto[]
  selected: ProjectDto | null
  activeTask?: { kind?: string }
  mcpStatus: MCPAccessView | null
  mcpStatusFailed: boolean
  systemStatus: SystemStatus
  onSelectProject: (project: ProjectDto) => void
  onConnectNew: () => void
  onRemoveCurrent: () => void
  onNavigate: (path: string) => void
  aiLabel: string
  onOpenAI: () => void
  onRequestShutdown: () => void
}

export function AppHeader({
  projects,
  selected,
  activeTask,
  mcpStatus,
  mcpStatusFailed,
  systemStatus,
  onSelectProject,
  onConnectNew,
  onRemoveCurrent,
  onNavigate,
  aiLabel,
  onOpenAI,
  onRequestShutdown,
}: AppHeaderProps) {
  const { mode, setMode } = useThemeMode()
  const themeLabels: Record<ThemeMode, string> = { system: '跟随系统', light: '亮色', dark: '暗色' }
  const mcpLabel = mcpStatusLabel(mcpStatus, mcpStatusFailed)
  const mcpConnected = mcpStatus?.connection_state === 'CONNECTED' || mcpStatus?.client_connected === true
  const compactMcpLabel = mcpConnected ? mcpStatus?.client_name?.trim() || 'AI 工具' : 'AI 工具'
  const systemLabel = systemStatusLabel(systemStatus)
  return <Layout.Header className="topbar">
    <div className="topbar-left">
      <ApplicationSwitcher projects={projects} selected={selected} onSelect={onSelectProject} onConnectNew={onConnectNew} onRemoveCurrent={onRemoveCurrent} />
      {activeTask && <Button type="link" onClick={() => onNavigate(activeTask.kind === 'RUN' ? '/validation' : '/flows')}>
        {activeTask.kind === 'RUN' ? '正在检查 · 查看' : '正在录制 · 查看'}
      </Button>}
    </div>
    <Space className="topbar-tools" size="small">
      <Button type="text" icon={<ApiOutlined />} aria-label={`${mcpLabel}，打开 AI 工具`} onClick={() => onNavigate('/tools')}><span>{compactMcpLabel}</span><i className={`topbar-status-dot${mcpConnected ? ' is-connected' : ''}`} aria-hidden="true" /></Button>
      <Dropdown
        destroyOnHidden
        placement="bottomRight"
        trigger={['click']}
        menu={{
          items: [
            { key: 'ai', icon: <RobotOutlined />, label: `AI 辅助 · ${aiLabel.replace(/^AI辅助 · /, '')}` },
            { key: 'system', icon: <CloudServerOutlined />, label: systemLabel },
            { type: 'divider' },
            {
              key: 'theme', icon: <BgColorsOutlined />, label: `主题 · ${themeLabels[mode]}`, children: [
                { key: 'theme:system', label: '跟随系统' },
                { key: 'theme:light', label: '亮色主题' },
                { key: 'theme:dark', label: '暗色主题' },
              ],
            },
            { type: 'divider' },
            { key: 'shutdown', danger: true, icon: <LogoutOutlined />, label: '退出界鉴' },
          ],
          onClick: ({ key }) => {
            if (key === 'ai') onOpenAI()
            else if (key === 'system') onNavigate('/settings/system')
            else if (key === 'shutdown') onRequestShutdown()
            else if (key.startsWith('theme:')) setMode(key.slice('theme:'.length) as ThemeMode)
          },
        }}
      >
        <Button type="text" icon={<MoreOutlined />} aria-label={`设置与更多，${systemLabel}`}><i className={`topbar-status-dot${systemLabel === '系统正常' ? ' is-connected' : ' is-warning'}`} aria-hidden="true" /></Button>
      </Dropdown>
    </Space>
  </Layout.Header>
}
