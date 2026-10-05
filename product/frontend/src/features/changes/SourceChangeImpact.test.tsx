// 验证旧批次使用原规则修订，未知关联完整可见，且影响展示不改变检查范围。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import type { SourceChangeViewDto } from '../../api/changes/sourceChanges'
import { SourceChangeImpact } from './SourceChangeImpact'

const api = vi.hoisted(() => ({ rule: vi.fn(), preparation: vi.fn() }))
vi.mock('../../api/boundaries/ruleDetails', () => ({ ruleDetailsApi: { read: api.rule } }))
vi.mock('../../api/preparation/preparation', () => ({ preparationApi: { get: api.preparation } }))
const first = { intent_id: 'deny', revision: 2, intent_hash: 'a'.repeat(64) }
const second = { intent_id: 'allow', revision: 4, intent_hash: 'b'.repeat(64) }
const change: SourceChangeViewDto = {
  manifest: { project_id: 'p1', change_id: 'old', reason: '修改导出', submitted_by: 'MCP', created_at_us: 1, claimed_paths: [], repair_reference: null },
  change_set: { status: 'COMPARABLE', added_paths: [], modified_paths: ['export.js'], removed_paths: [] },
  assessment: { payload: { policy_epoch: 6, permission_refs: [first, second], action_impacts: [
    { action_id: 'export', action_revision: 1, classification: 'DIRECTLY_AFFECTED', relevant_paths: ['export.js'], permission_refs: [first] },
    { action_id: 'view', action_revision: 3, classification: 'NO_DIRECT_EVIDENCE', relevant_paths: [], permission_refs: [second] },
  ] } }, revalidation: { status: 'READY', can_execute: true, preparation_gaps: [] },
}
const props = (value = change) => ({ projectId: 'p1', change: value, action: <button>准备本批检查</button>, onNavigate: vi.fn(), onSource: vi.fn() })
beforeEach(() => {
  vi.clearAllMocks()
  api.rule.mockImplementation(async (project_id, intent_id, revision) => ({ project_id, intent_id, revision, sentence: intent_id === 'deny' ? '成员不得导出完整交付包。' : '成员可以查看协作资料。', expectation: intent_id === 'deny' ? 'DENY' : 'ALLOW', action_id: intent_id === 'deny' ? 'export' : 'view', action_revision: intent_id === 'deny' ? 1 : 3, action_label: '导出项目', effects: [] }))
  api.preparation.mockResolvedValue({ project_id: 'p1', actions: [], preparation_complete: false })
})
it('默认展开需关注规则，其他规则按需读取并保留完整检查说明', async () => {
  render(<SourceChangeImpact {...props()}/>);
  await screen.findByText('成员不得导出完整交付包。')
  expect(api.rule).toHaveBeenCalledWith('p1', 'deny', 2)
  expect(api.rule).not.toHaveBeenCalledWith('p1', 'allow', 4)
  fireEvent.click(screen.getByRole('button', { name: '展开暂未发现直接关联的权限 · 1 条' }))
  await screen.findByText('成员可以查看协作资料。')
  expect(screen.getByText('仍纳入完整检查')).toBeInTheDocument()
  fireEvent.click(screen.getAllByRole('button', { name: '查看关联依据' })[0])
  expect(await screen.findByText('export.js')).toBeInTheDocument()
})
it('源码再次变化时所有规则可见，旧分类不继续表示当前影响', async () => {
  render(<SourceChangeImpact {...props({ ...change, revalidation: { ...change.revalidation, status: 'SOURCE_STALE', can_execute: false } })}/>);
  await screen.findByText('成员可以查看协作资料。')
  expect(screen.getAllByText('当前关联待核对')).toHaveLength(2)
  expect(screen.queryByText('实现来源有改动')).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /展开暂未发现/ })).not.toBeInTheDocument()
})
it('缺少比较基线时不展示文件关联依据', async () => {
  render(<SourceChangeImpact {...props({ ...change, revalidation: { ...change.revalidation, status: 'NO_BASELINE', can_execute: false } })}/>);
  await screen.findByText('成员可以查看协作资料。')
  expect(screen.getAllByText('暂不能判断关联')).toHaveLength(2)
  expect(screen.queryByRole('button', { name: '查看关联依据' })).not.toBeInTheDocument()
})
it('精确规则读取失败不换成最新修订，重试仍读取原修订', async () => {
  api.rule.mockRejectedValueOnce(new Error('offline'))
  render(<SourceChangeImpact {...props()}/>);
  fireEvent.click(await screen.findByRole('button', { name: '重新读取规则' }))
  await screen.findByText('成员不得导出完整交付包。')
  expect(api.rule.mock.calls).toEqual([['p1', 'deny', 2], ['p1', 'deny', 2]])
})
it('拒绝服务端返回的另一修订文本', async () => {
  api.rule.mockResolvedValue({ project_id: 'p1', intent_id: 'deny', revision: 9, sentence: '错误的新规则' })
  render(<SourceChangeImpact {...props()}/>);
  await screen.findByRole('button', { name: '重新读取规则' })
  expect(screen.queryByText('错误的新规则')).not.toBeInTheDocument()
})
it('切换应用后旧异步规则响应不会覆盖新对象', async () => {
  let resolveOld!: (value: unknown) => void
  api.rule.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve }))
  const view = render(<SourceChangeImpact {...props()}/>);
  await waitFor(() => expect(api.rule).toHaveBeenCalled())
  view.rerender(<SourceChangeImpact {...props()} projectId="p2"/>);
  await screen.findByText('成员不得导出完整交付包。')
  resolveOld({ project_id: 'p1', intent_id: 'deny', revision: 2, action_id: 'export', action_revision: 1, sentence: '旧应用的规则' })
  await waitFor(() => expect(screen.queryByText('旧应用的规则')).not.toBeInTheDocument())
})
