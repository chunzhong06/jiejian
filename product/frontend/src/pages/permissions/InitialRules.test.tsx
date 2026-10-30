import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { InitialRules } from './InitialRules';
import { businessBoundariesApi as api, type BoundaryMaintenanceCommandDto, type BoundaryMaintenanceDraftDto } from '../../entities/permission/api/businessBoundaries';

const draft: BoundaryMaintenanceCommandDto = {
    expected_boundary_state_fingerprint: 'basis', provenance: '负责人可完成自己的工单。',
    actors: [{ item_id: 'owner', display_name: '负责人', description: '管理自己的工单', effective_state: 'ACTIVE' }],
    actions: [{ item_id: 'finish', display_name: '完成工单', description: '标记工单已完成', primary_resource_concept: '工单', operation_kind: 'CHANGE', state_changing: true, effective_state: 'ACTIVE', effects: [{ item_id: 'done', business_label: '工单已完成', effect_kind: 'STATE_MUTATION', resource_concept: '工单', description: '业务记录状态为完成' }] }],
    permissions: [{ item_id: 'allow-owner', subject_actor_item_id: 'owner', business_action_item_id: 'finish', resource_owner_actor_item_id: 'owner', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: ['done'], effective_state: 'ACTIVE' }],
};
const basis: BoundaryMaintenanceDraftDto = { project_id: 'app', boundary_state_fingerprint: 'basis', actors: [], actions: [], permissions: [], candidate_options: [], implementation_inspections: [] };

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

it('跨分区编辑保留输入，预览随草稿更新，只有明确提交才创建完整提案', async () => {
    sessionStorage.setItem('jiejian.studio.initial-rules:app', JSON.stringify(draft));
    const create = vi.spyOn(api, 'createMaintenanceProposal').mockResolvedValue({ proposal: { proposal_id: 'proposal' } } as never);
    const opened = vi.fn().mockResolvedValue(undefined);
    render(<InitialRules projectId="app" basis={basis} onBack={() => {}} onProposal={opened} onError={vi.fn()} />);
    fireEvent.change(screen.getByLabelText('角色名称'), { target: { value: '主管' } });
    expect(within(screen.getByRole('complementary', { name: '权限草稿预览' })).getByText('主管可以完成工单')).toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: '操作与结果 1' }));
    expect(screen.getByLabelText('操作名称')).toHaveValue('完成工单');
    fireEvent.click(screen.getByRole('tab', { name: '访问规则 1' }));
    expect(screen.getByLabelText('权限要求的依据')).toHaveValue(draft.provenance);
    fireEvent.click(screen.getByRole('tab', { name: '业务角色 1' }));
    expect(screen.getByLabelText('角色名称')).toHaveValue('主管');
    expect(create).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '生成完整提案' }));
    await waitFor(() => expect(opened).toHaveBeenCalledWith('proposal'));
    expect(create).toHaveBeenCalledExactlyOnceWith('app', { ...draft, actors: [{ ...draft.actors[0], display_name: '主管' }] });
});

it('提案回执未知时保留草稿并阻止切换分区后重复提交', async () => {
    sessionStorage.setItem('jiejian.studio.initial-rules:app', JSON.stringify(draft));
    const create = vi.spyOn(api, 'createMaintenanceProposal').mockRejectedValue(new Error('响应中断'));
    render(<InitialRules projectId="app" basis={basis} onBack={() => {}} onProposal={vi.fn()} onError={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '生成完整提案' }));
    expect(await screen.findByText('提案结果尚未确认，草稿已保留。')).toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: '访问规则 1' }));
    expect(screen.getByRole('button', { name: '生成完整提案' })).toBeDisabled();
    expect(screen.getByLabelText('权限要求的依据')).toHaveValue(draft.provenance);
    expect(screen.getByRole('button', { name: '查询已接收的提案' })).toBeEnabled();
    expect(create).toHaveBeenCalledTimes(1);
});
