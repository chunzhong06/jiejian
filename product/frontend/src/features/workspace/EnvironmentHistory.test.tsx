// 已归档项目仍可读取历史；任何身份或发布完整性不符都不能展示结论。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EnvironmentHistory } from './EnvironmentHistory'

const api = vi.hoisted(() => ({ project: vi.fn(), status: vi.fn(), story: vi.fn() }))
vi.mock('../../api/projects', () => ({ projectsApi: { project: api.project } }))
vi.mock('../../api/currentChecks', () => ({ currentChecksApi: { status: api.status, story: api.story } }))
vi.mock('../testing/CheckHistoryPage', () => ({ CheckHistoryPage: ({ requestedRunId, onNavigate, renderRun }: { requestedRunId?: string; onNavigate: (path: string) => void; renderRun: (id: string, back: () => void) => ReactNode }) => requestedRunId ? renderRun(requestedRunId, () => onNavigate('/history')) : <button onClick={() => onNavigate('/history?run_id=old-run')}>查看原项目结果</button> }))
vi.mock('../testing/CurrentResultStory', () => ({ CurrentResultStory: ({ historicalOnly }: { historicalOnly: boolean }) => <p>{historicalOnly ? '只读历史结论' : '错误的活动操作'}</p> }))
vi.mock('../changes/SourceIdentityPanel', () => ({ SourceIdentityPanel: ({ projectId, recordId, historicalOnly }: { projectId: string; recordId: string; historicalOnly: boolean }) => <p>{projectId}/{recordId}/{historicalOnly ? '只读源码记录' : '错误的活动操作'}</p> }))

describe('EnvironmentHistory', () => {
  beforeEach(() => {
    vi.resetAllMocks()
    api.project.mockResolvedValue({ project_id: 'old-project', name: '原项目', status: 'ARCHIVED' })
    api.status.mockResolvedValue({ run: { project_id: 'old-project', run_id: 'old-run', verdict: 'INCONCLUSIVE' }, result_integrity: 'VALID' })
    api.story.mockResolvedValue({ project_id: 'old-project', run_id: 'old-run', verdict: 'INCONCLUSIVE', judgement: '证据不足' })
  })
  it('按原项目精确读取结果与源码，不切换到当前活动项目', async () => {
    render(<EnvironmentHistory projectId="old-project" onBack={vi.fn()} onError={vi.fn()}/>)
    fireEvent.click(await screen.findByRole('button', { name: '查看原项目结果' }))
    expect(await screen.findByText('只读历史结论')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '源码对应' }))
    expect(screen.getByText('old-project/old-run/只读源码记录')).toBeInTheDocument()
    expect(api.status).toHaveBeenCalledWith('old-run')
    expect(api.story).toHaveBeenCalledWith('old-run')
    fireEvent.click(screen.getByRole('button', { name: '返回原项目检查历史' }))
    expect(screen.getByRole('button', { name: '查看原项目结果' })).toBeInTheDocument()
  })
  it('发布完整性失效时不读取或展示历史结论', async () => {
    api.status.mockResolvedValue({ run: { project_id: 'old-project', run_id: 'old-run' }, result_integrity: 'INVALID' })
    render(<EnvironmentHistory projectId="old-project" onBack={vi.fn()} onError={vi.fn()}/>)
    fireEvent.click(await screen.findByRole('button', { name: '查看原项目结果' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('无法展示本轮已发布结论')
    expect(api.story).not.toHaveBeenCalled()
  })
  it('拒绝跨项目响应，不将其他项目当作原项目', async () => {
    api.project.mockResolvedValue({ project_id: 'other-project', name: '其他项目', status: 'ARCHIVED' })
    const onError = vi.fn()
    render(<EnvironmentHistory projectId="old-project" onBack={vi.fn()} onError={onError}/>)
    await waitFor(() => expect(onError).toHaveBeenCalledOnce())
    expect(screen.queryByRole('button', { name: '查看原项目结果' })).not.toBeInTheDocument()
    expect(api.status).not.toHaveBeenCalled()
  })
})
