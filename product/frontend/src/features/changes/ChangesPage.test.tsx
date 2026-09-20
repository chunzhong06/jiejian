// 当前变化页验证真实diff、精确change关联及未知回执不自动重复写入。
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ChangesPage } from './ChangesPage'
const api = vi.hoisted(() => ({ list: vi.fn(), show: vi.fn(), submit: vi.fn(), repair: vi.fn(), workspace: vi.fn() }))
vi.mock('../../api/workspace', () => ({ workspaceApi: { current: api.workspace } }))
vi.mock('../../api/sourceChanges', () => ({ sourceChangesApi: { list: api.list, show: api.show, submit: api.submit } }))
vi.mock('../../api/repairs', async () => ({ ...await vi.importActual<typeof import('../../api/repairs')>('../../api/repairs'), repairsApi: { project: api.repair } }))
const change = { manifest: { change_id: 'chg_one', project_id: 'p1', reason: '修改导出检查位置', submitted_by: 'MCP · Codex', created_at_us: 1, claimed_paths: ['wrong.py'], repair_reference: null }, change_set: { status: 'COMPARABLE', added_paths: [], modified_paths: ['real.py'], removed_paths: [] }, assessment: { payload: { action_impacts: [{ action_id: 'action', classification: 'DIRECTLY_AFFECTED', permission_refs: [], relevant_paths: ['real.py'] }] } }, revalidation: { status: 'READY', can_execute: true, preparation_gaps: [] } }
const props = () => ({ project: { project_id: 'p1' }, onNavigate: vi.fn(), onError: vi.fn(), onStateChanged: vi.fn() })
describe('当前变化与修复', () => {
  beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue([change]); api.repair.mockResolvedValue({ project_id: 'p1', status: null, tasks: [], primary_task_reference: null }); api.submit.mockResolvedValue(change) })
  it('展示真实文件并把精确变化带到完整检查', async () => {
    const p = props(); render(<ChangesPage {...p} />)
    expect(await screen.findByRole('heading', {name:'修改导出检查位置'})).toBeInTheDocument()
    expect(screen.getByText('real.py')).toBeInTheDocument()
    expect(screen.queryByText('wrong.py')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '检查这次变化' }))
    expect(p.onNavigate).toHaveBeenCalledWith('/tests?change_id=chg_one')
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('已有登记只读取当前材料任务，不重复登记或发起检查', async () => {
    api.workspace.mockResolvedValue({ project: { project_id: 'p1' }, primary_task: { route: '/tests', task_kind: 'PREPARE_TEST_IDENTITY', task_id: 'exact-task' } })
    const p = props(); render(<ChangesPage {...p}/>)
    fireEvent.click(await screen.findByRole('button', { name: '核对现有材料' }))
    await waitFor(() => expect(p.onNavigate).toHaveBeenCalledWith('/tests?task_id=exact-task'))
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('只在明确提交时登记说明和相对路径', async () => {
    const p = props(); render(<ChangesPage {...p} />)
    await screen.findByRole('heading', {name:'修改导出检查位置'})
    fireEvent.click(screen.getByText('Agent 连接与手动接管'))
    fireEvent.change(screen.getByLabelText('修改说明'), { target: { value: ' 调整导出授权 ' } })
    fireEvent.change(screen.getByLabelText('涉及文件（可选，每行一个相对路径）'), { target: { value: 'src/app.py' } })
    fireEvent.click(screen.getByRole('button', { name: '登记并核对实际变化' }))
    await waitFor(() => expect(api.submit).toHaveBeenCalledWith('p1', '调整导出授权', ['src/app.py'], null))
  })
  it('读取损坏或跨项目事实时关闭写入入口', async () => {
    api.repair.mockResolvedValue({ project_id: 'other', tasks: [] })
    const p = props(); render(<ChangesPage {...p} />)
    expect(await screen.findByText('无法完整读取变化与原题，暂不能登记或发起复验。')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '登记并核对实际变化', hidden: true })).toBeDisabled()
    expect(screen.queryByText('修改导出检查位置')).not.toBeInTheDocument()
  })
  it('未知登记回执只回读，不自动重复提交', async () => {
    api.submit.mockRejectedValue(new Error('response unavailable'))
    render(<ChangesPage {...props()} />)
    await screen.findByRole('heading', {name:'修改导出检查位置'})
    fireEvent.click(screen.getByText('Agent 连接与手动接管'))
    fireEvent.change(screen.getByLabelText('修改说明'), { target: { value: '修复导出' } })
    fireEvent.click(screen.getByRole('button', { name: '登记并核对实际变化' }))
    await screen.findByText('上次登记回执未确认。请先查看下方变化记录，避免重复登记。')
    expect(api.submit).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '登记并核对实际变化', hidden: true })).toBeDisabled()
  })
  it('不接受查询参数伪造的原题引用', async () => {
    const p = props(); render(<ChangesPage {...p} requestedRepair="unknown" />)
    await screen.findByRole('heading', {name:'修改导出检查位置'})
    fireEvent.click(screen.getByText('Agent 连接与手动接管'))
    fireEvent.change(screen.getByLabelText('修改说明'), { target: { value: '修复导出' } })
    fireEvent.click(screen.getByRole('button', { name: '登记并核对实际变化' }))
    await waitFor(() => expect(p.onError).toHaveBeenCalled())
    expect(api.submit).not.toHaveBeenCalled()
  })
  it('没有历史变化仍允许显式登记，不伪造安全状态', async () => {
    api.list.mockResolvedValue([]); render(<ChangesPage {...props()} />)
    expect(await screen.findByText('尚无代码变化记录')).toBeInTheDocument()
    expect(screen.queryByText('原题复验通过')).not.toBeInTheDocument()
  })
  it('缺少基线不把文件清单误当成已核实差异', async () => {
    api.list.mockResolvedValue([{ ...change, change_set: { ...change.change_set, status: 'NO_BASELINE' } }])
    render(<ChangesPage {...props()}/>)
    await screen.findByRole('heading', { name: '修改导出检查位置' })
    expect(screen.getByText('缺少基线，本次不展示差异清单。')).toBeInTheDocument()
    expect(screen.queryByText('real.py')).not.toBeInTheDocument()
  })
  it('同批只有部分原题通过时，不显示整体通过标题', async () => {
    const contract = { source_run_id: 'run', source_case_id: 'case', repair_fingerprint: 'ref', regressions: [] }
    api.repair.mockResolvedValue({ project_id: 'p1', primary_task_reference: null, tasks: [
      { task_reference: 'one', contract, change_id: 'chg_one', status: 'VERIFIED' },
      { task_reference: 'two', contract: { ...contract, repair_fingerprint: 'two' }, change_id: 'chg_one', status: 'INCONCLUSIVE' },
    ] })
    render(<ChangesPage {...props()}/>)
    expect(await screen.findByRole('heading', { name: '修改已登记，修复状态尚待确认' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '本批修改的原题复验已通过' })).not.toBeInTheDocument()
    expect(within(screen.getByRole('navigation', { name: '修改记录' })).queryByText('原题复验已通过')).not.toBeInTheDocument()
  })
  it('原题关联较早批次时按精确 ID 补读，刷新后仍保留所选批次', async () => {
    api.repair.mockResolvedValue({ project_id: 'p1', primary_task_reference: null, tasks: [{ task_reference: 'task', contract: { source_run_id: 'run', source_case_id: 'case', repair_fingerprint: 'ref', regressions: [] }, change_id: 'older', status: 'CHANGE_SUBMITTED' }] })
    api.show.mockResolvedValue({ ...change, manifest: { ...change.manifest, change_id: 'older', reason: '较早的精确批次' } })
    render(<ChangesPage {...props()} requestedRepair="ref"/>)
    fireEvent.click(await screen.findByRole('button', { name: '查看本批修改' }))
    expect(await screen.findByRole('heading', { name: '较早的精确批次' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: '刷新变化与修复' })).not.toHaveClass('ant-btn-loading'))
    fireEvent.click(screen.getByRole('button', { name: '刷新变化与修复' }))
    await waitFor(() => expect(api.show).toHaveBeenCalledWith('p1', 'older'))
    expect(screen.getByRole('heading', { name: '较早的精确批次' })).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '修改导出检查位置' })).not.toBeInTheDocument()
  })
})
