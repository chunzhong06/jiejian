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
    pause: vi.fn(),
    forget: vi.fn(),
    setProjectAccess: vi.fn(),
  },
}))

describe('ToolsPage', () => {
  afterEach(() => cleanup())

  it('展示 Codex、DSH、其他客户端和固定 Oracle 提示', async () => {
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
    })

    render(<ToolsPage projects={[{ project_id: 'project-demo', name: '演示应用', status: 'READY' }]} onError={vi.fn()} />)

    expect(await screen.findByRole('heading', { name: 'AI 工具' })).toBeInTheDocument()
    expect(screen.getByText('Codex', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText('DSH', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText('其他 MCP 客户端', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText(/不能批准权限变化、退休人的权限要求或改变安全结论/)).toBeInTheDocument()
    expect(document.querySelector('.process-navigation')).not.toBeInTheDocument()
  })
})
