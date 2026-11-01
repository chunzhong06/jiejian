import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { RuleWorkbench } from './RuleWorkbench';
import { ruleWorkspaceApi, type RuleItem } from '../../entities/permission/api/ruleWorkspace';
import type { BusinessBoundaryViewDto } from '../../entities/permission/api/businessBoundaries';
import { readRoute } from '../../shared/lib/navigation';

const permission = { intent_id: 'rule', revision: 1, intent_hash: 'hash' };
const rule: RuleItem = {
    permission, title: '协作者不得完成工单', expectation: 'DENY', subject: '协作者', action: '完成工单', resource_scope: '主管的资源', state: 'VULNERABLE',
    latest: null, changes: [], history: [{ run_id: 'run', created_at_us: 1000, case_ids: ['case'], verdict: 'VULNERABLE', case_count: 1, current: true, change_id: null }], history_has_more: false,
    issues: [{ task_reference: 'issue', status: 'REPAIR_REQUIRED', change_id: null, run_id: null, verification: null,
        contract: { project_id: 'app', source_run_id: 'run', source_case_id: 'case', repair_fingerprint: 'repair', original_policy_epoch: 1,
            deny: { identity: { action_id: 'action', resource_id: 'resource', subject_test_identity_id: 'member', resource_owner_test_identity_id: 'owner', protected_effect_ids: ['effect'] }, evidence_refs: [] }, regressions: [] } }],
};

beforeEach(() => {
    sessionStorage.clear();
    location.hash = '/permissions?rule_id=rule&project_id=app';
    Element.prototype.scrollIntoView = vi.fn();
    vi.spyOn(ruleWorkspaceApi, 'read').mockResolvedValue({ schema_version: '1', project_id: 'app', policy_epoch: 1, rules: [rule], change_history_limited: false });
});

it('同一角色的多条条件规则分别对应自己的状态和详情，筛选不丢失关系', async () => {
    const rows: RuleItem[] = [
        {...rule, permission:{...permission,intent_id:'archived'}, title:'负责人不得完成工单', subject:'负责人', conditions:{principal:'AUTHENTICATED',tenant:'SAME',resource_states:['archived']},state:'VULNERABLE'},
        {...rule, permission:{...permission,intent_id:'open'}, title:'负责人可以完成工单', subject:'负责人', expectation:'ALLOW',conditions:{principal:'AUTHENTICATED',tenant:'SAME',resource_states:['open']},state:'SAFE'},
    ];
    vi.mocked(ruleWorkspaceApi.read).mockResolvedValue({schema_version:'1',project_id:'app',policy_epoch:1,rules:rows,change_history_limited:false});
    const boundary={policy_epoch:1,actors:[{actor_id:'owner',revision:1,effective_state:'ACTIVE'}],actions:[{action_id:'action',revision:1,effective_state:'ACTIVE'}],permission_intents:rows.map(item=>({...item.permission,subject_actor_id:'owner',subject_actor_revision:1,resource_owner_actor_id:'owner',resource_owner_actor_revision:1,business_action_id:'action',action_revision:1,effective_state:'ACTIVE'}))} as BusinessBoundaryViewDto;
    location.hash='/permissions?project_id=app';
    render(<RuleWorkbench projectId="app" official={false} boundary={boundary} route={readRoute()} refresh={vi.fn()} onError={vi.fn()} onManage={vi.fn()}/>);
    const archived=(await screen.findByText('数据状态：archived')).closest('tr')!;
    expect(within(archived).getByText('负责人不得完成工单')).toBeVisible();
    expect(within(archived).getByText('发现违规')).toBeVisible();
    expect(within(archived).getByRole('link')).toHaveAttribute('href',expect.stringContaining('rule_id=archived'));
    expect(within(archived).getByRole('link')).toHaveAttribute('href',expect.stringContaining('project_id=app'));
    fireEvent.change(screen.getByRole('textbox',{name:'查找规则'}),{target:{value:'open'}});
    expect(screen.queryByText('数据状态：archived')).not.toBeInTheDocument();
    const open=screen.getByText('数据状态：open').closest('tr')!;
    expect(within(open).getByText('符合规则')).toBeVisible();
    expect(within(open).getByRole('link')).toHaveAttribute('href',expect.stringContaining('rule_id=open'));
});

it('从问题进入同一修复任务，登记和返回都保留准确原题', async () => {
    const props = { projectId: 'app', official: false, boundary: { policy_epoch: 1 } as BusinessBoundaryViewDto, route: readRoute(), refresh: vi.fn(), onError: vi.fn(), onManage: vi.fn() };
    const view = render(<RuleWorkbench {...props}/>);
    await screen.findByRole('heading', { name: '协作者不得完成工单' });
    fireEvent.click(screen.getByRole('button', { name: '继续处理问题' }));
    expect(readRoute().query.get('repair_reference')).toBe('repair');
    expect(readRoute().query.get('view')).toBe('repair');
    const update = () => view.rerender(<RuleWorkbench {...props} route={readRoute()}/>);
    update();
    expect(screen.getByRole('heading', {name:'先完成代码修改'})).toBeVisible();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name:'登记已完成的修改'}));
    fireEvent.change(screen.getByLabelText('修改说明'), {target:{value:'修正协作者的工单权限'}});
    fireEvent.click(screen.getByRole('button', {name:'返回修复任务'}));
    fireEvent.click(screen.getByRole('button', {name:'登记已完成的修改'}));
    expect(screen.getByLabelText('修改说明')).toHaveValue('修正协作者的工单权限');
    fireEvent.click(screen.getByRole('button', {name:'返回修复任务'}));
    fireEvent.click(screen.getByRole('button', {name:'返回这条权限规则'})); update();
    fireEvent.click(screen.getByRole('tab', {name:'检查历史'})); update();
    expect(within(screen.getByRole('tabpanel', {name:'检查历史'})).getByRole('heading', {name:'这条规则的检查历史'})).toBeVisible();
    expect(screen.queryByRole('heading', {name:'登记本地修改'})).not.toBeInTheDocument();
});
