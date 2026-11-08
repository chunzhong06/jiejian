import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {RoutineHandoff} from './RoutineHandoff'
import {collaborationApi} from '../../runtime/api/collaboration'

beforeEach(()=>sessionStorage.clear())
afterEach(()=>vi.restoreAllMocks())

it('交接回执未知后重新打开，保持原方案、绑定、返回位置和请求身份',async()=>{
 const document={routine_id:'csp_'+'1'.repeat(32),revision:2,name:'订单方案'},reference={routine_id:document.routine_id,revision:2,binding_id:'crb_'+'2'.repeat(32)}
 const create=vi.spyOn(collaborationApi,'create').mockRejectedValueOnce(new Error('连接中断')).mockResolvedValueOnce({project_id:'handoff-ui',task_id:'ctk_'+'3'.repeat(32)} as never)
 const props={projectId:'handoff-ui',document:document as never,reference,origin:'/testing?view=plans&routine_id='+document.routine_id+'&routine_revision=2',onClose:vi.fn()}
 const first=render(<RoutineHandoff {...props}/>)
 fireEvent.click(screen.getByRole('button',{name:'建立协作任务'}))
 const retry=await screen.findByRole('button',{name:'核对原交接请求'})
 await waitFor(()=>expect(retry).not.toBeDisabled())
 first.unmount();render(<RoutineHandoff {...props} origin="/reports?run_id=changed-context"/>)
 fireEvent.click(screen.getByRole('button',{name:'核对原交接请求'}))
 await waitFor(()=>expect(create).toHaveBeenCalledTimes(2))
 expect(create.mock.calls[1]).toEqual(create.mock.calls[0])
 expect(create.mock.calls[0][3]).toEqual({routine_id:document.routine_id,routine_revision:'2',binding_id:reference.binding_id,return_to:props.origin})
})
