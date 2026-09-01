// 验证 AI 工具一级页面独立承载连接向导、状态与 Oracle 边界。

import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToolsPage } from './ToolsPage'

const status = vi.hoisted(() => vi.fn())
vi.mock('../../api/mcp', () => ({
  mcpAccessApi: {
    status,
    pair: vi.fn(),
    reveal: vi.fn(),
    rotate: vi.fn(),
    resume: vi.fn(),
    pause: vi.fn(),
    forget: vi.fn(),
    setProjectAccess: vi.fn(),
  },
}))

describe('ToolsPage', () => {
  afterEach(() => cleanup())

  it('展示五类正式客户端和固定 Oracle 提示', async () => {
    status.mockResolvedValue({
      schema_version: '1',
      paired: true,
      accepting_connections: true,
      endpoint: 'http://127.0.0.1:8765/mcp',
      default_level: 'READ',
      project_grants: [],
      client_connected: false,
      client_name: null,
      client_version: null,
      last_seen_at_us: null,
      connection_state: 'CREDENTIAL_READY',
      last_authenticated_at_us: null,
      last_auth_failure_at_us: null,
    })

    render(<ToolsPage projects={[{ project_id: 'project-demo', name: '演示应用', status: 'READY' }]} onError={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'AI 工具连接' })).toBeInTheDocument()
    for (const label of ['Codex', 'TRAE', 'Qoder', 'CodeBuddy', 'DSH']) {
      expect(screen.getByText(label, { selector: '.ant-segmented-item-label' })).toBeInTheDocument()
    }
    expect(screen.getByText(/不能确认或更改权限规则，也不能改变界鉴的检查结论/)).toBeInTheDocument()
    expect(document.querySelector('.module-navigation')).not.toBeInTheDocument()
  })
})
