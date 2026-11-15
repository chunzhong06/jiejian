import {fireEvent,render,screen,within} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {ScenarioResults} from './ScenarioResults'
import {EvidenceInspector} from './EvidenceInspector'
import {story} from './Report.fixtures'

function experiment(account:string,role:string,caseId:string){
  const action=story().actions[0]
  action.case_id=caseId;action.display_name='发布资料';action.fact_comparison.resource_id='alpha'
  action.fact_comparison.planned_identity={...action.fact_comparison.planned_identity,label:account,actor_label:role}
  action.scenario_context={scenario_label:'资料发布',experiment_label:'按访问要求发布',invocation_label:'按访问要求发布',experiment_kind:'BASELINE',item_index:1,item_count:1,same_resource_occurrences:1,batch_strategy:null,expected_effect:'PRESENT'}
  return action
}

it('同一资源先辨认操作人和业务，重复实验名称只显示一次且点击保持准确用例',()=>{
  const alice=experiment('alice','负责人','allow-case'),bob=experiment('bob','普通成员','deny-case'),open=vi.fn()
  alice.case_verdict='SAFE';bob.case_verdict='VULNERABLE'
  render(<ScenarioResults actions={[alice,bob]} selected={null} onOpen={open}/>);
  const aliceRow=screen.getByRole('button',{name:'查看负责人 alice · 发布资料，资源alpha的依据'}).closest('tr')!
  expect(within(aliceRow).getByText('符合规则',{exact:true})).toBeVisible()
  expect(within(aliceRow).getAllByText('按访问要求发布')).toHaveLength(1)
  const bobButton=screen.getByRole('button',{name:'查看普通成员 bob · 发布资料，资源alpha的依据'})
  expect(within(bobButton.closest('tr')!).getByText('不符合规则',{exact:true})).toBeVisible()
  fireEvent.click(bobButton);expect(open).toHaveBeenCalledWith('deny-case')
})

it('概览保留实验与批量顺序，详情完整区分实验和执行安排',()=>{
  const action=experiment('alice','负责人','batch-case')
  action.case_verdict='INCONCLUSIVE';action.scenario_context={...action.scenario_context!,experiment_label:'负责人发布本人资料',invocation_label:'检查撤回后的公开状态',item_index:2,item_count:3,batch_strategy:'ATOMIC'}
  const open=vi.fn(),list=render(<ScenarioResults actions={[action]} selected={null} onOpen={open}/>);
  expect(screen.getByText('负责人发布本人资料',{exact:true})).toBeVisible()
  expect(screen.queryByText('检查撤回后的公开状态',{exact:true})).not.toBeInTheDocument()
  expect(screen.getByText('整批原子处理，第 2 / 3 项资源')).toBeVisible()
  expect(screen.getByText('证据不足',{exact:true})).toBeVisible()
  list.rerender(<ScenarioResults actions={[action]} selected={action.case_id} onOpen={open}/>);
  expect(screen.queryByText('负责人发布本人资料',{exact:true})).not.toBeInTheDocument()
  const selected=screen.getByRole('button',{name:'查看负责人 alice · 发布资料，资源alpha，整批原子处理，第 2 / 3 项资源的依据'})
  expect(selected).toHaveAttribute('aria-pressed','true')
  expect(within(selected).getByText('证据不足',{exact:true})).toBeVisible()
  list.unmount()
  const value=story();value.actions=[action]
  render(<EvidenceInspector story={value} action={action} tab="facts" evidenceId={null} recordId={null} onClose={vi.fn()} onLocate={vi.fn()} onError={vi.fn()}/>);
  expect(screen.getByText('负责人发布本人资料',{exact:true})).toBeVisible()
  expect(screen.getByText('检查撤回后的公开状态',{exact:true})).toBeVisible()
})

it('详情沿用相同实验命名，不重复输出相同实验与执行名称',()=>{
  const value=story(),action=experiment('alice','负责人','detail-case');value.actions=[action]
  render(<EvidenceInspector story={value} action={action} tab="facts" evidenceId={null} recordId={null} onClose={vi.fn()} onLocate={vi.fn()} onError={vi.fn()}/>);
  expect(screen.getAllByText('按访问要求发布',{exact:true})).toHaveLength(1)
  expect(screen.getByText('业务实验',{exact:true})).toBeVisible()
  expect(screen.queryByText('执行安排',{exact:true})).not.toBeInTheDocument()
})
