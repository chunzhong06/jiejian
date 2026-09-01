// 验证五类 MCP 客户端共享新手向导和真实状态机，秘密不在页面正文出现。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MCPAccessCard from './MCPAccessCard'

const mockApi = vi.hoisted(() => ({
  status: vi.fn(), pair: vi.fn(), reveal: vi.fn(), rotate: vi.fn(), resume: vi.fn(), pause: vi.fn(), forget: vi.fn(), setProjectAccess: vi.fn(),
}))

vi.mock('../../api/mcp', () => ({ mcpAccessApi: mockApi }))

const endpoint = 'http://127.0.0.1:8765/mcp'
const unpaired = {
  schema_version: '1' as const, paired: false, accepting_connections: false, endpoint,
  default_level: 'READ' as const, project_grants: [], client_connected: false,
  client_name: null, client_version: null, last_seen_at_us: null,
  connection_state: 'DISABLED' as const, last_authenticated_at_us: null, last_auth_failure_at_us: null,
}
const waiting = { ...unpaired, paired: true, accepting_connections: true, connection_state: 'CREDENTIAL_READY' as const }
const rejected = { ...waiting, connection_state: 'CREDENTIAL_REJECTED' as const, last_auth_failure_at_us: 10 }
const connected = {
  ...waiting,
  client_connected: true,
  client_name: 'Codex',
  client_version: '1.2.3',
  last_seen_at_us: 1_735_689_600_000_000,
  connection_state: 'CONNECTED' as const,
  last_authenticated_at_us: 1_735_689_599_000_000,
}
const credential = { ...waiting, access_token: 'mcp-secret-token' }

function renderCard(projects: { project_id: string; name?: string }[] = []) {
  return render(<MCPAccessCard open projects={projects} onError={vi.fn()} />)
}

describe('MCPAccessCard', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    })
    mockApi.status.mockReset().mockResolvedValue(unpaired)
    mockApi.pair.mockReset()
    mockApi.reveal.mockReset()
    mockApi.rotate.mockReset()
    mockApi.resume.mockReset()
    mockApi.pause.mockReset()
    mockApi.forget.mockReset()
    mockApi.setProjectAccess.mockReset()
  })

  afterEach(() => cleanup())

  it('按五个明确步骤引导首次连接，创建凭据后仍不冒充连接成功', async () => {
    mockApi.pair.mockResolvedValue(credential)
    renderCard()

    expect(await screen.findByRole('heading', { name: '跟着 5 步完成连接' })).toBeInTheDocument()
    expect(screen.getByText(/按 Win \+ R，输入 %USERPROFILE%/)).toBeInTheDocument()
    expect(screen.getByText(/打开“开始”菜单，搜索 Windows PowerShell/)).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '准备本机连接' }))
    expect(await screen.findByText('下一步：在 AI 工具中添加 jiejian')).toBeInTheDocument()
    expect(screen.getAllByText('界鉴已准备好')).toHaveLength(2)
    expect(screen.queryByText('连接成功')).not.toBeInTheDocument()
    expect(screen.queryByText('mcp-secret-token')).not.toBeInTheDocument()
  })

  it('用一个紧凑选择器提供 Codex、TRAE、Qoder、CodeBuddy 和 DSH', async () => {
    renderCard()

    await screen.findByText('跟着 5 步完成连接')
    for (const label of ['Codex', 'TRAE', 'Qoder', 'CodeBuddy', 'DSH']) {
      expect(screen.getByText(label, { selector: '.ant-segmented-item-label' })).toBeInTheDocument()
    }
    expect(document.querySelectorAll('.mcp-beginner-guide')).toHaveLength(1)
  })

  it('对需要本机凭据的客户端分开复制第 3 步配置和第 4 步凭据', async () => {
    mockApi.status.mockResolvedValue(waiting)
    mockApi.reveal.mockResolvedValue(credential)
    renderCard()

    fireEvent.click(await screen.findByText('TRAE', { selector: '.ant-segmented-item-label' }))
    expect(screen.getByText(/进入“设置 → MCP → 手动添加”/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '复制第 3 步内容' }))
    fireEvent.click(screen.getByRole('button', { name: '复制第 4 步内容' }))

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith('Bearer mcp-secret-token'))
    expect(screen.queryByText('mcp-secret-token')).not.toBeInTheDocument()
  })

  it('检查连接时能区分客户端未请求与凭据被拒绝', async () => {
    mockApi.status.mockResolvedValue(waiting)
    renderCard()
    await screen.findByText('下一步：在 AI 工具中添加 jiejian')
    mockApi.status.mockResolvedValue(rejected)

    fireEvent.click(screen.getByRole('button', { name: '检查连接' }))
    expect(await screen.findByText('客户端已访问界鉴，但使用的连接凭据无效。请更新凭据后重新连接。')).toBeInTheDocument()
    expect(screen.getByText('客户端已经找到界鉴，但使用了失效凭据')).toBeInTheDocument()
  })

  it('只有 SDK 成功处理请求后才显示客户端事实和逐应用权限', async () => {
    mockApi.status.mockResolvedValue(connected)
    mockApi.setProjectAccess.mockResolvedValue({
      ...connected,
      project_grants: [{ project_id: 'proj-1', level: 'PREPARE' as const }],
    })
    renderCard([{ project_id: 'proj-1', name: '示例应用' }])

    expect(await screen.findByRole('heading', { name: 'Codex 已连接到界鉴' })).toBeInTheDocument()
    expect(screen.getByText('Codex · 1.2.3')).toBeInTheDocument()
    expect(screen.getByText('AI 工具这次可以做什么')).toBeInTheDocument()
    expect(screen.getByText('一次登记整批变化')).toBeInTheDocument()
    expect(screen.getByText(/不会在每次保存或修改单个文件后打断你/)).toBeInTheDocument()
    expect(screen.queryByText('跟着 5 步完成连接')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '复制协作任务' }))
    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringMatching(/一个完整的用户任务已经完成/)))
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(expect.stringMatching(/jiejian_change_submit/))

    fireEvent.click(screen.getByRole('button', { name: '调整这次允许范围' }))
    expect(screen.getByRole('dialog', { name: '这次允许 AI 工具做到哪一步？' })).toBeInTheDocument()
    expect(screen.getByText(/完成一个用户任务后登记整批代码变化/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '保存这次允许范围' }))
    await waitFor(() => expect(mockApi.setProjectAccess).toHaveBeenCalledWith('proj-1', 'PREPARE'))
  })

  it('暂停后可在同一连接管理页恢复，不要求重新创建凭据', async () => {
    mockApi.status.mockResolvedValue(waiting)
    mockApi.pause.mockResolvedValue({ ...waiting, accepting_connections: false, connection_state: 'PAUSED' as const })
    mockApi.resume.mockResolvedValue(waiting)
    renderCard()

    fireEvent.click(await screen.findByRole('button', { name: '管理连接' }))
    fireEvent.click(screen.getByRole('button', { name: '暂停本次连接' }))
    expect(await screen.findByText('界鉴暂时不接受 AI 工具连接')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '恢复接受连接' }))

    await waitFor(() => expect(mockApi.resume).toHaveBeenCalledOnce())
    expect(await screen.findByText('下一步：在 AI 工具中添加 jiejian')).toBeInTheDocument()
    expect(mockApi.pair).not.toHaveBeenCalled()
  })
})
