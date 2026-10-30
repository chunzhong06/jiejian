import {render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {Accounts} from './Accounts';
import {testIdentitiesApi as identities} from '../../../entities/preparation/api/testIdentities';
import {preparationApi} from '../../../entities/preparation/api/preparation';

afterEach(()=>vi.restoreAllMocks());

it('明确返回原登录任务时，不被另一个进行中任务覆盖',async()=>{
    sessionStorage.clear();
    const original={preparation_id:'original',project_id:'app',identity_id:'owner',job_id:'job-old',status:'CANCELLED' as const,message:'本次登录已取消',error_code:null,log_path:'',cleanup_required:false};
    vi.spyOn(identities,'list').mockResolvedValue([]);
    vi.spyOn(identities,'preparations').mockResolvedValue([{...original,preparation_id:'another',status:'WAITING_FOR_LOGIN'}]);
    vi.spyOn(identities,'preparation').mockResolvedValue(original);
    vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[],preparation_complete:false,recommended_action_id:null,basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]});
    render(<Accounts projectId="app" actions={[]} requestedPreparation="original" onBack={()=>{}} onError={()=>{}}/>);
    expect(await screen.findByText('本次登录已取消')).toBeVisible();
    await waitFor(()=>expect(screen.queryByRole('button',{name:'我已完成登录'})).not.toBeInTheDocument());
});
