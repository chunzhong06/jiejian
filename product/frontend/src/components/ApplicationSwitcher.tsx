// 应用切换器：只在服务端返回的应用列表中切换上下文，并提供正式接入入口。

import { DeleteOutlined, DownOutlined, PlusOutlined, SwapOutlined } from '@ant-design/icons'
import { Button, Dropdown } from 'antd'
import type { ProjectDto } from '../api/projects'

export function ApplicationSwitcher({
  projects,
  selected,
  onSelect,
  onConnectNew,
  onRemoveCurrent,
}: {
  projects: ProjectDto[]
  selected: ProjectDto | null
  onSelect: (project: ProjectDto) => void
  onConnectNew: () => void
  onRemoveCurrent: () => void
}) {
  const currentLabel = selected ? selected.name?.trim() || '未命名应用' : '选择应用'
  const items = [
    ...projects.map((project) => ({
      key: project.project_id,
      label: project.name?.trim() || '未命名应用',
      icon: <SwapOutlined />,
    })),
    ...(projects.length > 0 ? [{ type: 'divider' as const }] : []),
    { key: 'connect-new', label: '接入新应用', icon: <PlusOutlined /> },
    ...(selected ? [{ key: 'remove-current', label: '移除当前应用', icon: <DeleteOutlined />, danger: true }] : []),
  ]
  return <Dropdown
    menu={{
      items,
      selectable: true,
      selectedKeys: selected ? [selected.project_id] : [],
      onClick: ({ key }) => {
        if (key === 'connect-new') onConnectNew()
        else if (key === 'remove-current') onRemoveCurrent()
        else {
          const project = projects.find((item) => item.project_id === key)
          if (project) onSelect(project)
        }
      },
    }}
    trigger={['click']}
  >
    <Button className="application-switcher" aria-label={`切换应用，当前：${selected ? currentLabel : '尚未选择'}`}>
      <span className="application-switcher-label">{currentLabel}</span><DownOutlined />
    </Button>
  </Dropdown>
}
