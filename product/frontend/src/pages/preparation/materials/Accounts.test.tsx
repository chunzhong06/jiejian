import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {Accounts} from './Accounts';
import {testIdentitiesApi as identities} from '../../../entities/preparation/api/testIdentities';
import {preparationApi} from '../../../entities/preparation/api/preparation';
import {AccountAuthentication} from './AccountAuthentication';
import type {TestIdentityDto} from '../../../entities/preparation/api/testIdentities';

afterEach(()=>vi.restoreAllMocks());

it.each(['owner',null])('沿用应用登录结构，当前账号编号独立填写，角色模板为 %s',async(role)=>{
    const identity:TestIdentityDto={identity_id:'second',project_id:'app',actor_id:'owner',actor_revision:1,actor_display_name:'负责人',label:'另一个负责人',auth_method:null,status:'NOT_PREPARED',review_reasons:[],cookie_count:0,prepared_at_us:null,refreshed_at_us:null,created_at_us:1,updated_at_us:1,authentication:null,verification:null};
    vi.spyOn(identities,'authenticationOptions').mockResolvedValue({identity_id:'second',templates:[{identity_id:'first',label:'负责人账号',expected_role:role,profile:{method:'BROWSER_SESSION',login_path:'/login',username_field:'name',password_field:'pass',token_path:['access'],verification:{path:'/session/current',subject_path:['account'],role_path:['kind']}}}]});
    const save=vi.spyOn(identities,'configureAuthentication').mockResolvedValue(identity);
    render(<AccountAuthentication identity={identity} onClose={()=>{}} onSaved={()=>{}}/>);
    const subject=await screen.findByLabelText('应用中的账号编号');
    expect(subject).toHaveValue('');
    expect(screen.getByText('/session/current')).toBeVisible();
    expect(screen.getByLabelText('应用中的角色值')).toHaveValue(role??'');
    fireEvent.change(subject,{target:{value:'owner-2'}});
    if(!role){expect(screen.getByRole('button',{name:'保存配置'})).toBeDisabled();fireEvent.change(screen.getByLabelText('应用中的角色值'),{target:{value:'member'}})}
    fireEvent.click(screen.getByRole('button',{name:'保存配置'}));
    await waitFor(()=>expect(save).toHaveBeenCalledWith(identity,expect.objectContaining({login_path:'/login',verification:expect.objectContaining({path:'/session/current',expected_subject:'owner-2',expected_role:role??'member'})})));
});

it('明确返回原登录任务时，不被另一个进行中任务覆盖',async()=>{
    sessionStorage.clear();
    const original={preparation_id:'original',project_id:'app',identity_id:'owner',job_id:'job-old',status:'CANCELLED' as const,message:'本次登录已取消',error_code:null,log_path:'',cleanup_required:false,purpose:'LOGIN' as const};
    vi.spyOn(identities,'list').mockResolvedValue([]);
    vi.spyOn(identities,'preparations').mockResolvedValue([{...original,preparation_id:'another',status:'WAITING_FOR_LOGIN'}]);
    vi.spyOn(identities,'preparation').mockResolvedValue(original);
    vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[],preparation_complete:false,recommended_action_id:null,basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]});
    render(<Accounts projectId="app" actions={[]} requestedPreparation="original" onBack={()=>{}} onError={()=>{}}/>);
    expect(await screen.findByText('本次登录已取消')).toBeVisible();
    await waitFor(()=>expect(screen.queryByRole('button',{name:'我已完成登录'})).not.toBeInTheDocument());
});
