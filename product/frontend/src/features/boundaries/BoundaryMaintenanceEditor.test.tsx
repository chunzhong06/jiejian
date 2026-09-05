// 验证维护编辑器保留 stable identity，并只把 desired state 交给服务端决策。

import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { BoundaryMaintenanceDraftDto } from '../../api/businessBoundaries'
import { BoundaryMaintenanceEditor } from './BoundaryMaintenanceEditor'

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
})
