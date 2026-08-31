/* 验证测试账号页面使用中文解释安全边界，并要求用户显式确认保存登录状态。 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { projectsApi } from '../../api/projects'
import { testIdentitiesApi } from '../../api/testIdentities'
import { TestIdentityPage } from './TestIdentityPage'

vi.mock('../../api/projects', () => ({ projectsApi: { understanding: vi.fn() } }))
vi.mock('../../api/testIdentities', () => ({ testIdentitiesApi: {
  list: vi.fn(), create: vi.fn(), reset: vi.fn(), delete: vi.fn(),
  startPreparation: vi.fn(), preparation: vi.fn(), confirmPreparation: vi.fn(), cancelPreparation: vi.fn(),
} }))

const role = { candidate_id: `role_${'a'.repeat(32)}`, canonical_key: 'member', display_name: '普通用户', confidence: 'HIGH', decision: 'CONFIRMED', origin: 'MANUAL', stale: false, evidence: [] }
const identity = {
  identity_id: `tid_${'b'.repeat(32)}`, project_id: 'sample-project', role_candidate_id: role.candidate_id,
  role_canonical_key: 'member', role_display_name: '普通用户', label: '普通用户A',
  confirmed_endpoint: 'http://127.0.0.1:8865', auth_method: null, status: 'NOT_PREPARED',
  review_reasons: [], cookie_count: 0, prepared_at_us: null, refreshed_at_us: null, created_at_us: 1, updated_at_us: 1,
}

function pageProps() {
  return {
    project: { project_id: 'sample-project', name: '样例' },
    onError: vi.fn(),
    onBack: vi.fn(),
    onStateChanged: vi.fn().mockResolvedValue({ status: {}, readiness: {}, runs: [] }),
    onContinuePreparation: vi.fn(),
  }
}

describe('TestIdentityPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(projectsApi.understanding).mockResolvedValue({ role_candidates: [role] } as never)
    vi.mocked(testIdentitiesApi.list).mockResolvedValue([identity] as never)
    vi.mocked(testIdentitiesApi.preparation).mockResolvedValue({
      preparation_id: `prep_poll_${'e'.repeat(28)}`, identity_id: identity.identity_id,
      status: 'WAITING_FOR_LOGIN', message: '请在独立浏览器中完成登录', error_code: null,
      log_path: 'D:/sample/var/logs/identity-preparations/prep.log',
    } as never)
  })

  it('说明不保存密码并显示每个已确认角色的账号准备情况', async () => {
    render(<TestIdentityPage {...pageProps()} />)
    expect(await screen.findByRole('heading', { name: '测试账号' })).toBeInTheDocument()
    expect(screen.getByText(/独立窗口中自行完成密码/)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '按权限组准备' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '普通用户' })).toBeInTheDocument()
    expect(screen.getByText('普通用户A')).toBeInTheDocument()
    expect(screen.getByText(/用于验证“普通用户”在合法路径和禁止路径中的真实权限边界/)).toBeInTheDocument()
    expect(screen.getByPlaceholderText('例如：普通用户A / 管理员测试账号')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '打开登录浏览器' })).toBeInTheDocument()
    expect(screen.queryByText(/Cookie|Bearer|内部标识/)).not.toBeInTheDocument()
  })

  it('只有用户明确确认后才请求保存测试状态', async () => {
    vi.mocked(testIdentitiesApi.startPreparation).mockResolvedValue({
      preparation_id: `prep_${'c'.repeat(32)}`, identity_id: identity.identity_id,
      status: 'WAITING_FOR_LOGIN', message: '请在独立浏览器中完成登录', error_code: null,
      log_path: 'D:/sample/var/logs/identity-preparations/prep.log',
    })
    vi.mocked(testIdentitiesApi.confirmPreparation).mockResolvedValue({
      preparation_id: `prep_${'c'.repeat(32)}`, identity_id: identity.identity_id,
      status: 'PREPARED', message: '测试账号登录状态已安全保存', error_code: null,
      log_path: 'D:/sample/var/logs/identity-preparations/prep.log',
    })
    const props = pageProps()
    render(<TestIdentityPage {...props} />)
    fireEvent.click(await screen.findByRole('button', { name: '打开登录浏览器' }))
    expect(await screen.findByText('不要关闭这个窗口')).toBeInTheDocument()
    expect(screen.getByText('在新窗口完成登录')).toBeInTheDocument()
    const confirm = await screen.findByRole('button', { name: '我已完成登录' })
    expect(testIdentitiesApi.confirmPreparation).not.toHaveBeenCalled()
    fireEvent.click(confirm)
    await waitFor(() => expect(testIdentitiesApi.confirmPreparation).toHaveBeenCalledWith(`prep_${'c'.repeat(32)}`))
    expect(await screen.findByText('登录状态已准备；界鉴没有保存你的密码')).toBeInTheDocument()
    const header = screen.getByRole('region', { name: '测试账号' })
    expect(screen.getByRole('button', { name: '继续准备' })).toBeInTheDocument()
    expect(props.onStateChanged).toHaveBeenCalled()
    expect(header).not.toHaveTextContent('完成当前登录准备')
    expect(header).not.toHaveTextContent('继续准备')
  })

  it('保存中显示固定的安全保存提示', async () => {
    vi.mocked(testIdentitiesApi.startPreparation).mockResolvedValue({
      preparation_id: `prep_${'d'.repeat(32)}`, identity_id: identity.identity_id,
      status: 'WAITING_FOR_LOGIN', message: '请在独立浏览器中完成登录', error_code: null,
      log_path: 'D:/sample/var/logs/identity-preparations/prep.log',
    })
    vi.mocked(testIdentitiesApi.confirmPreparation).mockResolvedValue({
      preparation_id: `prep_${'d'.repeat(32)}`, identity_id: identity.identity_id,
      status: 'SAVING', message: '正在保存', error_code: null,
      log_path: 'D:/sample/var/logs/identity-preparations/prep.log',
    })
    render(<TestIdentityPage {...pageProps()} />)
    fireEvent.click(await screen.findByRole('button', { name: '打开登录浏览器' }))
    fireEvent.click(await screen.findByRole('button', { name: '我已完成登录' }))
    expect(await screen.findByText('正在安全保存这个应用所需的登录状态…')).toBeInTheDocument()
  })

  it('刷新账号状态只重新读取权限组和账号事实', async () => {
    const props = pageProps()
    render(<TestIdentityPage {...props} />)
    expect(await screen.findByText('普通用户A')).toBeInTheDocument()
    vi.mocked(projectsApi.understanding).mockClear()
    vi.mocked(testIdentitiesApi.list).mockClear()

    fireEvent.click(screen.getByRole('button', { name: '刷新账号状态' }))

    await waitFor(() => expect(testIdentitiesApi.list).toHaveBeenCalledOnce())
    expect(projectsApi.understanding).toHaveBeenCalledOnce()
    expect(testIdentitiesApi.create).not.toHaveBeenCalled()
    expect(testIdentitiesApi.startPreparation).not.toHaveBeenCalled()
    expect(testIdentitiesApi.reset).not.toHaveBeenCalled()
    expect(props.onStateChanged).toHaveBeenCalledOnce()
  })

  it('本地刷新成功但工作区同步失败时给出可恢复提示', async () => {
    const props = pageProps()
    props.onStateChanged.mockResolvedValue(undefined)
    render(<TestIdentityPage {...props} />)

    fireEvent.click(await screen.findByRole('button', { name: '刷新账号状态' }))

    expect(await screen.findByText('账号状态已刷新，但工作区状态刷新失败，请重试“刷新账号状态”。')).toBeInTheDocument()
  })
})
