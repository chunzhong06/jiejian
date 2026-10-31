import {fireEvent,render,screen,within,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {Plan} from './CheckPlan'
import {currentChecksApi} from '../../entities/check/api/currentChecks'
import {workspaceApi} from '../../entities/workspace/api/workspace'
import {preparationApi} from '../../entities/preparation/api/preparation'
import {testIdentitiesApi} from '../../entities/preparation/api/testIdentities'

const props=()=>({projectId:'app',name:'展馆',official:false,route:{path:'/reports',query:new URLSearchParams('view=plan')},onError:vi.fn(),refresh:vi.fn()})
beforeEach(()=>{
  vi.spyOn(testIdentitiesApi,'list').mockResolvedValue([])
  vi.spyOn(workspaceApi,'current').mockResolvedValue({project:{project_id:'app'},actions:[]} as never)
  vi.spyOn(preparationApi,'get').mockResolvedValue({project_id:'app',actions:['下载','预览'].map((display_name,index)=>({action_id:'action'+index,display_name,identity_requirements:{slots:[]},effect_evidence:[]}))} as never)
  vi.spyOn(currentChecksApi,'preview').mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:2,case_count:0,actions:[],gaps:[0,0,1].map(index=>({action_id:'action'+index,reason:'TEST_IDENTITY_REQUIRED'}))} as never)
})
it('同类缺口保留所属操作，处理入口携带返回检查的上下文',async()=>{
  render(<Plan {...props()}/>);
  const action=(await screen.findByRole('heading',{name:'下载'})).closest('article')!
  expect(screen.getAllByText('测试账号尚未就绪')).toHaveLength(2)
  expect(workspaceApi.current).not.toHaveBeenCalled()
  fireEvent.click(within(action).getByRole('button',{name:'准备测试账号'}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(query.get('action_id')).toBe('action0')
  expect(query.get('focus')).toBe('identity')
  expect(query.get('return_to')).toContain('/reports?view=plan')
})

it('同一操作的证明缺口合并到一个明确入口，保留原因与结果定位',async()=>{
  vi.mocked(currentChecksApi.preview).mockResolvedValue({project_id:'app',can_execute:false,plan_fingerprint:'basis',action_count:1,case_count:0,actions:[],gaps:[
    {action_id:'action0',reason:'EFFECT_VERDICT_PROOF_REQUIRED',intent_id:'deny',effect_id:'effect'},
    {action_id:'action0',reason:'EFFECT_VERDICT_PROOF_REQUIRED',intent_id:'allow',effect_id:'effect'},
    {action_id:'action0',reason:'REGISTERED_OBSERVER_UNAVAILABLE'},
  ]} as never)
  render(<Plan {...props()}/>);
  const action=(await screen.findByRole('heading',{name:'下载'})).closest('article')!
  expect(within(action).getByText('业务结果缺少有效证明')).toBeVisible()
  expect(within(action).getByText('证明来源当前不可用')).toBeVisible()
  fireEvent.click(within(action).getByRole('button',{name:'核对证明来源'}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(query.get('focus')).toBe('evidence')
  expect(query.get('action_id')).toBe('action0')
  expect(query.get('effect_id')).toBe('effect')
})
it('原范围不可执行时仍可只读找回已经提交的检查',async()=>{
  sessionStorage.setItem('jiejian.studio.check:app',JSON.stringify({fingerprint:'old',operation:'op',change:null}))
  const receipt=vi.spyOn(currentChecksApi,'receipt').mockResolvedValue({run:{project_id:'app',run_id:'original'}} as never)
  const submit=vi.spyOn(currentChecksApi,'submit')
  render(<Plan {...props()}/>);
  fireEvent.click(await screen.findByRole('button',{name:'查询原检查'}))
  await waitFor(()=>expect(new URLSearchParams(location.hash.split('?')[1]).get('run_id')).toBe('original'))
  expect(receipt).toHaveBeenCalledWith('app','op')
  expect(submit).not.toHaveBeenCalled()
})
