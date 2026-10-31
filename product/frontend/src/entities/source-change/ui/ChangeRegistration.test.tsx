import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { ChangeRegistration } from './ChangeRegistration';
import { sourceChangesApi } from '../api/sourceChanges';
import { developmentApi } from '../api/development';

beforeEach(() => sessionStorage.clear());
const options = ['p1', 'p2'].map(id => ({ key: JSON.stringify([{intent_id:id,revision:1,intent_hash:id},null]),
    title: id === 'p1' ? '成员不得完成工单' : '主管可以完成工单', scope: '主管的资源', problem: false,
    target: { permission: { intent_id: id, revision: 1, intent_hash: id }, repair: null } }));

it('多目标登记丢失响应后，跨入口查询原操作，不重复登记', async () => {
    const preview = vi.spyOn(sourceChangesApi, 'registrationPreview').mockResolvedValue({project_id:'app', fingerprint:'preview', source_fingerprint:'source', policy_epoch:1, permission_count:2, files:[{path:'policy.mjs',status:'MODIFIED'}]});
    const register = vi.spyOn(sourceChangesApi, 'register').mockRejectedValue(new Error('response lost'));
    const saved = vi.fn(), onError = vi.fn();
    const props = { projectId:'app', options, onClose:vi.fn(), onSaved:saved, onError };
    const view = render(<ChangeRegistration {...props}/>);
    fireEvent.change(screen.getByLabelText('修改说明'), {target:{value:'恢复主管权限，限制成员操作'}});
    for (const checkbox of screen.getAllByRole('checkbox')) fireEvent.click(checkbox);
    fireEvent.click(screen.getByRole('button',{name:'预览文件变化'}));
    await screen.findByText('policy.mjs');
    fireEvent.click(screen.getByRole('button',{name:'确认登记修改'}));
    await waitFor(() => expect(onError).toHaveBeenCalled());
    const payload = register.mock.calls[0][1];
    expect(payload.rule_targets).toEqual(options.map(option => option.target));
    expect(payload.expected_registration_fingerprint).toBe('preview');
    view.unmount();
    vi.spyOn(developmentApi,'receipt').mockResolvedValue({project_id:'app', kind:'DELIVER',operation_id:payload.operation_id,status:'SUCCEEDED',task_id:'task',task_version:1,context_id:'context',delivery_id:'delivery',change_id:'change'});
    render(<ChangeRegistration {...props}/>);
    fireEvent.click(screen.getByRole('button',{name:'查询登记结果'}));
    await waitFor(() => expect(saved).toHaveBeenCalledWith('change'));
    expect(developmentApi.receipt).toHaveBeenCalledWith('app','DELIVER',payload.operation_id);
    expect(register).toHaveBeenCalledTimes(1);
    expect(preview).toHaveBeenCalledTimes(1);
});
