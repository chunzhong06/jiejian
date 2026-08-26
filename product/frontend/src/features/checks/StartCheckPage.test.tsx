// 验证开始检查预览、提交与运行进度的确定性页面行为。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StartCheckPage } from './StartCheckPage'

const checksApi = vi.hoisted(() => ({ preview: vi.fn(), submit: vi.fn() }))
const runsApi = vi.hoisted(() => ({ run: vi.fn(), progress: vi.fn(), cancel: vi.fn() }))
vi.mock('../../api/checks', () => ({ checksApi }))
vi.mock('../../api/runs', () => ({ runsApi }))

describe('StartCheckPage', () => {
  beforeEach(() => {
    checksApi.preview.mockResolvedValue({ project_id: 'p1', ready: true, actions: [], gaps: [], next_path: null, next_label: null, case_count: 2, differential_pair_count: 1 })
    runsApi.progress.mockResolvedValue({ job_id: 'job-test', attempt: 1, events: [] })
  })
  afterEach(() => { vi.clearAllMocks(); delete (globalThis as any).EventSource; localStorage.clear() })
  it('只在真实 completed/total 存在时显示数量与对应百分比', async () => {
    runsApi.run.mockResolvedValue({ run_id: 'run-1', lifecycle: 'RUNNING', result_integrity: 'UNAVAILABLE', case_progress: { completed: 2, total: 5 } })
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-1', lifecycle: 'RUNNING' }]} onRefresh={vi.fn()} onError={vi.fn()} />)
    expect(await screen.findByText('已完成 2/5 个用例')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('缺少真实总量时明确降级', async () => {
    runsApi.run.mockResolvedValue({ run_id: 'run-2', lifecycle: 'RUNNING', result_integrity: 'UNAVAILABLE', case_progress: { completed: null, total: null } })
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-2', lifecycle: 'RUNNING' }]} onRefresh={vi.fn()} onError={vi.fn()} />)
    expect(await screen.findByText('正在执行，暂时没有可确认的用例总量')).toBeInTheDocument()
  })

  it('展示人话差分预览并且普通路径不选择 Profile', async () => {
    checksApi.preview.mockResolvedValue({
      project_id: 'p1', ready: true, gaps: [{ code: 'ACTION_FLOW_OR_RESOURCE_MISSING', message: '尚未录制并确认这个业务动作', next_path: '/apps/flows', next_label: '去准备业务流程' }], next_path: '/apps/flows', next_label: '去准备业务流程', case_count: 2, differential_pair_count: 1,
      actions: [{ action_candidate_id: 'action-1', action_display_name: '修改测试文档', resource_logical_name: '所有者的测试文档', ready: true, gaps: [], checks: [
        { subject_label: '所有者账号', subject_role_display_name: '所有者', relation: 'OWNS', expectation: 'ALLOW', ready: true, gaps: [] },
        { subject_label: '同角色账号', subject_role_display_name: '所有者', relation: 'SAME_ROLE_OTHER_ACCOUNT', expectation: 'DENY', ready: true, gaps: [] },
      ] }, { action_candidate_id: 'action-2', action_display_name: '删除测试文档', resource_logical_name: null, ready: false, gaps: [{ code: 'ACTION_FLOW_OR_RESOURCE_MISSING', message: '尚未录制并确认这个业务动作', next_path: '/apps/flows', next_label: '去准备业务流程' }], checks: [] }],
    })
    checksApi.submit.mockResolvedValue({ schema_version: '1', run: { run_id: 'run-new', lifecycle: 'QUEUED' }, job: { job_id: 'job-new', state: 'QUEUED' } })

    const onResolved = vi.fn()
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[]} onRefresh={vi.fn()} onError={vi.fn()} onResolved={onResolved} />)

    expect(await screen.findByText('修改测试文档')).toBeInTheDocument()
    expect(onResolved).toHaveBeenCalledOnce()
    expect(screen.getByText('应该允许')).toBeInTheDocument()
    expect(screen.getByText('应该拒绝')).toBeInTheDocument()
    expect(screen.getByText('将执行 2 个检查用例，形成 1 组允许/拒绝对照，另外 1 个动作暂未覆盖。')).toBeInTheDocument()
    expect(screen.getByText('删除测试文档')).toBeInTheDocument()
    expect(screen.getByText('尚未录制并确认这个业务动作')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    screen.getByRole('button', { name: '开始检查' }).click()
    await waitFor(() => expect(checksApi.submit).toHaveBeenCalledWith('p1'))
    expect(onResolved).toHaveBeenCalledTimes(2)
  })

  it('观察到运行终态后补取一次权威项目状态', async () => {
    const onRefresh = vi.fn()
    const completed = { run_id: 'run-completed', lifecycle: 'COMPLETED', result_integrity: 'VERIFIED', verdict: 'BLOCK', job: { job_id: 'job-completed', state: 'SUCCEEDED' } }
    runsApi.run.mockResolvedValue(completed)

    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[completed]} onRefresh={onRefresh} onError={vi.fn()} />)

    await waitFor(() => expect(onRefresh).toHaveBeenCalledOnce())
  })

  it('同一运行进入失败状态后重新读取并展示可复制的诊断信息', async () => {
    runsApi.run
      .mockResolvedValueOnce({ run_id: 'run-failed', lifecycle: 'RUNNING', updated_at_us: 1, job: { job_id: 'job-failed', state: 'RUNNING' } })
      .mockResolvedValueOnce({
        run_id: 'run-failed',
        lifecycle: 'FAILED',
        updated_at_us: 2,
        job: { job_id: 'job-failed', state: 'FAILED' },
        execution_errors: [{ stage: '后台执行', message: 'Worker 在任务完成前异常退出', log_path: 'var/logs/workers/job-failed.log', recovery: '重新启动后再次检查。', copy_text: '请分析任务 job-failed 的失败原因。', diagnosis: { route: '/checks/start', headline: '隔离执行没有正常完成', short_message: '检查没有形成安全结论，请确认运行环境后重试。', cleanup_warnings: [] } }],
      })
    const onError = vi.fn()
    const onPrepare = vi.fn()
    const { rerender } = render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-failed', lifecycle: 'RUNNING', updated_at_us: 1, job: { job_id: 'job-failed', state: 'RUNNING' } }]} onRefresh={vi.fn()} onError={onError} onPrepare={onPrepare} />)
    await waitFor(() => expect(runsApi.run).toHaveBeenCalledTimes(1))

    rerender(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-failed', lifecycle: 'FAILED', updated_at_us: 2, job: { job_id: 'job-failed', state: 'FAILED' } }]} onRefresh={vi.fn()} onError={onError} onPrepare={onPrepare} />)

    expect(await screen.findByText('隔离执行没有正常完成')).toBeInTheDocument()
    expect(screen.getByText('检查没有形成安全结论，请确认运行环境后重试。')).toBeInTheDocument()
    screen.getByRole('button', { name: '前往处理页面' }).click()
    expect(onPrepare).toHaveBeenCalledWith('/checks/start')
    fireEvent.click(screen.getByRole('button', { name: /高级：执行错误详情/ }))
    expect(await screen.findByText('Worker 在任务完成前异常退出')).toBeInTheDocument()
    expect(screen.getByText(/var\/logs\/workers\/job-failed\.log/)).toBeInTheDocument()
    expect(screen.getByText('下一步：重新启动后再次检查。')).toBeInTheDocument()
    expect(screen.getByText('复制诊断信息')).toBeInTheDocument()
    expect(runsApi.run).toHaveBeenCalledTimes(2)
    expect(onError).not.toHaveBeenCalled()
  })

  it('从已保存游标续读事件并用真实 sequence 刷新状态', async () => {
    let source: any
    class FakeEventSource {
      onmessage?: (event: MessageEvent) => void
      onerror?: () => void
      close = vi.fn()
      constructor(public url: string) { source = this }
    }
    ;(globalThis as any).EventSource = FakeEventSource
    localStorage.setItem('jiejian.cursor.job-1', JSON.stringify(4))
    const refresh = vi.fn()
    runsApi.run.mockResolvedValue({ run_id: 'run-3', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } })
    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-3', lifecycle: 'RUNNING', job: { job_id: 'job-1', state: 'RUNNING' } }]} onRefresh={refresh} onError={vi.fn()} />)
    await waitFor(() => expect(source?.url).toBe('/api/jobs/job-1/events?after=4'))
    source.onmessage?.({ data: JSON.stringify({ sequence: 5, event_type: 'JOB_RUNNING' }), lastEventId: '' } as MessageEvent)
    expect(localStorage.getItem('jiejian.cursor.job-1')).toBe('5')
    expect(refresh).toHaveBeenCalled()
  })

  it('只展示真实旁路步骤的人话，未知动作不泄漏原始 ID', async () => {
    checksApi.preview.mockResolvedValue({
      project_id: 'p1', ready: true, actions: [
        { action_candidate_id: 'action-known', action_display_name: '修改资源', resource_logical_name: '测试资源', ready: true, gaps: [], checks: [{ subject_label: '成员账号', subject_role_display_name: '成员', relation: 'OWNS', expectation: 'ALLOW', ready: true, gaps: [] }] },
        { action_candidate_id: 'action-waiting', action_display_name: '删除资源', resource_logical_name: '测试资源', ready: true, gaps: [], checks: [{ subject_label: '成员账号', subject_role_display_name: '成员', relation: 'OWNS', expectation: 'DENY', ready: true, gaps: [] }] },
      ], gaps: [], next_path: null, next_label: null, case_count: 2, differential_pair_count: 1,
    })
    runsApi.run.mockResolvedValue({ run_id: 'run-progress', lifecycle: 'RUNNING', result_integrity: 'UNAVAILABLE', job: { job_id: 'job-progress', state: 'RUNNING' } })
    runsApi.progress.mockResolvedValue({ job_id: 'job-progress', attempt: 1, events: [
      { schema_version: '1', sequence: 1, case_id: 'case-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', action_id: 'action-known', twin_role: 'ALLOW_CONTROL', phase: 'RECOVERY', state: 'COMPLETED', recorded_at_us: 1 },
      { schema_version: '1', sequence: 2, case_id: 'case-bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', action_id: 'action-unknown', twin_role: 'DENY_VARIANT', phase: 'TARGET', state: 'STARTED', recorded_at_us: 2 },
    ] })

    render(<StartCheckPage project={{ project_id: 'p1' }} runs={[{ run_id: 'run-progress', lifecycle: 'RUNNING', job: { job_id: 'job-progress', state: 'RUNNING' } }]} onRefresh={vi.fn()} onError={vi.fn()} />)

    expect(await screen.findByText('修改资源 · 恢复测试数据')).toBeInTheDocument()
    expect(screen.getByText('删除资源 · 等待开始')).toBeInTheDocument()
    expect(screen.getByText('当前业务动作 · 尝试不应允许的操作')).toBeInTheDocument()
    expect(screen.getByText('已完成')).toBeInTheDocument()
    expect(screen.getByText('等待中')).toBeInTheDocument()
    expect(screen.getByText('进行中')).toBeInTheDocument()
    expect(screen.queryByText('action-unknown')).not.toBeInTheDocument()
    await waitFor(() => expect(runsApi.progress).toHaveBeenCalledWith('job-progress'))
  })
})
