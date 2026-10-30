import {fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {Activity} from './Activity';
import {projectsApi} from '../../entities/application/api/projects';

afterEach(()=>vi.restoreAllMocks());

it('没有浏览器本地记录时仍可找回服务端登录，入口保留精确任务位置',async()=>{
    sessionStorage.clear();
    const read=vi.spyOn(projectsApi,'activity').mockResolvedValue({project_id:'app',revision:3,items:[{id:'login',kind:'IDENTITY_PREPARATION',label:'继续账号登录',phase:'WAITING_FOR_LOGIN',destination:'/preparation?identities=1&preparation_id=original',updated_at_us:1}]});
    render(<Activity projectId="app"/>);
    fireEvent.click(await screen.findByRole('button',{name:/^继续账号登录/}));
    expect(location.hash).toContain('preparation_id=original');
    read.mockResolvedValue({project_id:'app',revision:3,items:[]});
    fireEvent(window,new Event('jiejian:activity-changed'));
    await waitFor(()=>expect(screen.queryByRole('button',{name:/^继续账号登录/})).not.toBeInTheDocument());
});

it('中断任务仍能打开原位置，并显示待处理状态',async()=>{
    vi.spyOn(projectsApi,'activity').mockResolvedValue({project_id:'app',revision:3,items:[{id:'failed',kind:'IDENTITY_PREPARATION',label:'查看登录中断',phase:'FAILED',destination:'/preparation?identities=1&preparation_id=failed',updated_at_us:2}]});
    render(<Activity projectId="app"/>);
    const entry=await screen.findByRole('button',{name:/^查看登录中断/});
    fireEvent.click(entry);
    expect(location.hash).toContain('preparation_id=failed');
    expect(within(entry).getByText('未完成')).toBeVisible();
});
