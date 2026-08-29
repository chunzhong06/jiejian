// 验证普通 AI 辅助设置、MCP 配对装配、秘密清理与高级字段折叠边界。

import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LLMSettingsDrawer from './LLMSettingsDrawer'

const mockApi = vi.hoisted(() => ({
  discoverModels: vi.fn(), refreshModels: vi.fn(), saveDefault: vi.fn(), create: vi.fn(), settings: vi.fn(), patchSettings: vi.fn(), update: vi.fn(), profile: vi.fn(), test: vi.fn(),
}))
const mockMcpApi = vi.hoisted(() => ({
  status: vi.fn().mockResolvedValue({ schema_version: '1', paired: false, accepting_connections: false, endpoint: 'http://127.0.0.1:8765/mcp', default_level: 'READ', project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null }),
  pair: vi.fn(), reveal: vi.fn(), rotate: vi.fn(), pause: vi.fn(), forget: vi.fn(), setProjectAccess: vi.fn(),
}))

vi.mock('../../api/llm', async () => {
  const actual = await vi.importActual<typeof import('../../api/llm')>('../../api/llm')
  return { ...actual, llmApi: mockApi }
})
vi.mock('../../api/mcp', async () => {
  const actual = await vi.importActual<typeof import('../../api/mcp')>('../../api/mcp')
  return { ...actual, mcpAccessApi: mockMcpApi }
})

const profile = {
  schema_version: '1' as const, profile_name: 'local', provider: 'openai' as const, model: 'gpt-test', reasoning_effort: null,
  base_url: null, timeout_ms: 30000, max_input_bytes: 131072, max_output_bytes: 65536,
  max_budget_microusd: 1000000, enabled: true, secret_ref: 'cred:jiejian/llm/local', allow_local_http: false,
  created_at_us: 1, updated_at_us: 1, secret_configured: true, connection_status: 'configured' as const,
  tested_at_us: null, duration_ms: null, error_code: null, error_message: null,
}
const catalog = {
  schema_version: '1' as const, provider: 'openai' as const, manual_model_allowed: false, truncated: false,
  models: [{ model: 'gpt-5.6', display_name: 'GPT 5.6', reasoning_options: ['high'], reasoning_default_label: '跟随模型默认', structured_output_mode: 'json_schema' }],
}

describe('LLMSettingsDrawer', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks() })

  it('ordinary settings hide advanced developer fields until expanded', () => {
    render(<LLMSettingsDrawer open profiles={[profile]} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)
    expect(screen.getByText('AI 只在系统确定事实之上提供辅助，不能决定权限要求或检查结论。')).toBeInTheDocument()
    expect(screen.queryByLabelText('profile_name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Base URL')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '获取当前账号可用模型' })).not.toHaveClass('ant-btn-primary')
    expect(document.querySelector('.llm-settings-fields-pair')).not.toBeInTheDocument()
    expect(document.querySelectorAll('.llm-settings-section .ant-btn-primary')).toHaveLength(1)
    expect(screen.getByText('AI 工具连接（MCP）')).toBeInTheDocument()
  })

  it('pairs a separate MCP connection and confirms one project grant', async () => {
    const enabled = {
      schema_version: '1' as const, paired: true, accepting_connections: true, endpoint: 'http://127.0.0.1:8765/mcp',
      default_level: 'READ' as const, project_grants: [], client_connected: false, client_name: null, client_version: null, last_seen_at_us: null,
      access_token: 'mcp-token',
    }
    mockMcpApi.pair.mockResolvedValue(enabled)
    mockMcpApi.setProjectAccess.mockResolvedValue({
      ...enabled, project_grants: [{ project_id: 'proj-1', level: 'PREPARE' }], access_token: undefined,
    })
    render(<LLMSettingsDrawer open profiles={[]} projects={[{ project_id: 'proj-1', name: '示例应用' }]} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)

    fireEvent.click(await screen.findByRole('button', { name: '首次配对 AI 工具' }))
    await waitFor(() => expect(screen.getByLabelText('MCP 连接凭据')).toHaveValue('mcp-token'))
    expect(screen.getByLabelText('API Key（只写入，不回显）')).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: '调整权限' }))
    expect(screen.getByText('本次确认不会永久保存，也不会逐工具重复弹窗。', { exact: false })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '确认临时权限' }))
    await waitFor(() => expect(mockMcpApi.setProjectAccess).toHaveBeenCalledWith('proj-1', 'PREPARE'))
    expect(mockMcpApi.status).toHaveBeenCalled()
  })

  it('discovers dynamic models, saves once, and clears the temporary API Key', async () => {
    mockApi.discoverModels.mockResolvedValue(catalog)
    mockApi.saveDefault.mockResolvedValue({ ...profile, profile_name: 'assistant-default', model: 'gpt-5.6', connection_status: 'available' })
    mockApi.settings.mockResolvedValue({ enabled: true, default_profile_name: 'assistant-default', updated_at_us: 2 })
    const onChanged = vi.fn()
    render(<LLMSettingsDrawer open profiles={[]} onClose={vi.fn()} onChanged={onChanged} onError={vi.fn()} />)
    const password = screen.getByLabelText('API Key（只写入，不回显）')
    fireEvent.change(password, { target: { value: 'temporary-key' } })
    fireEvent.click(screen.getByRole('button', { name: '获取当前账号可用模型' }))
    await waitFor(() => expect(mockApi.discoverModels).toHaveBeenCalledWith({ provider: 'openai', secret: 'temporary-key' }))
    expect(screen.getByText('GPT 5.6（gpt-5.6）')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '保存并测试' }))
    await waitFor(() => expect(mockApi.saveDefault).toHaveBeenCalledWith(expect.objectContaining({ provider: 'openai', model: 'gpt-5.6', reasoning_effort: null, secret: 'temporary-key' })))
    expect(password).toHaveValue('')
    expect(onChanged).toHaveBeenCalled()
    expect(screen.queryByText('temporary-key')).not.toBeInTheDocument()
    expect(localStorage.length).toBe(0)
  })

  it('edits the saved default profile in the ordinary section and refreshes without a new key', async () => {
    mockApi.refreshModels.mockResolvedValue(catalog)
    mockApi.saveDefault.mockResolvedValue(profile)
    mockApi.settings.mockResolvedValue({ enabled: false, default_profile_name: 'local', updated_at_us: 3 })
    render(<LLMSettingsDrawer open profiles={[profile]} aiSettings={{ enabled: false, default_profile_name: 'local', updated_at_us: 2 }} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)
    expect(screen.getByText('gpt-test')).toBeInTheDocument()
    expect(screen.getByText('已配置')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '获取当前账号可用模型' }))
    await waitFor(() => expect(mockApi.refreshModels).toHaveBeenCalledWith('local'))
    expect(mockApi.discoverModels).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '保存并测试' }))
    await waitFor(() => expect(mockApi.saveDefault).toHaveBeenCalled())
    expect(mockApi.update).not.toHaveBeenCalled()
  })

  it('clears API Key when discovery fails', async () => {
    mockApi.discoverModels.mockRejectedValueOnce(new Error('redacted failure'))
    const onError = vi.fn()
    render(<LLMSettingsDrawer open profiles={[]} onClose={vi.fn()} onChanged={vi.fn()} onError={onError} />)
    const password = screen.getByLabelText('API Key（只写入，不回显）')
    fireEvent.change(password, { target: { value: 'temporary-key' } })
    fireEvent.click(screen.getByRole('button', { name: '获取当前账号可用模型' }))
    await waitFor(() => expect(mockApi.discoverModels).toHaveBeenCalled())
    await waitFor(() => expect(password).toHaveValue(''))
    expect(onError).toHaveBeenCalled()
  })

  it('clears API Key after save failure and drawer close', async () => {
    mockApi.discoverModels.mockResolvedValue(catalog)
    mockApi.saveDefault.mockRejectedValueOnce(new Error('redacted failure'))
    const onError = vi.fn()
    const onClose = vi.fn()
    const view = render(<LLMSettingsDrawer open profiles={[]} onClose={onClose} onChanged={vi.fn()} onError={onError} />)
    const password = screen.getByLabelText('API Key（只写入，不回显）')
    fireEvent.change(password, { target: { value: 'temporary-key' } })
    fireEvent.click(screen.getByRole('button', { name: '获取当前账号可用模型' }))
    await waitFor(() => expect(mockApi.discoverModels).toHaveBeenCalled())
    fireEvent.click(screen.getByRole('button', { name: '保存并测试' }))
    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(password).toHaveValue('')
    fireEvent.change(password, { target: { value: 'temporary-key' } })
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalledOnce()
    view.unmount()
    expect(screen.queryByLabelText('API Key（只写入，不回显）')).not.toBeInTheDocument()
  })

  it('keeps explicit connection testing in the advanced section', async () => {
    mockApi.test.mockResolvedValue({ ...profile, connection_status: 'available' })
    render(<LLMSettingsDrawer open profiles={[profile]} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /高级设置/ }))
    fireEvent.click(screen.getByRole('button', { name: /编\s*辑/ }))
    expect(screen.getByLabelText('API Key（只写入，不回显）')).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }))
    await waitFor(() => expect(mockApi.test).toHaveBeenCalledWith('local'))
  })

  it('creates a compatible advanced profile with manual model fallback and keeps the ordinary default isolated', async () => {
    const compatibleCatalog = { ...catalog, provider: 'openai_compatible' as const, models: [], manual_model_allowed: true }
    const compatibleProfile = {
      ...profile,
      profile_name: 'advanced-profile', provider: 'openai_compatible' as const, model: 'manual-model',
      base_url: 'https://example.test/v1', secret_ref: 'env:MODEL_KEY',
    }
    mockApi.discoverModels.mockResolvedValue(compatibleCatalog)
    mockApi.create.mockResolvedValue(compatibleProfile)
    mockApi.settings.mockResolvedValue({ enabled: false, default_profile_name: null, updated_at_us: 0 })
    render(<LLMSettingsDrawer open profiles={[]} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)

    fireEvent.click(screen.getByRole('button', { name: /高级设置/ }))
    expect(screen.queryByText('普通设置')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('API Key（只写入，不回显）'), { target: { value: 'temporary-key' } })
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://example.test/v1' } })
    fireEvent.change(screen.getByLabelText('env: secret_ref'), { target: { value: 'env:MODEL_KEY' } })
    fireEvent.click(screen.getByRole('button', { name: '获取当前账号可用模型' }))
    await waitFor(() => expect(mockApi.discoverModels).toHaveBeenCalledWith({
      provider: 'openai_compatible', secret: 'temporary-key', base_url: 'https://example.test/v1', allow_local_http: false,
    }))
    fireEvent.change(screen.getByLabelText('model'), { target: { value: 'manual-model' } })
    fireEvent.click(screen.getByRole('button', { name: '创建高级 profile' }))
    await waitFor(() => expect(mockApi.create).toHaveBeenCalledWith(expect.objectContaining({
      profile_name: 'advanced-profile', provider: 'openai_compatible', model: 'manual-model',
      base_url: 'https://example.test/v1', secret_ref: 'env:MODEL_KEY',
    })))
    expect(mockApi.create.mock.calls[0][0]).not.toHaveProperty('secret')
    expect(mockApi.saveDefault).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '保存高级配置' })).toBeInTheDocument()
    expect(screen.getByLabelText('API Key（只写入，不回显）')).toHaveValue('')
  })

  it('restores the ordinary default when advanced mode is folded', () => {
    render(<LLMSettingsDrawer open profiles={[profile]} aiSettings={{ enabled: false, default_profile_name: 'local', updated_at_us: 2 }} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /高级设置/ }))
    fireEvent.click(screen.getByRole('button', { name: '新增高级 profile' }))
    expect(screen.queryByText('普通设置')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /高级设置/ }))
    expect(screen.getByText('普通设置')).toBeInTheDocument()
    expect(screen.getByText('gpt-test')).toBeInTheDocument()
    expect(screen.getByText('已配置')).toBeInTheDocument()
  })
})
