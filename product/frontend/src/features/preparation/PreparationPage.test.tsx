// 验证测试准备页只按后端四态推进，并始终把人工确认留在现有详细页面。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type {
  PreparationItemDto,
  ProjectPreparationDto,
  ProjectReadinessDto,
} from '../../api/deferredChecks'
import { PreparationPage } from './PreparationPage'

function preparationItem(
  status: PreparationItemDto['status'],
  updates: Partial<PreparationItemDto> = {},
): PreparationItemDto {
  return {
    key: 'identity:alice',
    kind: 'IDENTITY',
    label: 'Alice 测试账号',
    status,
    description: status === 'READY' ? 'Alice 的登录状态当前可用。' : 'Alice 需要完成登录。',
    next_path: status === 'READY' ? null : '/identities',
    next_label: status === 'READY' ? null : '管理测试账号',
    reason_codes: status === 'READY' ? [] : ['TEST_IDENTITY_NOT_PREPARED'],
    auto_action: status === 'AUTO' ? 'ENSURE_IDENTITY_RECORD' : null,
    role_candidate_id: null,
    action_candidate_id: null,
    recording_id: null,
    identity_id: null,
    owner_test_identity_id: null,
    ...updates,
  }
}

function preparation(
  items: PreparationItemDto[],
  updates: Partial<ProjectPreparationDto> = {},
): ProjectPreparationDto {
  const next = items.find((item) => item.status !== 'READY')
  const ready = items.length > 0 && items.every((item) => item.status === 'READY')
  return {
    project_id: 'p1',
    ready,
    items,
    next_item_key: next?.key ?? null,
    next_path: next?.status === 'USER' ? next.next_path : ready ? '/validation' : null,
    next_label: next?.status === 'USER' ? next.next_label : ready ? '前往验证运行' : next?.status === 'AUTO' ? '继续准备' : null,
    auto_action_count: items.filter((item) => item.status === 'AUTO').length,
    user_action_count: items.filter((item) => item.status === 'USER').length,
    blocked_count: items.filter((item) => item.status === 'BLOCKED').length,
    external_blockers: [],
    ...updates,
  }
}

function readiness(current: ProjectPreparationDto): ProjectReadinessDto {
  return {
    project_id: 'p1',
    project_status: 'READY',
    application_connected: true,
    endpoint_status: 'CONFIRMED',
    source_analysis_status: 'COMPLETED',
    discovered_role_count: 2,
    confirmed_role_count: 2,
    discovered_action_count: 1,
    confirmed_action_count: 1,
    execution_profile_available: current.ready,
    completed_flow_available: current.ready,
    active_contract_available: current.ready,
    current_scope_runnable: current.ready,
    remaining_gap_count: current.ready ? 0 : 1,
    active_tasks: [],
    latest_verified_run_id: null,
    next_required_action: current.ready ? 'RUN_CHECK' : 'RECORD_FLOW',
    preparation: current,
  }
}

describe('PreparationPage', () => {
  it('READY 项只显示后端给出的当前可用事实', () => {
    render(<PreparationPage
      readiness={readiness(preparation([preparationItem('READY')]))}
      onPrepareSafe={vi.fn()}
      onNavigate={vi.fn()}
    />)

    expect(screen.getByText('Alice 测试账号')).toBeInTheDocument()
    expect(screen.getByText('当前可用')).toBeInTheDocument()
    expect(screen.queryByText('TEST_IDENTITY_NOT_PREPARED')).not.toBeInTheDocument()
  })

  it('AUTO 项点击继续准备只调用 prepare-safe 适配动作', async () => {
    const onPrepareSafe = vi.fn().mockResolvedValue(undefined)
    const onNavigate = vi.fn()
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('AUTO', { description: '可以创建非秘密测试账号记录。' }),
      ]))}
      onPrepareSafe={onPrepareSafe}
      onNavigate={onNavigate}
    />)

    fireEvent.click(screen.getByRole('button', { name: '继续准备' }))
    await waitFor(() => expect(onPrepareSafe).toHaveBeenCalledOnce())
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('USER 项使用后端 next_path 进入现有人工页面', () => {
    const onNavigate = vi.fn()
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('USER', { next_path: '/identities', next_label: '管理测试账号' }),
      ]))}
      onPrepareSafe={vi.fn()}
      onNavigate={onNavigate}
    />)

    fireEvent.click(screen.getByRole('button', { name: '管理测试账号' }))
    expect(onNavigate).toHaveBeenCalledOnce()
    expect(onNavigate).toHaveBeenCalledWith('/identities')
  })

  it('BLOCKED 项显示原因且不会调用任何写动作', () => {
    const onPrepareSafe = vi.fn()
    const onNavigate = vi.fn()
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('BLOCKED', {
          kind: 'OBSERVATION',
          label: '结果确认方式',
          description: '当前还没有可靠的结果确认方式。',
          next_path: '/flows',
          next_label: '补录结果观察流程',
        }),
      ]))}
      onPrepareSafe={onPrepareSafe}
      onNavigate={onNavigate}
    />)

    expect(screen.getByText('当前还没有可靠的结果确认方式。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '继续准备' })).toBeDisabled()
    expect(onPrepareSafe).not.toHaveBeenCalled()
    expect(onNavigate).not.toHaveBeenCalled()
  })

  it('external blocker 按后端 next_item_key 导航到正式区域', () => {
    const onPrepareSafe = vi.fn()
    const onNavigate = vi.fn()
    const current = preparation([preparationItem('BLOCKED')], {
      next_item_key: 'permission-incomplete',
      next_path: '/permissions',
      next_label: '去确认权限规则',
      external_blockers: [{
        key: 'permission-incomplete',
        category: 'PERMISSION',
        label: '权限规则尚未形成当前可执行映射',
        description: '请先确认权限要求。',
        next_path: '/permissions',
        next_label: '去确认权限规则',
        reason_codes: ['PERMISSION_INTENT_NEEDS_REVIEW'],
      }],
    })
    render(<PreparationPage
      readiness={readiness(current)}
      onPrepareSafe={onPrepareSafe}
      onNavigate={onNavigate}
    />)

    fireEvent.click(screen.getByRole('button', { name: '去确认权限规则' }))
    expect(onNavigate).toHaveBeenCalledWith('/permissions')
    expect(onPrepareSafe).not.toHaveBeenCalled()
  })

  it('全部 READY 后唯一主操作进入验证运行', () => {
    const onNavigate = vi.fn()
    render(<PreparationPage
      readiness={readiness(preparation([preparationItem('READY')]))}
      onPrepareSafe={vi.fn()}
      onNavigate={onNavigate}
    />)

    fireEvent.click(screen.getByRole('button', { name: '前往验证运行' }))
    expect(onNavigate).toHaveBeenCalledWith('/validation')
    expect(screen.queryByRole('button', { name: '继续准备' })).not.toBeInTheDocument()
  })

  it('单一候选仍导航到人工确认页，不在加载或继续准备时确认', () => {
    const onPrepareSafe = vi.fn()
    const onNavigate = vi.fn()
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('USER', {
          kind: 'RECOVERY',
          label: '测试后恢复',
          description: '已找到一个可靠候选，请确认恢复方式。',
          next_path: '/flows',
          next_label: '确认恢复方式',
        }),
      ]))}
      onPrepareSafe={onPrepareSafe}
      onNavigate={onNavigate}
    />)

    expect(onPrepareSafe).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '确认恢复方式' }))
    expect(onNavigate).toHaveBeenCalledWith('/flows')
    expect(onPrepareSafe).not.toHaveBeenCalled()
  })

  it('只信任 ProjectPreparation 顶层导航，不使用 item 内部的旧路径', () => {
    const onNavigate = vi.fn()
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('USER', { next_path: '/flows', next_label: '旧入口' }),
      ], { next_path: '/identities', next_label: '准备测试账号' }))}
      onPrepareSafe={vi.fn()}
      onNavigate={onNavigate}
    />)

    fireEvent.click(screen.getByRole('button', { name: '准备测试账号' }))
    expect(onNavigate).toHaveBeenCalledWith('/identities')
  })

  it('账号登录失效时只把身份项标为需要处理，静态资产继续可复用', () => {
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('USER', { key: 'identity:bob', label: 'Bob 测试账号', description: 'Bob 需要登录或重新登录。' }),
        preparationItem('READY', { key: 'flow:export', kind: 'FLOW', label: '导出业务流程', description: '当前静态测试资产仍与正式事实一致。' }),
        preparationItem('READY', { key: 'resource:export', kind: 'RESOURCE', label: '导出测试资源', description: '当前静态测试资产仍与正式事实一致。' }),
        preparationItem('READY', { key: 'observation:export', kind: 'OBSERVATION', label: '导出结果观察', description: '当前静态测试资产仍与正式事实一致。' }),
        preparationItem('READY', { key: 'recovery:export', kind: 'RECOVERY', label: '导出现场恢复', description: '当前静态测试资产仍与正式事实一致。' }),
        preparationItem('READY', { key: 'effect:export', kind: 'EFFECT', label: '导出受保护后果', description: '当前静态测试资产仍与正式事实一致。' }),
      ]))}
      onPrepareSafe={vi.fn()}
      onNavigate={vi.fn()}
    />)

    expect(screen.getAllByText('需要你处理')).toHaveLength(1)
    expect(screen.getAllByText('当前可用')).toHaveLength(5)
    expect(screen.getByText('Bob 需要登录或重新登录。')).toBeInTheDocument()
  })

  it('观察绑定失效时只展示这一项需要重新确认', () => {
    render(<PreparationPage
      readiness={readiness(preparation([
        preparationItem('READY', { key: 'flow:export', kind: 'FLOW', label: '导出业务流程' }),
        preparationItem('READY', { key: 'resource:export', kind: 'RESOURCE', label: '导出测试资源' }),
        preparationItem('USER', { key: 'observation:export', kind: 'OBSERVATION', label: '导出结果观察', description: '已有有限候选，需要用户重新确认。', next_path: '/flows', next_label: '管理业务流程', reason_codes: ['OBSERVATION_STALE'] }),
        preparationItem('READY', { key: 'recovery:export', kind: 'RECOVERY', label: '导出现场恢复' }),
        preparationItem('READY', { key: 'effect:export', kind: 'EFFECT', label: '导出受保护后果' }),
      ]))}
      onPrepareSafe={vi.fn()}
      onNavigate={vi.fn()}
    />)

    expect(screen.getAllByText('需要你处理')).toHaveLength(1)
    expect(screen.getAllByText('当前可用')).toHaveLength(4)
    expect(screen.getByText('已有有限候选，需要用户重新确认。')).toBeInTheDocument()
  })

  it('prepare-safe 后接受重新读取的权威 readiness，而不保留本地完成态', async () => {
    const onPrepareSafe = vi.fn().mockResolvedValue(undefined)
    const { rerender } = render(<PreparationPage
      readiness={readiness(preparation([preparationItem('AUTO')]))}
      onPrepareSafe={onPrepareSafe}
      onNavigate={vi.fn()}
    />)

    fireEvent.click(screen.getByRole('button', { name: '继续准备' }))
    await waitFor(() => expect(onPrepareSafe).toHaveBeenCalledOnce())
    rerender(<PreparationPage
      readiness={readiness(preparation([preparationItem('READY')]))}
      onPrepareSafe={onPrepareSafe}
      onNavigate={vi.fn()}
    />)
    expect(screen.getByRole('button', { name: '前往验证运行' })).toBeInTheDocument()
  })
})
