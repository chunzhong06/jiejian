// 验证变化页只展示真实源码差异，并把待确认规则与重验动作送回持续工作区。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChangesPage } from './ChangesPage'

const api = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('../../api/sourceChanges', () => ({ sourceChangesApi: { list: api.list } }))

const change = {
  change_id: `chg_${'1'.repeat(32)}`,
  project_id: 'p1',
  reason: 'Agent 增加了批量导出入口',
  submitted_by: 'MCP · Codex',
  created_at_us: 1,
  status: 'COMPARABLE' as const,
  complete: true,
  actual_changed_path_count: 2,
  added_count: 1,
  modified_count: 1,
  removed_count: 0,
  claimed_paths: [],
  added_paths: ['app/export_job.py'],
  modified_paths: ['app/permissions.py'],
  removed_paths: [],
  directly_affected_count: 1,
  mapping_review_required_count: 1,
  no_direct_evidence_count: 0,
  review_intent_ids: [`pin_${'2'.repeat(32)}`],
  summary: '发现 1 条权限规则需要重新确认。',
  next_path: '/permissions' as const,
}

describe('ChangesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.list.mockResolvedValue([change])
  })

  it('展示真实变化并只按服务端指定的当前 change_id 绑定主操作', async () => {
    const onNavigate = vi.fn()
    const olderChange = { ...change, change_id: `chg_${'3'.repeat(32)}`, reason: '较早的变化' }
    api.list.mockResolvedValue([olderChange, change])
    const { rerender } = render(<ChangesPage
      project={{ project_id: 'p1', name: '持续开发应用' }}
      status={{ revalidation: { status: 'REVIEW_REQUIRED', change_id: change.change_id, summary: '当前实现映射待确认', next_path: '/permissions', next_label: '确认权限实现' } } as any}
      onError={vi.fn()}
      onNavigate={onNavigate}
    />)

    expect(await screen.findByText('Agent 增加了批量导出入口')).toBeInTheDocument()
    expect(screen.getAllByText(/MCP · Codex/).length).toBeGreaterThan(0)
    expect(api.list).toHaveBeenCalledWith('p1')
    expect(screen.getAllByText('app/export_job.py').length).toBeGreaterThan(0)
    expect(screen.getAllByText('app/permissions.py').length).toBeGreaterThan(0)
    expect(screen.getAllByText('需要重新确认实现映射').length).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: '确认权限实现' }))
    expect(onNavigate).toHaveBeenNthCalledWith(1, '/permissions')

    rerender(<ChangesPage
      project={{ project_id: 'p1', name: '持续开发应用' }}
      status={{ revalidation: { status: 'READY', change_id: change.change_id, summary: '可以重验', next_path: '/validation', next_label: '开始重新验证' } } as any}
      onError={vi.fn()}
      onNavigate={onNavigate}
    />)
    fireEvent.click(screen.getByRole('button', { name: '开始重新验证' }))
    expect(onNavigate).toHaveBeenNthCalledWith(2, '/validation')
  })

  it.each([
    ['PREPARATION_REQUIRED', '/preparation', '补齐测试准备', '需要补齐测试准备'],
    ['VERIFIED', '/results', '查看验证结果', '已纳入当前安全基线'],
    ['STALE', '/changes', '重新说明代码变化', '当前变化已失效'],
  ] as const)('%s 完全使用统一状态提供的路径和说明', async (status, path, action, label) => {
    const onNavigate = vi.fn()
    render(<ChangesPage
      project={{ project_id: 'p1', name: '持续开发应用' }}
      status={{ revalidation: { status, change_id: change.change_id, summary: `${label}说明`, next_path: path, next_label: action } } as any}
      onError={vi.fn()}
      onNavigate={onNavigate}
    />)

    expect((await screen.findAllByText(label)).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: action }))
    expect(onNavigate).toHaveBeenCalledWith(path)
  })

  it('NO_CHANGE 不把历史数量重新解释为当前操作', async () => {
    render(<ChangesPage
      project={{ project_id: 'p1', name: '持续开发应用' }}
      status={{ revalidation: { status: 'NO_CHANGE', change_id: null, summary: '无待处理变化', next_path: null, next_label: null } } as any}
      onError={vi.fn()}
      onNavigate={vi.fn()}
    />)
    expect(await screen.findByText('Agent 增加了批量导出入口')).toBeInTheDocument()
    expect(screen.getAllByText('无待处理变化').length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /确认权限实现|补齐测试准备|开始重新验证|查看验证结果|重新说明代码变化/ })).not.toBeInTheDocument()
  })

  it('没有变化时说明正在等待后续 Agent 修改', async () => {
    api.list.mockResolvedValue([])
    render(<ChangesPage project={{ project_id: 'p1' }} status={null} onError={vi.fn()} onNavigate={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('当前没有需要重新核对的代码变化。')).toBeInTheDocument())
    expect(screen.getByText('等待 Agent 提交下一次代码变化。')).toBeInTheDocument()
  })
})
