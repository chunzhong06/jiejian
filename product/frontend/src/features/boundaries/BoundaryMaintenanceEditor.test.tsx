// 验证维护编辑器保留 stable identity，并只把 desired state 交给服务端决策。

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BoundaryMaintenanceDraftDto } from '../../api/businessBoundaries'
import { BoundaryMaintenanceEditor } from './BoundaryMaintenanceEditor'

const ai = vi.hoisted(() => ({ generate: vi.fn(), maintenanceDraft: vi.fn() }))
vi.mock('../../api/permissionDrafts', () => ({ permissionDraftsApi: { generate: ai.generate } }))
vi.mock('../../api/businessBoundaries', () => ({ businessBoundariesApi: { maintenanceDraft: ai.maintenanceDraft } }))
vi.mock('../../components/AssistantPanel', () => ({ AssistantPanel: () => null }))
const actorId = `bar_${'1'.repeat(32)}`
const actionId = `bac_${'2'.repeat(32)}`
const effectId = `bef_${'3'.repeat(32)}`
const intentId = `pin_${'4'.repeat(32)}`

const draft: BoundaryMaintenanceDraftDto = {
  project_id: 'p1', boundary_state_fingerprint: 'f'.repeat(64),
  actors: [{
    item_id: 'pactr_existing', actor_id: actorId, expected_current_revision: 2,
    display_name: '项目负责人', description: '负责项目交付', effective_state: 'ACTIVE',
    source_candidate_ids: [`role_${'5'.repeat(32)}`],
  }],
  actions: [{
    item_id: 'pactn_existing', action_id: actionId, expected_current_revision: 3,
    display_name: '导出交付包', description: '导出完整项目交付内容',
    primary_resource_concept: '项目交付包', operation_kind: 'EXPORT', state_changing: true,
    effects: [{
      item_id: 'peff_existing', effect_id: effectId, business_label: '交付包真实形成',
      effect_kind: 'OBJECT_CREATION', resource_concept: '项目交付包',
      expected_state: null, protected_projection: [], description: '导出文件已经生成',
    }],
    effective_state: 'ACTIVE', source_candidate_ids: [`action_${'6'.repeat(32)}`],
  }],
  permissions: [{
    item_id: 'pperm_existing', intent_id: intentId, expected_current_revision: 4,
    effective_state: 'ACTIVE', subject_actor_item_id: 'pactr_existing',
    business_action_item_id: 'pactn_existing', resource_owner_actor_item_id: 'pactr_existing',
    relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: ['peff_existing'],
  }],
  candidate_options: [
    { candidate_kind: 'ROLE', candidate_id: `role_${'5'.repeat(32)}`, display_name: '项目负责人', confidence: 'HIGH', evidence_available: true },
    { candidate_kind: 'ACTION', candidate_id: `action_${'6'.repeat(32)}`, display_name: '导出交付包', confidence: 'MEDIUM', evidence_available: true },
  ],
  implementation_inspections: [],
}

beforeEach(() => { vi.clearAllMocks(); ai.maintenanceDraft.mockResolvedValue(draft) })
const suggestion = { option_ids: ['opt-1'], subject_actor_id: actorId, subject_actor_revision: 2, business_action_id: actionId, action_revision: 3, resource_owner_actor_id: actorId, resource_owner_actor_revision: 2, relation: 'OWNS', protected_effect_ids: [effectId], subject_display_name: '项目负责人', action_display_name: '导出交付包', resource_owner_display_name: '项目负责人', effect_display_names: ['交付包真实形成'], current_expectation: 'ALLOW', suggested_expectation: 'DENY', source_quotes: ['负责人不得导出交付包'] }
const response = { project_id: 'p1', boundary_fingerprint: 'semantic', status: 'READY_FOR_REVIEW', suggestions: [suggestion], issues: [] }
describe('BoundaryMaintenanceEditor', () => {
  it('提交编辑后的完整 desired state，不暴露或生成 write_mode', () => {
    const onSubmit = vi.fn()
    render(<BoundaryMaintenanceEditor draft={draft} busy={false} onSubmit={onSubmit} />)

    expect(screen.getByRole('heading', { name: '调整当前业务边界' })).toBeInTheDocument()
    expect(screen.queryByText(actorId)).not.toBeInTheDocument()
    expect(screen.queryByText(actionId)).not.toBeInTheDocument()
    expect(screen.queryByText(/write_mode/i)).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('业务动作名称'), { target: { value: '导出完整交付包' } })
    fireEvent.click(screen.getByRole('button', { name: '生成待审调整提案' }))

    expect(onSubmit).toHaveBeenCalledOnce()
    const command = onSubmit.mock.calls[0][0]
    expect(command.expected_boundary_state_fingerprint).toBe(draft.boundary_state_fingerprint)
    expect(command.actors[0]).toMatchObject({ actor_id: actorId, expected_current_revision: 2 })
    expect(command.actions[0]).toMatchObject({ action_id: actionId, expected_current_revision: 3, display_name: '导出完整交付包' })
    expect(command.permissions[0]).toMatchObject({ intent_id: intentId, expected_current_revision: 4 })
    expect(JSON.stringify(command)).not.toContain('write_mode')
  })
  it('AI 只显式生成，用户选择填入后仍须单独生成提案', async () => {
    ai.generate.mockResolvedValue(response)
    const onSubmit = vi.fn()
    render(<BoundaryMaintenanceEditor draft={draft} busy={false} onSubmit={onSubmit} />)
    expect(ai.generate).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('权限要求原文'), { target: { value: '负责人不得导出交付包' } })
    fireEvent.click(screen.getByRole('button', { name: 'AI 辅助整理' }))
    expect(await screen.findByText('原文：“负责人不得导出交付包”')).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox', { name: /项目负责人对项目负责人/ }))
    fireEvent.click(screen.getByRole('button', { name: '将选中建议填入草稿' }))
    await waitFor(() => expect(screen.queryByText('待你确认的建议')).not.toBeInTheDocument())
    expect(onSubmit).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '生成待审调整提案' }))
    expect(onSubmit.mock.calls[0][0].permissions[0]).toMatchObject({ intent_id: intentId, expectation: 'DENY', protected_effect_item_ids: ['peff_existing'] })
  })
  it('生成期间修改草稿会丢弃迟到建议，保留手工内容', async () => {
    let resolve!: (value: typeof response) => void
    ai.generate.mockReturnValue(new Promise((done) => { resolve = done }))
    const onSubmit = vi.fn()
    render(<BoundaryMaintenanceEditor draft={draft} busy={false} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText('权限要求原文'), { target: { value: '负责人不得导出交付包' } })
    fireEvent.click(screen.getByRole('button', { name: 'AI 辅助整理' }))
    await waitFor(() => expect(ai.generate).toHaveBeenCalledOnce())
    fireEvent.change(screen.getByLabelText('业务动作名称'), { target: { value: '手工修改的动作' } })
    resolve(response)
    await waitFor(() => expect(screen.getByRole('button', { name: 'AI 辅助整理' })).not.toHaveClass('ant-btn-loading'))
    expect(screen.queryByText('待你确认的建议')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '生成待审调整提案' }))
    expect(onSubmit.mock.calls[0][0].actions[0].display_name).toBe('手工修改的动作')
    expect(onSubmit.mock.calls[0][0].permissions[0].expectation).toBe('ALLOW')
  })
  it('AI 失败不阻止手工提交，正式边界漂移不允许填入建议', async () => {
    ai.generate.mockRejectedValue(new Error('disabled'))
    const onSubmit = vi.fn()
    render(<BoundaryMaintenanceEditor draft={draft} busy={false} onSubmit={onSubmit} />)
    fireEvent.change(screen.getByLabelText('权限要求原文'), { target: { value: '负责人不得导出交付包' } })
    fireEvent.click(screen.getByRole('button', { name: 'AI 辅助整理' }))
    expect(await screen.findByText(/请继续手工填写权限规则/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '生成待审调整提案' }))
    expect(onSubmit).toHaveBeenCalledOnce()
    ai.generate.mockResolvedValue(response)
    fireEvent.click(screen.getByRole('button', { name: 'AI 辅助整理' }))
    fireEvent.click(await screen.findByRole('checkbox', { name: /项目负责人对项目负责人/ }))
    ai.maintenanceDraft.mockResolvedValue({ ...draft, boundary_state_fingerprint: 'changed' })
    fireEvent.click(screen.getByRole('button', { name: '将选中建议填入草稿' }))
    expect(await screen.findByText('业务边界已变化，请刷新后重新整理。')).toBeInTheDocument()
    expect(onSubmit).toHaveBeenCalledOnce()
  })

})
