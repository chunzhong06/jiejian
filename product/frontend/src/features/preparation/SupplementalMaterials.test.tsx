// 验证材料登记的明确操作、只读边界、归属隔离和同次保存回执恢复。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SupplementalMaterials } from './SupplementalMaterials'
import { ApiError } from '../../api/http'
const api = vi.hoisted(() => ({ list: vi.fn(), preview: vi.fn(), create: vi.fn(), revise: vi.fn(), withdraw: vi.fn(), revisions: vi.fn() }))
vi.mock('../../api/supplementalMaterials', () => ({ supplementalMaterialsApi: api }))
const document = { schema_version: '1', project_id: 'p1', action_id: 'a1', action_revision: 1, title: '下载记录', source_label: '应用导出记录', claimed_resource_label: null, records: [{ recorded_at_us: 1, resource_label: '资料一', event_label: '已记录下载事件' }] }
const preview = { project_id: 'p1', action_id: 'a1', document, fingerprint: 'f'.repeat(64), record_count: 1, association_status: 'UNCONFIRMED', usage: 'SUPPLEMENTAL_ONLY' }
const saved = { ...document, material_id: 'mat_one', revision: 1, record_count: 1, received_at_us: 2, updated_at_us: 2, association_status: 'UNCONFIRMED', usage: 'SUPPLEMENTAL_ONLY', withdrawn: false, fingerprint: 'f'.repeat(64) }
const props = { projectId: 'p1', actionId: 'a1', actionRevision: 1, actionLabel: '下载资料', onBack: vi.fn() }
const upload = async () => {
  const file = new File([JSON.stringify(document)], 'records.json', { type: 'application/json' })
  Object.defineProperty(file, 'text', { value: async () => JSON.stringify(document) })
  fireEvent.change(screen.getByLabelText('选择补充材料文件'), { target: { files: [file] } })
  await screen.findByRole('heading', { name: '这份材料能说明什么' })
}
beforeEach(() => {
  vi.clearAllMocks(); api.list.mockResolvedValue({ project_id: 'p1', action_id: 'a1', items: [], has_more: false })
  api.preview.mockResolvedValue(preview); api.create.mockResolvedValue(saved); api.revise.mockResolvedValue({ ...saved, revision: 2 }); api.withdraw.mockResolvedValue({ ...saved, revision: 2, withdrawn: true }); api.revisions.mockResolvedValue({ project_id: 'p1', action_id: 'a1', items: [saved] })
})
it('读取与预览都不保存，明确确认后才登记补充材料', async () => {
  render(<SupplementalMaterials {...props}/>)
  await upload()
  expect(api.create).not.toHaveBeenCalled()
  expect(screen.getByText('目前只能作为补充材料')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '保存为补充材料' }))
  expect(await screen.findByRole('status')).toHaveTextContent('不会改变准备状态或检查结论')
  expect(api.create).toHaveBeenCalledWith('p1', 'a1', document, preview.fingerprint, expect.any(String))
})
it('未知保存回执仅回读，用户确认时复用完全相同的请求身份', async () => {
  api.create.mockRejectedValueOnce(new Error('lost response'))
  render(<SupplementalMaterials {...props}/>); await upload()
  fireEvent.click(screen.getByRole('button', { name: '保存为补充材料' }))
  await screen.findByText(/保存回执尚未确认/)
  expect(api.create).toHaveBeenCalledTimes(1)
  const key = api.create.mock.calls[0][4]
  fireEvent.click(screen.getByRole('button', { name: '确认同次保存' }))
  await waitFor(() => expect(api.create).toHaveBeenCalledTimes(2))
  expect(api.create.mock.calls[1][4]).toBe(key)
})
it('错误项目的预览不能成为可保存材料', async () => {
  api.preview.mockResolvedValue({ ...preview, project_id: 'other' })
  render(<SupplementalMaterials {...props}/>)
  const file = new File(['{}'], 'records.json'); Object.defineProperty(file, 'text', { value: async () => '{}' })
  fireEvent.change(screen.getByLabelText('选择补充材料文件'), { target: { files: [file] } })
  await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: '保存为补充材料' })).not.toBeInTheDocument()
  expect(api.create).not.toHaveBeenCalled()
})
it('明确拒绝保存后仍可取消并修正，不进入未知回执死路', async () => {
  api.create.mockRejectedValueOnce(new ApiError('STATE_PRECONDITION', '动作版本已变化'))
  render(<SupplementalMaterials {...props}/>); await upload()
  fireEvent.click(screen.getByRole('button', { name: '保存为补充材料' }))
  expect(await screen.findByText(/本次保存未被接受/)).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '确认同次保存' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '取消本次登记' })).toBeEnabled()
  expect(api.create).toHaveBeenCalledTimes(1)
})
it('查看已有材料和修订历史不提交新版本', async () => {
  api.list.mockResolvedValue({ project_id: 'p1', action_id: 'a1', items: [saved], has_more: false })
  render(<SupplementalMaterials {...props}/>)
  fireEvent.click(await screen.findByRole('button', { name: /下载记录/ }))
  fireEvent.click(screen.getByRole('button', { name: '查看全部修订' }))
  expect(await screen.findByRole('region', { name: '材料修订历史' })).toHaveTextContent('修订 1')
  expect(api.create).not.toHaveBeenCalled(); expect(api.revise).not.toHaveBeenCalled(); expect(api.withdraw).not.toHaveBeenCalled()
})
it('按精确修订位置继续读取历史，不重复最新一页', async () => {
  api.list.mockResolvedValue({ project_id: 'p1', action_id: 'a1', items: [{ ...saved, revision: 2 }], has_more: false })
  api.revisions.mockResolvedValueOnce({ project_id: 'p1', action_id: 'a1', items: [{ ...saved, revision: 2 }], has_more: true })
    .mockResolvedValueOnce({ project_id: 'p1', action_id: 'a1', items: [saved], has_more: false })
  render(<SupplementalMaterials {...props}/>)
  fireEvent.click(await screen.findByRole('button', { name: /下载记录/ }))
  fireEvent.click(screen.getByRole('button', { name: '查看全部修订' }))
  fireEvent.click(await screen.findByRole('button', { name: '读取更早修订' }))
  await waitFor(() => expect(screen.getByRole('region', { name: '材料修订历史' })).toHaveTextContent('修订 1'))
  expect(api.revisions.mock.calls[1]).toEqual(['p1', 'a1', 'mat_one', 2])
  expect(screen.queryByRole('button', { name: '读取更早修订' })).not.toBeInTheDocument()
})
