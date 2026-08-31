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

  it('展示真实变化并分别进入权限确认和验证运行', async () => {
    const onNavigate = vi.fn()
    render(<ChangesPage
      project={{ project_id: 'p1', name: '持续开发应用' }}
      status={{ latest_result: null } as any}
      onError={vi.fn()}
      onNavigate={onNavigate}
    />)

    expect(await screen.findByText('Agent 增加了批量导出入口')).toBeInTheDocument()
    expect(api.list).toHaveBeenCalledWith('p1')
    expect(screen.getByText('app/export_job.py')).toBeInTheDocument()
    expect(screen.getByText('app/permissions.py')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新确认权限规则' }))
    fireEvent.click(screen.getByRole('button', { name: '检查这次变化' }))
    expect(onNavigate).toHaveBeenNthCalledWith(1, '/permissions')
    expect(onNavigate).toHaveBeenNthCalledWith(2, '/validation')
  })

  it('没有变化时说明正在等待后续 Agent 修改', async () => {
    api.list.mockResolvedValue([])
    render(<ChangesPage project={{ project_id: 'p1' }} status={null} onError={vi.fn()} onNavigate={vi.fn()} />)

    await waitFor(() => expect(screen.getByText('当前还没有 Agent 代码变化记录')).toBeInTheDocument())
    expect(screen.getByText('等待 Agent 代码变化')).toBeInTheDocument()
  })
})
