import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { Preparation } from './Preparation';
import { preparationApi } from '../../entities/preparation/api/preparation';
import { preparationBatchesApi as batches } from '../../entities/preparation/api/batches';

afterEach(() => { vi.restoreAllMocks(); sessionStorage.clear(); });

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
