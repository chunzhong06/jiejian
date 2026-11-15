import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {AccountAuthentication} from './AccountAuthentication'
import {testIdentitiesApi as api,type TestIdentityDto} from '../../../entities/preparation/api/testIdentities'
import {discardProjectEditorDrafts} from '../../../entities/runtime/model/handoff'

const identity:TestIdentityDto={identity_id:'authentication-draft',project_id:'auth-task',actor_id:'owner',actor_revision:1,actor_display_name:'负责人',label:'测试负责人',auth_method:null,status:'NOT_PREPARED',review_reasons:[],cookie_count:0,prepared_at_us:null,refreshed_at_us:null,created_at_us:1,updated_at_us:1,verification:null,authentication:{method:'BROWSER_SESSION',login_path:'/login',username_field:'username',password_field:'password',token_path:['token'],verification:{path:'/api/me',subject_path:['id'],role_path:['role'],expected_subject:'owner-1',expected_role:'owner'}}}
beforeEach(()=>{discardProjectEditorDrafts(identity.project_id);vi.spyOn(api,'authenticationOptions').mockResolvedValue({identity_id:identity.identity_id,templates:[]})})
afterEach(()=>vi.restoreAllMocks())

it('返回保留当前修订草稿，取消明确丢弃，其他修订重新读取保存值',async()=>{
 const close=vi.fn(),props={identity,onClose:close,onSaved:vi.fn()}
 const view=render(<AccountAuthentication {...props}/>)
 fireEvent.change(await screen.findByLabelText('应用中的账号编号'),{target:{value:'owner-edited'}})
 fireEvent.click(screen.getByRole('button',{name:'返回账号核对'}));expect(close).toHaveBeenCalledOnce();view.unmount()
 const restored=render(<AccountAuthentication {...props}/>)
 expect(await screen.findByLabelText('应用中的账号编号')).toHaveValue('owner-edited')
 fireEvent.click(screen.getByRole('button',{name:'取消'}));restored.unmount()
 const cancelled=render(<AccountAuthentication {...props}/>)
 expect(await screen.findByLabelText('应用中的账号编号')).toHaveValue('owner-1')
 fireEvent.change(screen.getByLabelText('应用中的账号编号'),{target:{value:'old-revision'}});cancelled.unmount()
 render(<AccountAuthentication {...props} identity={{...identity,updated_at_us:2}}/>)
 expect(await screen.findByLabelText('应用中的账号编号')).toHaveValue('owner-1')
})

it('保存中阻止离开和修改，失败保留输入供修正',async()=>{
 let reject!:(error:Error)=>void
 const save=vi.spyOn(api,'configureAuthentication').mockImplementation(()=>new Promise((_resolve,rejection)=>{reject=rejection}))
 const close=vi.fn(),saved=vi.fn()
 render(<AccountAuthentication identity={identity} onClose={close} onSaved={saved}/>)
 fireEvent.change(await screen.findByLabelText('应用中的账号编号'),{target:{value:'owner-edited'}})
 fireEvent.click(screen.getByRole('button',{name:'保存配置'}))
 expect(screen.getByRole('button',{name:'返回账号核对'})).toBeDisabled()
 expect(screen.getByLabelText('应用中的账号编号')).toBeDisabled()
 reject(new Error('账号设置已有变化，请重新核对'))
 expect(await screen.findByRole('alert')).toHaveTextContent('账号设置已有变化')
 expect(screen.getByLabelText('应用中的账号编号')).toHaveValue('owner-edited')
 expect(close).not.toHaveBeenCalled();expect(saved).not.toHaveBeenCalled()
 await waitFor(()=>expect(screen.getByRole('button',{name:'保存配置'})).toBeEnabled())
 expect(save).toHaveBeenCalledWith(identity,expect.objectContaining({verification:expect.objectContaining({expected_subject:'owner-edited'})}))
})
