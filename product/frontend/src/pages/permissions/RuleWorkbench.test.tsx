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

it('从问题进入修复工作面，切换页签不再保留挡住内容的登记表单', async () => {
    const props = { projectId: 'app', official: false, boundary: { policy_epoch: 1 } as BusinessBoundaryViewDto, route: readRoute(), refresh: vi.fn(), onError: vi.fn(), onManage: vi.fn() };
    const view = render(<RuleWorkbench {...props}/>);
    await screen.findByRole('heading', { name: '协作者不得完成工单' });
    fireEvent.click(screen.getByRole('button', { name: '提交修复' }));
    expect(readRoute().query.get('section')).toBe('changes');
    const update = () => view.rerender(<RuleWorkbench {...props} route={readRoute()}/>);
    update();
    const changes = screen.getByRole('tabpanel', { name: '修复与修改' });
    expect(within(changes).getByRole('heading', { name: '登记本地修改' })).toBeVisible();
    expect(screen.queryByRole('heading', { name: '发现的问题' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('修改说明'), { target: { value: '修正协作者的工单权限' } });
    fireEvent.click(screen.getByRole('tab', { name: '检查历史' })); update();
    expect(screen.queryByRole('region', { name: '登记本地修改' })).not.toBeInTheDocument();
    expect(within(screen.getByRole('tabpanel', { name: '检查历史' })).getByRole('heading', { name: '这条规则的检查历史' })).toBeVisible();
    fireEvent.click(screen.getByRole('tab', { name: '修复与修改' })); update();
    expect(screen.getByRole('heading', { name: '关联修改' })).toBeVisible();
    fireEvent.click(screen.getByRole('button', { name: '登记修改' }));
    expect(screen.getByLabelText('修改说明')).toHaveValue('修正协作者的工单权限');
    fireEvent.click(screen.getByRole('button', { name: '返回修改记录' }));
    expect(screen.getByRole('heading', { name: '关联修改' })).toBeVisible();
});
