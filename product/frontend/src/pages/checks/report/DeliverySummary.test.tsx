import {fireEvent,render,screen} from '@testing-library/react'
import {expect,it,vi} from 'vitest'
import {DeliverySummary} from './DeliverySummary'
import type {ResultStory} from '../../../entities/check/api/currentChecks'

type Item=NonNullable<ResultStory['delivery_summary']>[number]
function result(items:Array<Pick<Item,'kind'|'label'|'result'|'case_ids'>&Partial<Item>>):ResultStory{
  return {project_id:'app',run_id:'current',verdict:'PASS',judgement:'符合本次要求',policy_epoch:1,
    actions:[],claim_boundary:[],technical_references:[],
    delivery_summary:items.map(item=>({permission:null,source_run_id:null,source_case_id:null,...item}))}
}

it('从修复摘要按业务对象选择本次事实，并保留准确原题回程',()=>{
  const onInspect=vi.fn()
  const story=result([
    {kind:'NORMAL',label:'本人读取申请',result:'符合要求',case_ids:['owner']},
    {kind:'PERMISSION',label:'他人读取申请',result:'符合要求',case_ids:['other']},
    {kind:'REPAIR',label:'原问题修复',result:'VERIFIED',case_ids:['owner','other'],source_run_id:'original',source_case_id:'before'}
  ])
  render(<DeliverySummary story={story} origin="/reports?run_id=current" onInspect={onInspect}/>)
  fireEvent.click(screen.getByText('本次交付摘要'))
  expect(screen.getByText('原题修复已验证')).toBeVisible()
  fireEvent.click(screen.getByText('阅读本次 2 项事实'))
  fireEvent.click(screen.getByRole('button',{name:'他人读取申请'}))
  expect(onInspect).toHaveBeenCalledWith('other')
  const destination=new URL(screen.getByRole('link',{name:'阅读原问题'}).getAttribute('href')!.slice(1),'http://localhost')
  expect(destination.searchParams.get('run_id')).toBe('original')
  expect(destination.searchParams.get('case_id')).toBe('before')
  expect(destination.searchParams.get('project_id')).toBe('app')
  expect(destination.searchParams.get('return_to')).toBe('/reports?run_id=current')
})

it('未执行要求可核对原修订与内容身份，且不提供虚假的执行事实入口',()=>{
  const story=result([{kind:'UNCHECKED',label:'本次未选要求',result:'未执行',case_ids:[],
    permission:{intent_id:'original-rule',revision:3,intent_hash:'a'.repeat(64)}}])
  render(<DeliverySummary story={story} origin="/reports?run_id=current" onInspect={vi.fn()}/>)
  fireEvent.click(screen.getByText('本次交付摘要'))
  expect(screen.queryByRole('button',{name:'阅读本项事实'})).toBeNull()
  fireEvent.click(screen.getByText('查看准确要求引用'))
  expect(screen.getByText('original-rule')).toBeVisible()
  expect(screen.getByText('修订 3')).toBeVisible()
})
