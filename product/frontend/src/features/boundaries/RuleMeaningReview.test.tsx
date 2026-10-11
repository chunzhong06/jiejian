// 多页选择只保存在当前编辑会话；修订回读保留未提交草稿，依据变化必须重新选择。
import {cleanup,fireEvent,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {RuleMeaningReview} from './RuleMeaningReview'
import type {RuleCandidateView} from '../../api/boundaries/ruleCandidates'

afterEach(cleanup)
const fixture=():RuleCandidateView=>({candidate:{candidate_id:'rcd_a',project_id:'app_a',revision:1,basis_id:'basis',submitted_via:'MCP',created_at_us:1,
  content:{original_text:'原始要求',actors:[],actions:[],permissions:[],examples:[],unresolved_questions:[],unsupported_constraints:[],
    scenarios:['first','second'].map(id=>({scenario_id:id,scenario_fingerprint:id,original_excerpt:'原始要求',question:`问题 ${id}`,options:[
      {option_id:'allow',label:'允许',explanation:'按约定执行',replacements:[]},{option_id:'deny',label:'禁止',explanation:'保护结果',replacements:[]}]}))}},
  assessment:'NEEDS_CHANGES',issues:[],proposal_id:null,decision:null,reuse:{status:'MISSING',message:''},review_url:''})

it('切换情境和保存另一处修订都保留未保存选择，依据变更后失效',()=>{
  const value=fixture(),onSave=vi.fn(),view=render(<RuleMeaningReview value={value} busy={false} onSave={onSave}/>)
  fireEvent.click(screen.getByRole('radio',{name:'允许 按约定执行'}))
  fireEvent.click(screen.getByRole('button',{name:'下一处'}))
  fireEvent.click(screen.getByRole('radio',{name:/暂不确定/}))
  fireEvent.click(screen.getByRole('button',{name:'保存待定'}))
  expect(onSave).toHaveBeenCalledWith({scenario_id:'second',scenario_fingerprint:'second',action:'DEFER'})
  const saved:RuleCandidateView={...value,candidate:{...value.candidate,revision:2},scenario_decisions:[{scenario_id:'second',status:'DEFER',decision:{decision_id:'decision',option_id:null,correction:null}}]}
  view.rerender(<RuleMeaningReview value={saved} busy={false} onSave={onSave}/>)
  expect(screen.getByRole('button',{name:'保存待定'})).toBeDisabled()
  expect(screen.getByText(/已保存 1 \/ 2 处；1 处修改尚未保存/)).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'上一处'}))
  expect(screen.getByRole('radio',{name:'允许 按约定执行'})).toBeChecked()
  expect(screen.getByRole('button',{name:'保存这个含义'})).toBeEnabled()
  const changed={...saved,candidate:{...saved.candidate,revision:3,content:{...saved.candidate.content,scenarios:saved.candidate.content.scenarios!.map(item=>({...item,scenario_fingerprint:'changed-'+item.scenario_id}))}}}
  view.rerender(<RuleMeaningReview value={changed} busy={false} onSave={onSave}/>)
  expect(screen.getByRole('radio',{name:'允许 按约定执行'})).not.toBeChecked()
  expect(onSave).toHaveBeenCalledTimes(1)
})

it('已有人工选择回填；纠正文字切页保留且离开前提醒',()=>{
  const value=fixture()
  value.scenario_decisions=[{scenario_id:'first',status:'SELECT',decision:{decision_id:'d',option_id:'deny',correction:null}}]
  render(<RuleMeaningReview value={value} busy={false} onSave={vi.fn()}/>)
  expect(screen.getByRole('radio',{name:'禁止 保护结果'})).toBeChecked()
  fireEvent.click(screen.getByRole('radio',{name:/不是这个意思/}))
  fireEvent.change(screen.getByRole('textbox'),{target:{value:'仍须保留曾经开放的要求'}})
  fireEvent.click(screen.getByRole('button',{name:'下一处'}));fireEvent.click(screen.getByRole('button',{name:'上一处'}))
  expect(screen.getByRole('textbox')).toHaveValue('仍须保留曾经开放的要求')
  const event=new Event('beforeunload',{cancelable:true});window.dispatchEvent(event)
  expect(event.defaultPrevented).toBe(true)
})
