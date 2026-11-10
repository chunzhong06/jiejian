import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {Accounts} from './Accounts';
import {testIdentitiesApi as identities} from '../../../entities/preparation/api/testIdentities';
import {preparationApi,type ActionPreparation} from '../../../entities/preparation/api/preparation';
import {AccountAuthentication} from './AccountAuthentication';
import type {TestIdentityDto} from '../../../entities/preparation/api/testIdentities';
import {WorkflowContext} from '../../../shared/lib/workflow';

afterEach(()=>vi.restoreAllMocks());

it('本次检查补账号只显示范围内操作，刷新读取不会带入其他操作的账号需求',async()=>{
    const action=(id:string):ActionPreparation=>({action_id:id,action_revision:1,display_name:id,preparation_complete:false,next_material:'identity',permissions:[],assurance_contract:{allow_controls:[]},identity_requirements:{status:'NEEDS_USER',reason_codes:[],allocation_mode:'ROLE',slots:[{requirement:{slot_id:id,actor_id:id,actor_revision:1,ordinal:1},actor_display_name:id==='read'?'成员':'无关角色',test_identity_id:null,status:'NEEDS_USER',reason_codes:[]}]},execution:{status:'NEEDS_USER',reason_codes:[]},resources:[],effect_evidence:[],recovery:{status:'NOT_REQUIRED',reason_codes:[]},reason_codes:[]});
    const selected=action('read');
    vi.spyOn(identities,'list').mockResolvedValue([]);vi.spyOn(identities,'preparations').mockResolvedValue([]);
    vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[selected,action('other')],preparation_complete:false,recommended_action_id:'other',basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]});
    render(<WorkflowContext.Provider value={{open:vi.fn(),finish:vi.fn(),label:'本次检查'}}><Accounts projectId="app" actions={[selected]} onBack={vi.fn()} onError={vi.fn()}/></WorkflowContext.Provider>);
    expect(await screen.findByRole('heading',{name:'成员账号'})).toBeVisible();
    expect(screen.queryByRole('button',{name:/无关角色/})).not.toBeInTheDocument();
});

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

it.each(['member-slot','missing-slot'])('按被点击的账号需求定位，不悄悄换成另一个账号：%s',async(requestedSlot)=>{
    sessionStorage.clear();
    const action:ActionPreparation={action_id:'edit',action_revision:1,display_name:'更新工单',preparation_complete:false,next_material:'identity',permissions:[],assurance_contract:{allow_controls:[]},identity_requirements:{status:'NEEDS_USER',reason_codes:[],allocation_mode:'ROLE',slots:[
        {requirement:{slot_id:'owner-slot',actor_id:'owner',actor_revision:1,ordinal:1},actor_display_name:'负责人',test_identity_id:null,status:'NEEDS_USER',reason_codes:[]},
        {requirement:{slot_id:'member-slot',actor_id:'member',actor_revision:1,ordinal:1},actor_display_name:'成员',test_identity_id:null,status:'NEEDS_USER',reason_codes:[]},
    ]},execution:{status:'NEEDS_USER',reason_codes:[]},resources:[],effect_evidence:[],recovery:{status:'NOT_REQUIRED',reason_codes:[]},reason_codes:[]};
    vi.spyOn(identities,'list').mockResolvedValue([]);
    vi.spyOn(identities,'preparations').mockResolvedValue([]);
    vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[action],preparation_complete:false,recommended_action_id:'edit',basis_fingerprint:null,policy_epoch:1,source_fingerprint:null,impacts:[]});
    render(<Accounts projectId="app" actions={[action]} requestedSlot={requestedSlot} onBack={()=>{}} onError={()=>{}}/>);
    if(requestedSlot==='member-slot')expect(await screen.findByRole('heading',{name:'成员账号'})).toBeVisible();
    else expect(await screen.findByText('这项账号需求已发生变化，请返回材料清单重新选择。')).toBeVisible();
    expect(screen.queryByRole('heading',{name:'负责人账号'})).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:/负责人账号/}));
    expect(await screen.findByRole('heading',{name:'负责人账号'})).toBeVisible();
});
