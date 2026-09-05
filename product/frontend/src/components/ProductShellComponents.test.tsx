// 验证产品壳直接消费长期工作区状态，并保留键盘焦点和明确主动作。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApplicationSwitcher } from './ApplicationSwitcher'
import { DesktopModuleNavigation, MobileModuleNavigation } from './ModuleNavigation'
import { TaskActionBar } from './TaskActionBar'

const areas = [
  { key: 'overview' as const, label: '工作台', description: '查看全局状态', route: '/workspace' as const, status: 'READY' as const, status_label: '持续更新' },
  { key: 'changes' as const, label: '变化', description: '核对 Agent 修改', route: '/changes' as const, status: 'NEEDS_ATTENTION' as const, status_label: '需要处理' },
  { key: 'permissions' as const, label: '权限', description: '维护权限边界', route: '/permissions' as const, status: 'READY' as const, status_label: '规则已建立' },
  { key: 'tests' as const, label: '测试', description: '准备、运行与结果', route: '/tests' as const, status: 'BLOCKED' as const, status_label: '当前不可检查' },
]

describe('Web V1 产品壳共享组件', () => {
  it('区域状态来自统一产品状态，当前 route 只标记页面焦点', () => {
    render(<DesktopModuleNavigation route="/flows" areas={areas} onNavigate={vi.fn()} />)
    expect(screen.getByText('专项工作')).toBeInTheDocument()
    expect(document.querySelector('.module-workbench-group')).toContainElement(screen.getByRole('button', { name: /工作台.*持续更新/ }))
    expect(screen.queryByText('辅助工具')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /AI 工具/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /运行环境/ })).not.toBeInTheDocument()
    expect(document.querySelector('.module-navigation-utilities')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /AI 辅助/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '退出界鉴' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /权限.*规则已建立/ })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: /变化.*需要处理/ })).toBeInTheDocument()
    expect(screen.queryByText(/第 .* 步/)).not.toBeInTheDocument()
  })

  it('窄屏抽屉关闭后把焦点还给流程按钮', async () => {
    const onNavigate = vi.fn()
    render(<MobileModuleNavigation route="/validation" areas={areas} onNavigate={onNavigate} />)
    const trigger = screen.getByRole('button', { name: '打开持续验证工作区' })
    trigger.focus()
    fireEvent.click(trigger)
    await waitFor(() => expect(screen.getByRole('button', { name: /检查与结果.*当前不可检查/ })).toHaveFocus())
    fireEvent.click(await screen.findByRole('button', { name: /变化与修复.*需要处理/ }))
    expect(onNavigate).toHaveBeenCalledWith('/changes')
    await waitFor(() => expect(trigger).toHaveFocus())
  })

  it('窄屏位于工作台时把抽屉焦点交给独立主入口', async () => {
    render(<MobileModuleNavigation route="/workspace" areas={areas} onNavigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '打开持续验证工作区' }))
    await waitFor(() => expect(screen.getByRole('button', { name: /工作台.*持续更新/ })).toHaveFocus())
  })

  it('应用切换只返回服务端列表中的应用，并保留接入新应用入口', async () => {
    const projects = [{ project_id: 'p1', name: '演示一号' }, { project_id: 'p2', name: '演示二号' }]
    const onSelect = vi.fn()
    const onConnectNew = vi.fn()
    render(<ApplicationSwitcher projects={projects} selected={projects[0]} onSelect={onSelect} onConnectNew={onConnectNew} onRemoveCurrent={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '切换应用，当前：演示一号' }))
    fireEvent.click(await screen.findByText('演示二号'))
    expect(onSelect).toHaveBeenCalledWith(projects[1])
  })

  it('当前应用菜单提供独立的移除入口', async () => {
    const project = { project_id: 'p1', name: '演示一号' }
    const onRemoveCurrent = vi.fn()
    render(<ApplicationSwitcher projects={[project]} selected={project} onSelect={vi.fn()} onConnectNew={vi.fn()} onRemoveCurrent={onRemoveCurrent} />)
    fireEvent.click(screen.getByRole('button', { name: '切换应用，当前：演示一号' }))
    fireEvent.click(await screen.findByText('移除当前应用'))
    expect(onRemoveCurrent).toHaveBeenCalledOnce()
  })

  it('底部动作区统一返回、只读刷新、明确重新开始副作用和唯一主动作', async () => {
    const onRestart = vi.fn()
    render(<TaskActionBar
      back={{ label: '返回上一步', onClick: vi.fn() }}
      refresh={{ label: '刷新状态', onClick: vi.fn() }}
      restart={{ label: '重新开始', onClick: onRestart, confirm: { title: '重新开始？', description: '会丢弃当前未保存内容。', okText: '确认重新开始' } }}
      primary={{ label: '继续检查', onClick: vi.fn() }}
    />)
    expect(screen.getByRole('button', { name: '刷新状态' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '继续检查' })).toHaveClass('ant-btn-primary')
    expect(document.querySelectorAll('.task-action-bar .ant-btn-primary')).toHaveLength(1)
    expect(Array.from(document.querySelectorAll('.task-action-bar button')).map((button) => button.textContent)).toEqual(['返回上一步', '刷新状态', '重新开始', '继续检查'])
    fireEvent.click(screen.getByRole('button', { name: '重新开始' }))
    expect(await screen.findByText('会丢弃当前未保存内容。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认重新开始' }))
    expect(onRestart).toHaveBeenCalledOnce()
  })
})
