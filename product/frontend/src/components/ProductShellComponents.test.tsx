// 验证 Web V1 壳共享组件直接消费统一产品步骤、键盘焦点和唯一主动作。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApplicationSwitcher } from './ApplicationSwitcher'
import { DesktopProcessNavigation, MobileProcessNavigation } from './ProcessNavigation'
import { TaskActionBar } from './TaskActionBar'

const steps = [
  { key: 'application' as const, label: '应用接入', route: '/application' as const, status: 'COMPLETE' as const, status_label: '已完成' },
  { key: 'account' as const, label: '测试账号', route: '/identities' as const, status: 'COMPLETE' as const, status_label: '已完成' },
  { key: 'flow' as const, label: '业务流程', route: '/flows' as const, status: 'COMPLETE' as const, status_label: '已完成' },
  { key: 'check' as const, label: '权限与检查', route: '/check' as const, status: 'CURRENT' as const, status_label: '当前步骤' },
  { key: 'result' as const, label: '检查结果', route: '/results' as const, status: 'UPCOMING' as const, status_label: '尚未开始' },
  { key: 'history' as const, label: '历史变化', route: '/history' as const, status: 'EMPTY' as const, status_label: '暂无历史' },
]

describe('Web V1 产品壳共享组件', () => {
  it('流程完成状态来自统一产品步骤，当前 route 只标记页面焦点', () => {
    render(<DesktopProcessNavigation route="/flows" steps={steps} onNavigate={vi.fn()} />)
    expect(screen.getByRole('button', { name: /工作台/ })).toBeInTheDocument()
    expect(screen.getByText('检查流程')).toBeInTheDocument()
    expect(screen.getByText('辅助工具')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /AI 工具/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /运行环境/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /业务流程/ })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name: /权限与检查.*当前步骤/ })).toBeInTheDocument()
    expect(screen.getAllByText('已完成')).toHaveLength(3)
  })

  it('窄屏抽屉关闭后把焦点还给流程按钮', async () => {
    const onNavigate = vi.fn()
    render(<MobileProcessNavigation route="/check" steps={steps} onNavigate={onNavigate} />)
    const trigger = screen.getByRole('button', { name: '打开检查流程' })
    trigger.focus()
    fireEvent.click(trigger)
    await waitFor(() => expect(screen.getByRole('button', { name: /权限与检查/ })).toHaveFocus())
    fireEvent.click(await screen.findByRole('button', { name: /检查结果/ }))
    expect(onNavigate).toHaveBeenCalledWith('/results')
    await waitFor(() => expect(trigger).toHaveFocus())
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
