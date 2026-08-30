// 验证 MCP 配对、凭据展示、连接向导、活动状态与逐应用临时授权边界。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MCPAccessCard from './MCPAccessCard'

const mockApi = vi.hoisted(() => ({
  status: vi.fn(), pair: vi.fn(), reveal: vi.fn(), rotate: vi.fn(), pause: vi.fn(), forget: vi.fn(), setProjectAccess: vi.fn(),
}))

vi.mock('../../api/mcp', () => ({ mcpAccessApi: mockApi }))

const endpoint = 'http://127.0.0.1:8765/mcp'
const unpaired = {
  schema_version: '1' as const, paired: false, accepting_connections: false, endpoint,
  default_level: 'READ' as const, project_grants: [], client_connected: false,
  client_name: null, client_version: null, last_seen_at_us: null,
}
const waiting = { ...unpaired, paired: true, accepting_connections: true }
const credential = { ...waiting, access_token: 'mcp-secret-token' }

function renderCard(projects: { project_id: string; name?: string }[] = []) {
  return render(<MCPAccessCard open projects={projects} onError={vi.fn()} />)
}

describe('MCPAccessCard', () => {
  beforeEach(() => {
    mockApi.status.mockResolvedValue(unpaired)
    mockApi.pair.mockReset()
    mockApi.reveal.mockReset()
    mockApi.rotate.mockReset()
    mockApi.pause.mockReset()
    mockApi.forget.mockReset()
    mockApi.setProjectAccess.mockReset()
  })

  afterEach(() => cleanup())

  it('pairs once and keeps the returned credential masked', async () => {
    mockApi.pair.mockResolvedValue(credential)
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: '首次配对 AI 工具' }))
    fireEvent.click(await screen.findByRole('button', { name: '管理连接' }))
    const token = await screen.findByLabelText('MCP 连接凭据')
    expect(token).toHaveValue('mcp-secret-token')
    expect(token).toHaveAttribute('type', 'password')
    expect(mockApi.pair).toHaveBeenCalledOnce()
  })

  it('does not put a token in the DOM after ordinary status', async () => {
    mockApi.status.mockResolvedValue(waiting)
    renderCard()

    await screen.findByText('已配对，正在等待客户端完成 initialize。默认权限为只读。')
    expect(screen.queryByLabelText('MCP 连接凭据')).not.toBeInTheDocument()
    expect(screen.queryByText('mcp-secret-token')).not.toBeInTheDocument()
  })

  it('keeps all client guides available before the first pairing', async () => {
    renderCard()

    expect(await screen.findByText('Codex', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText('DSH', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByText('其他 MCP 客户端', { selector: '.ant-card-head-title' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '查看 Codex 三步连接' })).toBeInTheDocument()
  })

  it('reveals only after the explicit action while keeping the input masked', async () => {
    mockApi.status.mockResolvedValue(waiting)
    mockApi.reveal.mockResolvedValue(credential)
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: '管理连接' }))
    fireEvent.click(screen.getByRole('button', { name: '显示连接凭据' }))
    const token = await screen.findByLabelText('MCP 连接凭据')
    expect(mockApi.reveal).toHaveBeenCalledOnce()
    expect(token).toHaveValue('mcp-secret-token')
    expect(token).toHaveAttribute('type', 'password')
  })

  it('shows the three connection guides without embedding a real token', async () => {
    mockApi.status.mockResolvedValue(waiting)
    renderCard()

    await screen.findByText('Codex', { selector: '.ant-card-head-title' })
    fireEvent.click(screen.getByRole('button', { name: '查看 Codex 三步连接' }))
    expect(screen.getByText('1. 准备长期凭据')).toBeInTheDocument()
    expect(screen.getByText('2. 一次性配置客户端')).toBeInTheDocument()
    expect(screen.getByText('3. 等待 initialize 成功')).toBeInTheDocument()
    expect(screen.getByText(/codex mcp add jiejian/)).toBeInTheDocument()
    expect(screen.getByText(/SetEnvironmentVariable/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.click(screen.getByRole('button', { name: '查看 DSH 三步连接' }))
    expect(screen.getAllByText(/@deepseek-ai\/dsh-mcp-client/).length).toBeGreaterThan(0)
    expect(screen.getByText(/!!js/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    fireEvent.click(screen.getByRole('button', { name: '查看其他 MCP 客户端连接说明' }))
    expect(screen.getByText(/Streamable HTTP endpoint/)).toBeInTheDocument()
    expect(screen.getByText(/PREPARE\/EXECUTE 必须回界鉴当前会话授权/)).toBeInTheDocument()
    expect(screen.getByText(/以后启动界鉴会自动恢复只读连接/)).toBeInTheDocument()
    expect(screen.getByText(/轮换后只需更新客户端读取的 JIEJIAN_MCP_TOKEN/)).toBeInTheDocument()
    expect(screen.getByText(/忘记此连接.*彻底删除长期配对/)).toBeInTheDocument()
  })

  it('shows connected client activity and the safe fallback identity', async () => {
    mockApi.status.mockResolvedValue({ ...waiting, client_connected: true, client_name: 'Codex', client_version: '1.2.3', last_seen_at_us: 1_735_689_600_000_000 })
    renderCard()
    expect(await screen.findByText('已连接')).toBeInTheDocument()
    expect(screen.getByText('客户端：Codex · 版本：1.2.3')).toBeInTheDocument()
    expect(screen.getByText(/最近活动：/)).toBeInTheDocument()

    cleanup()
    mockApi.status.mockResolvedValue({ ...waiting, client_connected: true, client_name: null, client_version: null, last_seen_at_us: 1_735_689_600_000_000 })
    renderCard()
    expect(await screen.findByText('已认证客户端已连接')).toBeInTheDocument()
    expect(screen.queryByText(/客户端名称未提供/)).not.toBeInTheDocument()
  })

  it('pauses and clears the temporary credential, then confirms rotate and forget', async () => {
    mockApi.status.mockResolvedValue(waiting)
    mockApi.reveal.mockResolvedValue(credential)
    mockApi.pause.mockResolvedValue({ ...waiting, accepting_connections: false })
    mockApi.rotate.mockResolvedValue({ ...waiting, access_token: 'rotated-token' })
    mockApi.forget.mockResolvedValue(unpaired)
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: '管理连接' }))
    fireEvent.click(screen.getByRole('button', { name: '显示连接凭据' }))
    await screen.findByLabelText('MCP 连接凭据')
    fireEvent.click(screen.getByRole('button', { name: '暂停本次连接' }))
    await waitFor(() => expect(mockApi.pause).toHaveBeenCalledOnce())
    expect(screen.queryByLabelText('MCP 连接凭据')).not.toBeInTheDocument()
    expect(await screen.findByText('本次连接已暂停；长期配对仍保留，下次启动界鉴会自动恢复只读连接。当前 serve 不提供恢复按钮。')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '恢复连接' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '重新生成连接凭据' }))
    fireEvent.click(await screen.findByRole('button', { name: /确\s*认/ }))
    await waitFor(() => expect(mockApi.rotate).toHaveBeenCalledOnce())
    expect(await screen.findByLabelText('MCP 连接凭据')).toHaveValue('rotated-token')

    fireEvent.click(screen.getByRole('button', { name: '忘记此连接' }))
    fireEvent.click(await screen.findByRole('button', { name: /确\s*认/ }))
    await waitFor(() => expect(mockApi.forget).toHaveBeenCalledOnce())
    expect(await screen.findByText('尚未配对。首次配对会把长期连接凭据安全保存到 Windows Credential Manager；默认只读。')).toBeInTheDocument()
  })

  it('changes a project grant only while the serve accepts connections', async () => {
    mockApi.status.mockResolvedValue(waiting)
    mockApi.setProjectAccess.mockResolvedValue({ ...waiting, project_grants: [{ project_id: 'proj-1', level: 'PREPARE' as const }] })
    renderCard([{ project_id: 'proj-1', name: '示例应用' }])

    fireEvent.click(await screen.findByRole('button', { name: '调整权限' }))
    expect(screen.getByText(/本次确认不会永久保存/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认临时权限' }))
    await waitFor(() => expect(mockApi.setProjectAccess).toHaveBeenCalledWith('proj-1', 'PREPARE'))
  })

  it('does not write a stale status response after the drawer closes', async () => {
    let resolveStatus!: (value: typeof waiting) => void
    mockApi.status.mockReturnValue(new Promise((resolve) => { resolveStatus = resolve }))
    const view = render(<MCPAccessCard open projects={[]} onError={vi.fn()} />)
    view.rerender(<MCPAccessCard open={false} projects={[]} onError={vi.fn()} />)
    resolveStatus(waiting)
    await Promise.resolve()
    expect(screen.queryByText('已配对，正在等待客户端完成 initialize。默认权限为只读。')).not.toBeInTheDocument()
  })

  it('does not write a stale credential response into a reopened drawer', async () => {
    mockApi.status.mockResolvedValue(waiting)
    let resolveReveal!: (value: typeof credential) => void
    mockApi.reveal.mockReturnValue(new Promise((resolve) => { resolveReveal = resolve }))
    const onError = vi.fn()
    const view = render(<MCPAccessCard open projects={[]} onError={onError} />)

    fireEvent.click(await screen.findByRole('button', { name: '管理连接' }))
    fireEvent.click(screen.getByRole('button', { name: '显示连接凭据' }))
    view.rerender(<MCPAccessCard open={false} projects={[]} onError={onError} />)
    view.rerender(<MCPAccessCard open projects={[]} onError={onError} />)
    await screen.findByText('已配对，正在等待客户端完成 initialize。默认权限为只读。')
    resolveReveal(credential)
    await Promise.resolve()

    expect(screen.queryByLabelText('MCP 连接凭据')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('MCP 连接凭据')).not.toBeInTheDocument()
  })
})
