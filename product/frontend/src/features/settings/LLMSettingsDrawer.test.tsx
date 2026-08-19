import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import LLMSettingsDrawer from './LLMSettingsDrawer'

const mockApi = vi.hoisted(() => ({
  create: vi.fn(),
  update: vi.fn(),
  profile: vi.fn(),
  test: vi.fn(),
}))

vi.mock('../../api/llm', async () => {
  const actual = await vi.importActual<typeof import('../../api/llm')>('../../api/llm')
  return { ...actual, llmApi: mockApi }
})

const profile = {
  schema_version: '1' as const,
  profile_name: 'local', provider: 'openai' as const, model: 'gpt-test', base_url: null,
  timeout_ms: 30000, max_input_bytes: 131072, max_output_bytes: 65536,
  max_budget_microusd: 1000000, enabled: true, secret_ref: 'cred:jiejian/llm/local',
  allow_local_http: false, created_at_us: 1, updated_at_us: 1, secret_configured: true,
  connection_status: 'configured' as const, tested_at_us: null, duration_ms: null,
  error_code: null, error_message: null,
}

describe('LLMSettingsDrawer', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('does not echo API Key and explicitly tests once', async () => {
    mockApi.test.mockResolvedValue({ ...profile, connection_status: 'available' })
    const onChanged = vi.fn()
    render(<LLMSettingsDrawer open profiles={[profile]} onClose={vi.fn()} onChanged={onChanged} onError={vi.fn()} />)
    fireEvent.click(screen.getAllByRole('button', { name: /编\s*辑/ })[0])
    const password = screen.getByLabelText('API Key（只写入，不回显）')
    expect(password).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }))
    await waitFor(() => expect(mockApi.test).toHaveBeenCalledWith('local'))
    expect(onChanged).toHaveBeenCalledWith([expect.objectContaining({ connection_status: 'available' })])
    expect(localStorage.length).toBe(0)
  })

  it('refreshes the backend failure state and never leaves testing', async () => {
    const onChanged = vi.fn()
    const onError = vi.fn()
    mockApi.test.mockRejectedValueOnce(new Error('redacted failure'))
    mockApi.profile.mockResolvedValueOnce({ ...profile, connection_status: 'unavailable', error_code: 'llm_timeout', error_message: '连接超时' })
    render(<LLMSettingsDrawer open profiles={[profile]} onClose={vi.fn()} onChanged={onChanged} onError={onError} />)
    fireEvent.click(screen.getAllByRole('button', { name: /编\s*辑/ })[0])
    expect(screen.getByLabelText('API Key（只写入，不回显）')).toHaveValue('')
    fireEvent.click(screen.getByRole('button', { name: '测试连接' }))
    await waitFor(() => expect(mockApi.profile).toHaveBeenCalledWith('local'))
    expect(onChanged).toHaveBeenCalledWith([expect.objectContaining({ connection_status: 'unavailable', error_code: 'llm_timeout' })])
    expect(onError).toHaveBeenCalled()
    expect(localStorage.length).toBe(0)
  })

  it('rejects localhost HTTP before saving', async () => {
    mockApi.create.mockClear()
    render(<LLMSettingsDrawer open profiles={[]} onClose={vi.fn()} onChanged={vi.fn()} onError={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('配置名称'), { target: { value: 'local' } })
    fireEvent.change(screen.getByLabelText('模型'), { target: { value: 'gpt-test' } })
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'http://localhost:8080/v1' } })
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(screen.getByText('HTTP 仅允许显式授权的本机回环地址')).toBeInTheDocument())
    expect(mockApi.create).not.toHaveBeenCalled()
  })

  it('clears the write-only password after a save failure', async () => {
    const onError = vi.fn()
    mockApi.create.mockRejectedValueOnce(new Error('save failed'))
    render(<LLMSettingsDrawer open profiles={[]} onClose={vi.fn()} onChanged={vi.fn()} onError={onError} />)
    fireEvent.change(screen.getByLabelText('配置名称'), { target: { value: 'local' } })
    fireEvent.change(screen.getByLabelText('模型'), { target: { value: 'gpt-test' } })
    const password = screen.getByLabelText('API Key（只写入，不回显）')
    fireEvent.change(password, { target: { value: 'typed' } })
    fireEvent.click(screen.getByRole('button', { name: /保\s*存/ }))
    await waitFor(() => expect(onError).toHaveBeenCalled())
    expect(password).toHaveValue('')
    expect(localStorage.length).toBe(0)
  })
})
