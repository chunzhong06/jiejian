import {fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Accounts} from './Accounts'
import {testIdentitiesApi as api,type TestIdentityDto} from '../../../entities/preparation/api/testIdentities'
import {preparationApi,type ActionPreparation} from '../../../entities/preparation/api/preparation'

afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})

it('连接变化时明确重新登录，不把检查旧会话作为可用的推进动作',async()=>{
 const identity:TestIdentityDto={identity_id:'owner-login',project_id:'app',actor_id:'owner',actor_revision:1,actor_display_name:'负责人',label:'负责人',status:'NEEDS_REVIEW',review_reasons:['IDENTITY_ENVIRONMENT_CHANGED'],auth_method:'COOKIE_SESSION',cookie_count:1,prepared_at_us:1,refreshed_at_us:1,created_at_us:1,updated_at_us:1,authentication:{method:'BROWSER_SESSION',login_path:'/login',username_field:'username',password_field:'password',token_path:['token'],verification:{path:'/api/me',subject_path:['id'],role_path:['role'],expected_subject:'owner-1',expected_role:'owner'}},verification:null}
 const action={action_id:'download',display_name:'下载资料',identity_requirements:{slots:[{requirement:{slot_id:'owner-slot',actor_id:'owner',actor_revision:1,ordinal:1},actor_display_name:'负责人',test_identity_id:identity.identity_id}]}} as ActionPreparation
 vi.spyOn(api,'list').mockResolvedValue([identity]);vi.spyOn(api,'preparations').mockResolvedValue([])
 vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:[action]} as never)
 const start=vi.spyOn(api,'startPreparation')
 render(<Accounts projectId="app" actions={[action]} onBack={vi.fn()} onError={vi.fn()}/>)
 expect(await screen.findByText('已有登录属于原连接。请重新登录此账号，使其对应当前连接。')).toBeVisible()
 expect(screen.getByRole('button',{name:'检查登录是否有效'})).toBeDisabled()
 fireEvent.click(screen.getByRole('button',{name:'重新登录此账号'}))
 expect(await screen.findByRole('dialog',{name:'重新准备这个账号'})).toBeVisible()
 expect(start).not.toHaveBeenCalled()
})
