import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { OnboardingWizard } from './OnboardingWizard'

const mockApi = vi.hoisted(() => ({
  selectFolder: vi.fn(),
  inspect: vi.fn(),
  createSession: vi.fn(),
  getSession: vi.fn(),
  updateSession: vi.fn(),
  putCredentials: vi.fn(),
  quickCheck: vi.fn(),
}))

vi.mock('../../../api/onboarding', () => ({ onboardingApi: mockApi }))

const session = (overrides = {}) => ({
  schema_version: '1',
  session_id: 'onb_session',
  revision: 0,
  status: 'DRAFT',
  source_path: 'D:\\apps\\demo',
  project_name: 'demo',
  mode: 'quick',
  target_address: null,
  primary_display_name: null,
  comparison_display_name: null,
  primary_resource_id: null,
  comparison_resource_id: null,
  read_only_path_template: null,
  recovery_path: null,
  startup_candidate_source: null,
  confirmations: { app_started: false, target_authorized: false, recovery_confirmed: false, dangerous_inference_confirmed: false },
  primary_configured: false,
  comparison_configured: false,
  missing_items: ['应用已由用户启动确认', '目标地址', '测试账号显示名', '归属资源', '只读路径', '恢复方式确认'],
  ...overrides,
})

const discovery = {
  schema_version: '1',
  detected_types: ['Node.js'],
  start_candidates: [{ label: '开发服务', command: 'pnpm run dev', source: 'package.json:scripts.dev', confirmation_required: true, executed: false, safety_note: '只供复制' }],
  config_hints: [{ detail: '发现配置', source: 'package.json', confirmation_required: true }],
  interface_hints: [],
  auth_hints: [],
  missing_items: [],
  warnings: [],
}

describe('OnboardingWizard', () => {
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
  })

  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('首屏只有新手主入口，高级执行配置不在向导默认路径', () => {
    render(<OnboardingWizard />)
    expect(screen.getByRole('button', { name: '选择应用文件夹' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '开始体验' })).not.toBeInTheDocument()
    expect(screen.queryByText('项目 YAML')).not.toBeInTheDocument()
  })

  it('取消选择不是错误，并支持手工路径识别和创建会话', async () => {
    mockApi.selectFolder.mockResolvedValue({ status: 'cancelled' })
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: '选择应用文件夹' }))
    expect(await screen.findByText(/已取消选择/)).toBeInTheDocument()
    mockApi.inspect.mockResolvedValue(discovery)
    mockApi.createSession.mockResolvedValue(session())
    fireEvent.click(screen.getByText('无法打开目录选择器？'))
    fireEvent.change(screen.getByLabelText('应用文件夹绝对路径'), { target: { value: 'D:\\apps\\demo' } })
    fireEvent.click(screen.getByRole('button', { name: '识别文件夹' }))
    await waitFor(() => expect(mockApi.createSession).toHaveBeenCalledWith('D:\\apps\\demo', 'demo'))
    expect(localStorage.getItem('product.backend.workflows.onboarding.session')).toBe('onb_session')
    expect(screen.getByText('项目类型：Node.js')).toBeInTheDocument()
  })

  it('等待系统选择器时给出可见提示，并在不可用后恢复操作', async () => {
    let finish: ((value: { status: 'unavailable'; message: string }) => void) | undefined
    mockApi.selectFolder.mockImplementation(() => new Promise((resolve) => { finish = resolve }))
    render(<OnboardingWizard />)

    fireEvent.click(screen.getByRole('button', { name: '选择应用文件夹' }))

    expect(await screen.findByText(/请在系统窗口中完成选择/)).toBeInTheDocument()
    expect(mockApi.selectFolder).toHaveBeenCalledWith(expect.any(AbortSignal))
    await act(async () => finish?.({ status: 'unavailable', message: '桌面不可用，请改用手工绝对路径' }))
    expect(await screen.findByText('桌面不可用，请改用手工绝对路径')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: '选择应用文件夹' })).not.toBeDisabled())
  })

  it('客户端超时会终止等待并恢复手工路径回退', async () => {
    vi.useFakeTimers()
    mockApi.selectFolder.mockImplementation((signal: AbortSignal) => new Promise((_resolve, reject) => {
      signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
    }))
    render(<OnboardingWizard />)
    fireEvent.click(screen.getByRole('button', { name: '选择应用文件夹' }))

    await act(async () => { await vi.advanceTimersByTimeAsync(125_000) })

    expect(screen.getByText(/打开目录选择器超时/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '选择应用文件夹' })).not.toBeDisabled()
  })

  it('失效 session 只清理 session_id 并回到首屏', async () => {
    localStorage.setItem('product.backend.workflows.onboarding.session', 'onb_stale')
    mockApi.getSession.mockRejectedValue(new Error('gone'))
    render(<OnboardingWizard />)
    expect(await screen.findByText(/之前的新手会话已失效/)).toBeInTheDocument()
    expect(localStorage.getItem('product.backend.workflows.onboarding.session')).toBeNull()
    expect(screen.getByRole('button', { name: '选择应用文件夹' })).toBeInTheDocument()
  })

  it('项目名失焦不单独 PATCH，并在保存启动确认时使用同一 revision', async () => {
    const current = session({ revision: 4, confirmations: { schema_version: '1', app_started: false, target_authorized: false, recovery_confirmed: false, dangerous_inference_confirmed: false } })
    const updated = session({ ...current, revision: 5, project_name: '新名称', confirmations: { ...current.confirmations, app_started: true }, startup_candidate_source: 'manual:user-started' })
    localStorage.setItem('product.backend.workflows.onboarding.session', 'onb_session')
    mockApi.getSession.mockResolvedValue(current)
    mockApi.inspect.mockResolvedValue(discovery)
    mockApi.updateSession.mockResolvedValue(updated)
    render(<OnboardingWizard />)
    const name = await screen.findByLabelText('项目名称')
    fireEvent.change(name, { target: { value: '新名称' } })
    fireEvent.blur(name)
    expect(mockApi.updateSession).not.toHaveBeenCalled()
    fireEvent.click(screen.getByLabelText('应用已经在本机运行'))
    fireEvent.click(screen.getByRole('button', { name: '保存并继续' }))
    await waitFor(() => expect(mockApi.updateSession).toHaveBeenCalledTimes(1))
    expect(mockApi.updateSession).toHaveBeenCalledWith('onb_session', 4, { project_name: '新名称', startup_candidate_source: 'manual:user-started', confirmations: { app_started: true, target_authorized: false, recovery_confirmed: false, dangerous_inference_confirmed: false } })
    expect(await screen.findByText('允许访问哪些地址')).toBeInTheDocument()
    expect(screen.queryByText('测试账号有哪些')).not.toBeInTheDocument()
  })

  it('刷新恢复重新识别失败时保留会话答案，并定位到第一个缺项步骤', async () => {
    const current = session({ revision: 2, confirmations: { app_started: true, target_authorized: false, recovery_confirmed: false, dangerous_inference_confirmed: false }, target_address: null })
    localStorage.setItem('product.backend.workflows.onboarding.session', 'onb_session')
    mockApi.getSession.mockResolvedValue(current)
    mockApi.inspect.mockRejectedValue(new Error('unavailable'))
    render(<OnboardingWizard />)
    expect(await screen.findByText('允许访问哪些地址')).toBeInTheDocument()
    expect(await screen.findByText(/暂时无法重新识别/)).toBeInTheDocument()
    expect(screen.getByDisplayValue('demo')).toBeInTheDocument()
    expect(localStorage.getItem('product.backend.workflows.onboarding.session')).toBe('onb_session')
  })

  it('SUBMITTED 会话显示已提交且不允许继续修改', async () => {
    const submitted = session({ status: 'SUBMITTED', revision: 8, confirmations: { app_started: true, target_authorized: true, recovery_confirmed: true, dangerous_inference_confirmed: true }, primary_configured: true, comparison_configured: true, target_address: 'http://127.0.0.1:8765', read_only_path_template: '/resources/{resource_id}', recovery_path: '/reset', missing_items: [] })
    localStorage.setItem('product.backend.workflows.onboarding.session', 'onb_session')
    mockApi.getSession.mockResolvedValue(submitted)
    mockApi.inspect.mockResolvedValue(discovery)
    render(<OnboardingWizard />)
    expect(await screen.findByText('检查已提交')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '开始快速检查' })).toBeDisabled()
    expect(screen.getByLabelText('项目名称')).toBeDisabled()
  })

  it('密码提交后清空输入，不写入 localStorage，并使用最新 revision 和完整确认', async () => {
    const current = session({ revision: 3, target_address: 'http://127.0.0.1:8765', confirmations: { app_started: true, target_authorized: true, recovery_confirmed: false, dangerous_inference_confirmed: false }, missing_items: ['测试账号显示名', '归属资源', '恢复方式确认'] })
    localStorage.setItem('product.backend.workflows.onboarding.session', 'onb_session')
    mockApi.getSession.mockResolvedValue(current)
    mockApi.updateSession.mockResolvedValue(session({ ...current, revision: 4, primary_display_name: '主', comparison_display_name: '对照', primary_resource_id: 'owner', comparison_resource_id: 'attacker', confirmations: { ...current.confirmations } }))
    mockApi.putCredentials.mockResolvedValue({ primary_configured: true, comparison_configured: true })
    render(<OnboardingWizard />)
    await screen.findByText('两个测试账号')
    fireEvent.change(screen.getByLabelText('主账号显示名'), { target: { value: '主' } })
    fireEvent.change(screen.getByLabelText('对照账号显示名'), { target: { value: '对照' } })
    fireEvent.change(screen.getByLabelText('主账号拥有的资源标识'), { target: { value: 'owner' } })
    fireEvent.change(screen.getByLabelText('对照账号拥有的资源标识'), { target: { value: 'attacker' } })
    const passwordInputs = document.querySelectorAll('input[type="password"]')
    fireEvent.change(passwordInputs[0], { target: { value: 'one-secret' } })
    fireEvent.change(passwordInputs[1], { target: { value: 'two-secret' } })
    fireEvent.click(screen.getByRole('button', { name: '保存并继续' }))
    await waitFor(() => expect(mockApi.putCredentials).toHaveBeenCalledWith('onb_session', 'one-secret', 'two-secret'))
    expect(screen.queryByDisplayValue('one-secret')).not.toBeInTheDocument()
    expect(screen.queryByDisplayValue('two-secret')).not.toBeInTheDocument()
    expect(localStorage.getItem('one-secret')).toBeNull()
    expect(mockApi.updateSession).toHaveBeenCalledWith('onb_session', 3, expect.objectContaining({ confirmations: expect.objectContaining({ app_started: true, target_authorized: true }) }))
  })

  it('快速检查直接转交后端已排队的真实标识，不重复创建运行任务', async () => {
    const ready = session({
      revision: 6,
      target_address: 'http://127.0.0.1:8765',
      primary_display_name: '主',
      comparison_display_name: '对照',
      primary_resource_id: 'owner',
      comparison_resource_id: 'attacker',
      read_only_path_template: '/resources/{resource_id}',
      recovery_path: '/reset',
      confirmations: { app_started: true, target_authorized: true, recovery_confirmed: true, dangerous_inference_confirmed: true },
      primary_configured: true,
      comparison_configured: true,
      missing_items: [],
    })
    mockApi.getSession.mockResolvedValue(ready)
    mockApi.updateSession.mockResolvedValue(ready)
    mockApi.quickCheck.mockResolvedValue({ schema_version: '1', session: ready, project_id: 'onboarding_ready', run_id: 'run_ready', job_id: 'job_ready', created: true })
    const onSubmitted = vi.fn()
    localStorage.setItem('product.backend.workflows.onboarding.session', 'onb_session')
    render(<OnboardingWizard onSubmitted={onSubmitted} />)
    await screen.findByText('检查后怎样恢复数据')
    fireEvent.click(screen.getByRole('button', { name: '开始快速检查' }))
    await waitFor(() => expect(onSubmitted).toHaveBeenCalledWith({ project_id: 'onboarding_ready', run_id: 'run_ready', job_id: 'job_ready' }))
    expect(mockApi.updateSession).toHaveBeenCalledWith('onb_session', 6, expect.objectContaining({ read_only_path_template: '/resources/{resource_id}', recovery_path: '/reset', confirmations: expect.objectContaining({ recovery_confirmed: true, dangerous_inference_confirmed: true }) }))
    expect(mockApi.quickCheck).toHaveBeenCalledWith('onb_session')
    expect(mockApi.createSession).not.toHaveBeenCalled()
  })
})
