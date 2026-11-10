import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Preparation } from './Preparation';
import { preparationApi } from '../../entities/preparation/api/preparation';
import { preparationBatchesApi as batches } from '../../entities/preparation/api/batches';
import {WorkflowContext} from '../../shared/lib/workflow';

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

it('一键示例入口先展示整批范围确认，刷新读取不自动开始准备',async()=>{
 vi.spyOn(batches,'latest').mockResolvedValue(null)
 vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[],preparation_complete:false} as never)
 const preview=vi.spyOn(batches,'preview').mockResolvedValue({schema_version:'1',project_id:'app',mode:'OFFICIAL',basis_id:'basis',runtime_origin:'http://127.0.0.1:8080',guard:'guard',sources:[]})
 const start=vi.spyOn(batches,'start')
 render(<WorkflowContext.Provider value={{open:vi.fn(),finish:vi.fn(),label:'本次检查'}}><Preparation projectId="app" name="数字展馆" official route={{path:'/preparation',query:new URLSearchParams({prepare_example:'1'})}} refresh={vi.fn()} onError={vi.fn()}/></WorkflowContext.Provider>)
 expect(await screen.findByRole('heading',{name:'为数字展馆准备检查材料'})).toBeVisible()
 expect(preview).toHaveBeenCalledWith('app','OFFICIAL')
 expect(screen.getByRole('button',{name:'允许并开始准备'})).toBeDisabled()
 expect(start).not.toHaveBeenCalled()
})

it('准备响应未知时查询原批次，不重新提交或仅刷新材料清单', async () => {
    sessionStorage.setItem('jiejian.studio.batch:app', 'original');
    const materials = vi.spyOn(preparationApi, 'get').mockResolvedValue({project_id:'app',actions:[],preparation_complete:false,recommended_action_id:null,basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]});
    const read = vi.spyOn(batches, 'status').mockRejectedValueOnce(new Error('连接已中断')).mockResolvedValue({schema_version:'1',project_id:'app',operation_id:'original',state:'CANCELLED',cancel_requested:true,message:'已经停止准备',error_code:null,completed:0,total:1,preflight_id:null,updated_at_us:2});
    const start = vi.spyOn(batches, 'start');
    render(<Preparation projectId="app" name="应用" official={false} route={{path:'/preparation',query:new URLSearchParams()}} refresh={()=>{}} onError={()=>{}}/>);
    fireEvent.click(await screen.findByRole('button', {name:'查询本次准备'}));
    await waitFor(() => expect(read).toHaveBeenCalledTimes(2));
    expect(read.mock.calls.every(call => call[0] === 'app' && call[1] === 'original')).toBe(true);
    expect(await screen.findByText('已经停止准备')).toBeVisible();
    expect(start).not.toHaveBeenCalled();
    expect(materials).toHaveBeenCalledTimes(1);
});

it.each(['action_id=missing','action_id=current&action_revision=1'])('指定操作或修订失效时保留缺失状态，不回退其他操作 %s',async query=>{
    vi.spyOn(batches,'latest').mockResolvedValue(null);
    vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[{action_id:'current',action_revision:2}],preparation_complete:false} as never);
    const finish=vi.fn();
    render(<WorkflowContext.Provider value={{open:vi.fn(),finish,label:'本次检查'}}><Preparation projectId="app" name="应用" official={false} route={{path:'/preparation',query:new URLSearchParams(query)}} refresh={()=>{}} onError={()=>{}}/></WorkflowContext.Provider>);
    expect(await screen.findByText(/指定的业务操作或修订已不在当前准备范围中/)).toBeVisible();
    expect(screen.queryByRole('button',{name:'核对整批材料'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'返回原事项'}));expect(finish).toHaveBeenCalledOnce();
});
