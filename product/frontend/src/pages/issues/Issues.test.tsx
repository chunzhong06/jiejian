import {fireEvent,render,screen,within} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Issues} from './Issues'
import {repairsApi,type ProjectRepair} from '../../entities/check/api/repairs'
import {workbenchApi} from '../../entities/application/api/workbench'
import {ruleWorkspaceApi} from '../../entities/permission/api/ruleWorkspace'
import {sourceChangesApi} from '../../entities/source-change/api/sourceChanges'
import {developmentApi} from '../../entities/source-change/api/development'

const contract={project_id:'app',source_run_id:'run',source_case_id:'case',repair_fingerprint:'fingerprint',original_policy_epoch:1,
  deny:{identity:{action_id:'read',resource_id:'order',subject_test_identity_id:'member',resource_owner_test_identity_id:'owner',protected_effect_ids:[]},evidence_refs:[]},regressions:[]}
function setup(query:string,source=false){
  const tasks:ProjectRepair['tasks']=['VERIFIED','REPAIR_REQUIRED'].map((status,index)=>({task_reference:index?'other':'exact',status:status as 'VERIFIED'|'REPAIR_REQUIRED',contract,change_id:null,run_id:null,verification:null,
    comparison:[{role:'DENY',source_case_id:'case',action_label:index?'其他待处理问题':'指定的已验证问题',subject_label:'成员',resource_owner_label:'所有者',resource_id:'order',effect_labels:[],before_verdict:'VULNERABLE',before_evidence_refs:[],match_status:'NOT_AVAILABLE'}]}))
  vi.spyOn(repairsApi,'project').mockResolvedValue({project_id:'app',status:null,primary_task_reference:null,tasks})
  vi.spyOn(workbenchApi,'environments').mockResolvedValue({project_id:'app',revision:1,environments:[],active_environment:null,confirmed_endpoint:null,endpoint_reachable:null,endpoint_checked_at_us:null,source_available:source})
  if(source)vi.spyOn(ruleWorkspaceApi,'read').mockResolvedValue({project_id:'app',rules:[{permission:{intent_id:'deny',revision:1,intent_hash:'hash'},title:'指定规则',issues:tasks,resource_scope:'所有者的数据'}]} as never)
  return render(<Issues projectId="app" name="订单" official={false} refresh={vi.fn()} onError={vi.fn()} route={{path:'/issues',query:new URLSearchParams(query)}}/>)
}
afterEach(()=>vi.restoreAllMocks())

it('指定的已验证问题优先于默认筛选，不借用其他问题',async()=>{
  setup('issue=exact')
  expect(await screen.findByRole('heading',{name:'指定的已验证问题'})).toBeVisible()
  expect(screen.getByRole('checkbox',{name:'包含已验证修复的问题'})).toBeChecked()
  expect(within(screen.getByRole('navigation',{name:'问题列表'})).getByRole('button',{name:/指定的已验证问题/})).toHaveAttribute('aria-current','true')
  fireEvent.click(screen.getByRole('link',{name:/阅读原问题证据/}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(new URLSearchParams(query.get('return_to')!.split('?')[1]).get('issue')).toBe('exact')
  expect(query.get('case_id')).toBe('case')
})

it('问题处理在当前事项内展开，原题证据回程保留准确问题及视角',async()=>{
  setup('issue=other&section=repair',true)
  expect(await screen.findByRole('button',{name:/登记已完成的修改/})).toBeVisible()
  expect(screen.getAllByRole('heading',{level:1})).toHaveLength(1)
  expect(screen.getByRole('tab',{name:'处理与复验'})).toHaveAttribute('aria-selected','true')
  fireEvent.click(screen.getByRole('link',{name:/查看原问题与证据/}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  const origin=new URLSearchParams(query.get('return_to')!.split('?')[1])
  expect(origin.get('issue')).toBe('other');expect(origin.get('section')).toBe('repair')
  expect(query.get('run_id')).toBe('run');expect(query.get('case_id')).toBe('case')
})

it('失效的准确问题显示缺失状态，并提供主动选择当前问题的入口',async()=>{
  setup('issue=missing')
  expect(await screen.findByText('指定的问题已不在当前问题列表中')).toBeVisible()
  expect(screen.queryByRole('heading',{name:'其他待处理问题'})).not.toBeInTheDocument()
  expect(screen.queryByRole('link',{name:/阅读原问题证据/})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('link',{name:'查看当前问题'}))
  expect(location.hash).not.toContain('issue=missing')
})

it('登记修改后提示核对复验条件，缺少运行交付时仍不能开始复验',async()=>{
  vi.spyOn(sourceChangesApi,'show').mockResolvedValue({manifest:{project_id:'app',created_at_us:1,reason:'核对订单权限',repair_reference:{repair_fingerprint:'fingerprint'}},change_set:{modified_paths:['api/orders.mjs'],added_paths:[],removed_paths:[]},revalidation:{preparation_gaps:[]}} as never)
  vi.spyOn(developmentApi,'details').mockResolvedValue(null)
  setup('issue=other&section=repair&change_id=change',true)
  expect(await screen.findByRole('heading',{name:'已登记的修改'})).toBeVisible()
  const progress=screen.getByRole('list',{name:'修复流程'})
  expect(within(progress).getByText('核对复验条件').closest('li')).toHaveAttribute('aria-current','step')
  expect(screen.getByText('这次修改缺少可读取的运行交付，请核对修改记录。')).toBeVisible()
  expect(screen.queryByRole('button',{name:/核对原问题复验范围/})).not.toBeInTheDocument()
})
