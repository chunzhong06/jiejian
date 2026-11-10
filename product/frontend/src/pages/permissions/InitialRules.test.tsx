import {discardProjectEditorDrafts} from '../../entities/runtime/model/handoff'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { InitialRules } from './InitialRules';
import { RuleEditor } from './RuleEditor';
import { prefixedId } from '../../shared/lib/id';
import { businessBoundariesApi as api, type BoundaryMaintenanceCommandDto, type BoundaryMaintenanceDraftDto } from '../../entities/permission/api/businessBoundaries';

const draft: BoundaryMaintenanceCommandDto = {
    expected_boundary_state_fingerprint: 'basis', provenance: '负责人可完成自己的工单。',
    actors: [{ item_id: 'owner', display_name: '负责人', description: '管理自己的工单', effective_state: 'ACTIVE' }],
    actions: [{ item_id: 'finish', display_name: '完成工单', description: '标记工单已完成', primary_resource_concept: '工单', operation_kind: 'CHANGE', state_changing: true, effective_state: 'ACTIVE', effects: [{ item_id: 'done', business_label: '工单已完成', effect_kind: 'STATE_MUTATION', resource_concept: '工单', description: '业务记录状态为完成' }] }],
    permissions: [{ item_id: 'allow-owner', subject_actor_item_id: 'owner', business_action_item_id: 'finish', resource_owner_actor_item_id: 'owner', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: ['done'], effective_state: 'ACTIVE' }],
};
const basis: BoundaryMaintenanceDraftDto = { project_id: 'app', boundary_state_fingerprint: 'basis', actors: [], actions: [], permissions: [], candidate_options: [], implementation_inspections: [] };

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear();discardProjectEditorDrafts('app'); });

it('草稿编号保留前缀及既有的16位UUID后缀，只取一次随机值',()=>{
    const random=vi.spyOn(crypto,'randomUUID').mockReturnValue('01234567-89ab-4cde-8fab-0123456789ab');
    expect(prefixedId('pactn_')).toBe('pactn_0123456789ab4cde');
    expect(random).toHaveBeenCalledOnce();
});

it('规则条件切换编辑保留各自草稿，只有生成提案才提交对应规则的修改', async () => {
    const second = {...draft.permissions[0], item_id:'deny-owner', expectation:'DENY' as const};
    vi.spyOn(api,'maintenanceDraft').mockResolvedValue({...basis, actors:draft.actors, actions:draft.actions, permissions:[draft.permissions[0],second]});
    const create = vi.spyOn(api,'createMaintenanceProposal').mockResolvedValue({proposal:{project_id:'app',proposal_id:'proposal'}} as never);
    render(<RuleEditor projectId="app" onBack={vi.fn()} onProposal={vi.fn().mockResolvedValue(undefined)} onError={vi.fn()}/>);
    const editors = await screen.findAllByRole('button',{name:/^编辑.*的适用条件$/});
    fireEvent.click(editors[0]);
    const states = screen.getByLabelText('仅检查这些数据状态（选填）');
    fireEvent.change(states,{target:{value:'OPEN、OPEN'}});
    fireEvent.blur(states);
    fireEvent.click(editors[1]);
    expect(screen.getByLabelText('仅检查这些数据状态（选填）')).toHaveValue('');
    expect(screen.getAllByRole('region',{name:/的适用条件$/})).toHaveLength(1);
    fireEvent.click(screen.getAllByRole('button',{name:/^编辑.*的适用条件$/})[0]);
    expect(screen.getByLabelText('仅检查这些数据状态（选填）')).toHaveValue('OPEN');
    expect(create).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText('变更理由'),{target:{value:'只检查开放中的工单'}});
    fireEvent.click(screen.getByRole('button',{name:'生成待审变更'}));
    await waitFor(()=>expect(create).toHaveBeenCalledTimes(1));
    const submitted = create.mock.calls[0][1];
    expect(submitted.permissions[0].conditions?.resource_states).toEqual(['OPEN']);
    expect(submitted.permissions[1].conditions).toBeUndefined();
});

it('空白草稿先填写当前分区，尚无规则时不展示空预览和提交操作', () => {
    const create = vi.spyOn(api, 'createMaintenanceProposal');
    render(<InitialRules projectId="app" basis={basis} onBack={() => {}} onProposal={vi.fn()} onError={vi.fn()} />);
    expect(screen.queryByRole('button', { name: '生成完整提案' })).not.toBeInTheDocument();
    expect(screen.queryByRole('complementary', {name:'权限草稿预览'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('tab', { name: /^操作与结果/ }));
    expect(screen.getByRole('tab', { name: /^操作与结果/ })).toHaveAttribute('aria-selected', 'true');
    expect(create).not.toHaveBeenCalled();
});

it('创建操作属于操作集合，创建结果只修改所在操作，跨分区仍保留归属', () => {
    const second={...structuredClone(draft.actions[0]),item_id:'archive',display_name:'归档工单',effects:[{...structuredClone(draft.actions[0].effects[0]),item_id:'archived',business_label:'工单已归档'}]};
    sessionStorage.setItem('jiejian.studio.initial-rules:app',JSON.stringify({...draft,actions:[draft.actions[0],second]}));
    const create=vi.spyOn(api,'createMaintenanceProposal');
    render(<InitialRules projectId="app" basis={basis} onBack={()=>{}} onProposal={vi.fn()} onError={vi.fn()}/>);
    fireEvent.click(screen.getByRole('tab',{name:'操作与结果 2'}));
    const collection=within(screen.getByRole('region',{name:'业务操作'}));
    expect(collection.getByRole('heading',{name:'业务操作',level:2})).toBeVisible();
    const results=within(screen.getByRole('region',{name:'业务操作 1的业务结果'}));
    expect(results.getByRole('heading',{name:'业务结果',level:3})).toBeVisible();
    fireEvent.click(results.getByRole('button',{name:'添加结果'}));
    expect(results.getAllByLabelText('结果名称')).toHaveLength(2);
    expect(within(screen.getByRole('region',{name:'业务操作 2的业务结果'})).getAllByLabelText('结果名称')).toHaveLength(1);
    fireEvent.click(collection.getByRole('button',{name:'添加操作'}));
    expect(collection.getAllByRole('article')).toHaveLength(3);
    fireEvent.click(screen.getByRole('tab',{name:'业务角色 1'}));
    fireEvent.click(screen.getByRole('tab',{name:'操作与结果 3'}));
    expect(within(screen.getByRole('article',{name:'业务操作 2'})).getByLabelText('结果名称')).toHaveValue('工单已归档');
    expect(create).not.toHaveBeenCalled();
});

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

it('只填写权限含义即可生成提案，说明与来源补充保持选填', async () => {
    const minimal={...draft,provenance:'',actors:draft.actors.map(actor=>({...actor,description:''})),actions:draft.actions.map(action=>({...action,description:'',effects:action.effects.map(effect=>({...effect,description:''}))}))};
    sessionStorage.setItem('jiejian.studio.initial-rules:app',JSON.stringify(minimal));
    const create=vi.spyOn(api,'createMaintenanceProposal').mockResolvedValue({proposal:{proposal_id:'minimal'}} as never);
    const opened=vi.fn().mockResolvedValue(undefined);
    render(<InitialRules projectId="app" basis={basis} onBack={()=>{}} onProposal={opened} onError={vi.fn()}/>);
    fireEvent.click(screen.getByRole('button',{name:'生成完整提案'}));
    await waitFor(()=>expect(opened).toHaveBeenCalledWith('minimal'));
    const submitted=create.mock.calls[0][1];
    expect(submitted).not.toHaveProperty('provenance');
    expect(submitted.actors[0].description).toBe('');
    expect(submitted.permissions[0].protected_effect_item_ids).toEqual(['done']);
});
