import {fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {PreparationNext} from './PreparationNext'
import {taskDestination} from './taskDestination'
import {workspaceApi,type PrimaryTaskDto} from './api/workspace'
import type {CheckPreview} from '../check/api/currentChecks'
import {WorkflowContext} from '../../shared/lib/workflow'

afterEach(()=>vi.restoreAllMocks())
const task=(values:Partial<PrimaryTaskDto>)=>({task_kind:'PREPARE_TEST_IDENTITY',business_action_id:'read',title:'准备成员账号',user_responsibility:'登录本次检查所需的成员账号。',action_label:'准备账号',...values} as PrimaryTaskDto)

it('下一步仅请求本次动作，账号槽位与修订准确传入原工作面',async()=>{
 const read=vi.spyOn(workspaceApi,'preparation').mockResolvedValue({project_id:'app',actions:[],preparation_complete:false,primary_task:task({action_revision:3,identity_slot_id:'member-2'})})
 const open=vi.fn()
 render(<WorkflowContext.Provider value={{open,finish:vi.fn(),label:'本次检查'}}><PreparationNext preview={{project_id:'app',actions:[{action_id:'read'}],gaps:[{action_id:'read'}]} as CheckPreview} onReview={vi.fn()}/></WorkflowContext.Provider>)
 fireEvent.click(await screen.findByRole('button',{name:'准备账号'}))
 expect(read.mock.calls[0].slice(0,2)).toEqual(['app',['read']])
 const query=new URLSearchParams(open.mock.calls[0][0].split('?')[1])
 expect(query.get('account_slot')).toBe('member-2');expect(query.get('action_revision')).toBe('3')
})

it('没有材料任务时仍可就地核对权限缺口，不留下无动作的页尾',async()=>{
 const onReview=vi.fn()
 render(<PreparationNext preview={{project_id:'app',actions:[],gaps:[]} as unknown as CheckPreview} onReview={onReview}/>)
 fireEvent.click(screen.getByRole('button',{name:'核对待准备事项'}));expect(onReview).toHaveBeenCalledOnce()
})

it('录制、资源和原问题任务携带各自对象，不借用其他对象',()=>{
 let query=new URLSearchParams(taskDestination(task({task_kind:'REVIEW_RECORDING',recording_id:'capture',recording_purpose:'OBSERVATION',effect_id:'effect'})).split('?')[1])
 expect(query.get('recording_id')).toBe('capture');expect(query.get('material_kind')).toBe('evidence');expect(query.get('member_id')).toBe('effect')
 query=new URLSearchParams(taskDestination(task({task_kind:'PREPARE_ACTION_RESOURCE',resource_owner_test_identity_id:'owner'})).split('?')[1])
 expect(query.get('member_id')).toBe('owner')
 query=new URLSearchParams(taskDestination(task({task_kind:'VERIFY_REPAIR',change_id:'change',repair_fingerprint:'original'})).split('?')[1])
 expect(query.get('change_id')).toBe('change');expect(query.get('repair_reference')).toBe('original')
 expect(taskDestination(task({task_kind:'SELECT_ALLOW_CONTROL',route:'/permissions'}))).toMatch(/^\/permissions\?/)
})
