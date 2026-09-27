// 验证材料预览与保存分离，以及丢失回执后只回读同一操作。
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MaterialEditor } from './MaterialEditor'
const api = vi.hoisted(() => ({ material: vi.fn(), draft: vi.fn(), saveDraft: vi.fn(), previewMaterial: vi.fn(), saveMaterial: vi.fn(), materialReceipt: vi.fn() }))
vi.mock('../../api/preparation', () => ({ preparationApi: api }))
const reference = { action_id: 'action', action_revision: 1, kind: 'evidence' as const, member_id: 'effect' }
const draft = { schema_version: '1', revision: 1, action_id: 'action', action_revision: 1, material: reference,
  candidate_recording_id: null, base_fingerprint: 'basis', pending_operation_id: null }
const details = { material: reference, status: 'SATISFIED', reason_codes: [], retained: true, confirmed_at_us: 100,
  source_recording_id: 'old', expected_fingerprint: 'basis', candidates: [] }
const props = () => ({ projectId: 'project', reference, actionLabel: '导出项目', effectLabel: '交付包真实形成', onBack: vi.fn(), onSaved: vi.fn(), onError: vi.fn() })
beforeEach(() => {
  vi.clearAllMocks()
  api.material.mockResolvedValue(details); api.draft.mockResolvedValue(draft)
  api.saveDraft.mockImplementation(async (_project, value) => ({ ...value, revision: value.revision + 1 }))
  api.previewMaterial.mockResolvedValue({ updates: [], retained: [], recheck: [] })
})
it('先展示服务端影响，再由用户确认写入；核对不执行检查', async () => {
  const p = props(); render(<MaterialEditor {...p} />)
  fireEvent.click(await screen.findByRole('button', { name: '核对本次影响' }))
  expect(await screen.findByRole('button', { name: '确认沿用材料' })).toBeEnabled()
  expect(api.saveMaterial).not.toHaveBeenCalled()
  api.saveMaterial.mockResolvedValue({ result: 'RECHECKED' })
  fireEvent.click(screen.getByRole('button', { name: '确认沿用材料' }))
  await waitFor(() => expect(api.saveMaterial).toHaveBeenCalledTimes(1))
  expect(api.saveMaterial.mock.calls[0][1].expected_fingerprint).toBe('basis')
})
it('刷新后发现待确认操作，只核对既有回执，不重放保存', async () => {
  api.draft.mockResolvedValue({ ...draft, pending_operation_id: 'pending' })
  api.materialReceipt.mockRejectedValue(new Error('not found'))
  render(<MaterialEditor {...props()} />)
  fireEvent.click(await screen.findByRole('button', { name: '核对保存回执' }))
  await waitFor(() => expect(api.materialReceipt).toHaveBeenCalledWith('project', 'pending'))
  expect(api.saveMaterial).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '核对本次影响' })).toBeDisabled()
})
it('陈旧材料不能通过重新核对按钮伪装为可用', async () => {
  api.material.mockResolvedValue({ ...details, status: 'STALE', reason_codes: ['ACTION_BINDING_SOURCE_STALE'] })
  render(<MaterialEditor {...props()} />)
  expect(await screen.findByRole('button', { name: '核对本次影响' })).toBeDisabled()
  expect(screen.getByText('已保存，需复核')).toBeInTheDocument()
  expect(api.saveMaterial).not.toHaveBeenCalled()
})
it('从来源能力返回后只恢复一次入口焦点', async () => {
  render(<MaterialEditor {...props()} onEvidence={vi.fn()} focusSourceEntry />)
  const button = await screen.findByRole('button', { name: '查看证明要求与来源能力' })
  await waitFor(() => expect(button).toHaveFocus())
})
