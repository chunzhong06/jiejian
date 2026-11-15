import {story as resultStory} from './Report.fixtures'
import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {SampleCoverage} from './SampleCoverage'
import type {ResultStory} from '../../../entities/check/api/currentChecks'

const story={project_id:'app',run_id:'original',actions:[],sample_coverage:[{
  permission:{intent_id:'rule',revision:2,intent_hash:'frozen'},applicable_states:['已批准','待领取'],
  observed_states:['已批准'],concluded_states:['已批准'],unchecked_states:['待领取'],unknown_case_ids:[],
  samples:[{case_id:'case',resource_id:'loan-1042',subject_identity_id:'owner',case_verdict:'SAFE',conditions:[],evidence_refs:['evidence']}],
}]} as unknown as ResultStory

it('报告首层区分规则条件与实际取得结论的状态，补查保留准确修订',()=>{
  const inspect=vi.fn()
  render(<SampleCoverage story={story} origin="/reports?run_id=original" onInspect={inspect}/>)
  expect(screen.getByRole('heading',{name:'本次实际样本'})).toBeVisible()
  expect(screen.getByRole('heading',{name:'仍需检查'})).toBeVisible()
  const address=new URL(screen.getAllByRole('link',{name:'准备剩余场景'})[0].getAttribute('href')!.slice(1),'http://localhost')
  expect(address.searchParams.get('revision')).toBe('2')
  expect(address.searchParams.get('intent_hash')).toBe('frozen')
  fireEvent.click(screen.getByText('逐条权限的覆盖情况'))
  expect(screen.getByRole('columnheader',{name:'尚未取得结论的状态'})).toBeVisible()
  expect(screen.getByRole('cell',{name:/待领取.*准备剩余场景/})).toBeVisible()
  fireEvent.click(screen.getByText('阅读实际样本与观察来源'))
  fireEvent.click(screen.getByRole('button',{name:'资源 loan-1042 · 阅读本项依据'}))
  expect(inspect).toHaveBeenCalledWith('case')
})

it('历史没有覆盖摘要时给出实际阅读位置，归档不提供修改入口',()=>{
  const {rerender}=render(<SampleCoverage story={{...story,sample_coverage:undefined}} origin="/reports" onInspect={vi.fn()}/>)
  expect(screen.getByText(/本报告未提供可核对的样本覆盖摘要/)).toBeVisible()
  rerender(<SampleCoverage story={story} origin="/reports" onInspect={vi.fn()} readOnly/>)
  expect(screen.queryByRole('link',{name:'准备剩余场景'})).not.toBeInTheDocument()
})

it('补查带着准确规则、目标状态和原报告直达对应资源材料',()=>{
 const value=resultStory();value.sample_coverage=story.sample_coverage;value.actions[0].permission={...value.actions[0].permission,...story.sample_coverage![0].permission}
 render(<SampleCoverage story={value} origin="/reports?run_id=original" onInspect={vi.fn()}/> )
 const address=new URL(screen.getAllByRole('link',{name:'准备剩余场景'})[0].getAttribute('href')!.slice(1),'http://localhost')
 expect(address.pathname).toBe('/preparation');expect(address.searchParams.get('target_state')).toBe('待领取');expect(address.searchParams.get('focus')).toBe('resource');expect(address.searchParams.get('action_id')).toBe(value.actions[0].action_id);expect(address.searchParams.get('revision')).toBe('2');expect(address.searchParams.get('return_to')).toBe('/reports?run_id=original')
})
