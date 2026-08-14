import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RunPage } from './RunPage'

const permissionApi = vi.hoisted(() => ({
  profiles: vi.fn().mockResolvedValue([]),
  register: vi.fn(),
  submit: vi.fn(),
}))

vi.mock('../../api/permissionExecution', () => ({ permissionExecutionApi: permissionApi }))

vi.mock('./JobProgress', () => ({ JobProgress: () => null }))

describe('RunPage', () => {
  beforeEach(() => {
    cleanup()
    localStorage.clear()
    permissionApi.profiles.mockReset().mockResolvedValue([])
    permissionApi.register.mockReset()
    permissionApi.submit.mockReset()
  })

  it('复杂权限入口只使用 V2 API，且不保存 Profile 路径', async () => {
    permissionApi.profiles.mockResolvedValue([{ profile_id: 'profile-1', contract_id: 'contract-1', contract_version: 1 }])
    permissionApi.register.mockResolvedValue({ profile_id: 'profile-1', project_id: 'project-1' })
    permissionApi.submit.mockResolvedValue({ run: { run_id: 'run-v2' } })
    localStorage.clear()
    render(<RunPage project={{ project_id: 'project-1' }} runs={[]} onRefresh={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getByText('高级：复杂权限检查（Permission Profile V2）'))
    const input = await screen.findByLabelText('Permission Profile JSON 路径')
    fireEvent.change(input, { target: { value: 'D:\\profiles\\permission.json' } })
    fireEvent.click(screen.getByRole('button', { name: '登记配置' }))
    await waitFor(() => expect(permissionApi.register).toHaveBeenCalledWith('D:\\profiles\\permission.json', false))
    fireEvent.click(screen.getByRole('button', { name: '开始复杂权限检查' }))
    await waitFor(() => expect(permissionApi.submit).toHaveBeenCalledWith('project-1', 'profile-1'))
    expect(localStorage.getItem('D:\\profiles\\permission.json')).toBeNull()
    expect(JSON.stringify(localStorage)).not.toContain('D:\\profiles\\permission.json')
  })

  it('拒绝跨项目 Profile，且不提交', async () => {
    permissionApi.profiles.mockResolvedValue([])
    permissionApi.register.mockResolvedValue({ profile_id: 'profile-other', project_id: 'project-2' })
    permissionApi.submit.mockClear()
    render(<RunPage project={{ project_id: 'project-1' }} runs={[]} onRefresh={vi.fn()} onError={vi.fn()} />)
    fireEvent.click(screen.getAllByText('高级：复杂权限检查（Permission Profile V2）')[0])
    fireEvent.change(await screen.findByLabelText('Permission Profile JSON 路径'), { target: { value: 'D:\\profiles\\other.json' } })
    fireEvent.click(screen.getByRole('button', { name: '登记配置' }))
    expect(await screen.findByText(/与当前项目 project-1 不一致/)).toBeInTheDocument()
    expect(permissionApi.submit).not.toHaveBeenCalled()
  })

  it.each([
    ['FAILED', '检查失败，请查看恢复提示或重新开始'],
    ['CANCELLED', '已取消，可重新开始'],
  ])('%s 不提供验证导航', (lifecycle, message) => {
    render(<RunPage project={{ project_id: 'project-1' }} runs={[{ run_id: 'run-1', lifecycle, result_integrity: 'UNAVAILABLE' }]} onRefresh={vi.fn()} onError={vi.fn()} onNext={vi.fn()} />)
    expect(screen.getAllByText(message).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: '查看验证结果' })).not.toBeInTheDocument()
  })

  it('仅对已完成且结果完整性可读的运行提供验证导航', () => {
    const onNext = vi.fn()
    render(<RunPage project={{ project_id: 'project-1' }} runs={[{ run_id: 'run-1', lifecycle: 'COMPLETED', result_integrity: 'VERIFIED' }]} onRefresh={vi.fn()} onError={vi.fn()} onNext={onNext} />)
    fireEvent.click(screen.getByRole('button', { name: '查看验证结果' }))
    expect(onNext).toHaveBeenCalledTimes(1)
  })
})
