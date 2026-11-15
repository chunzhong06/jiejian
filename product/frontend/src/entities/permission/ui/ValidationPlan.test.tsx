import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,beforeEach,expect,it,vi} from 'vitest'
import {ValidationPlanPanel} from './ValidationPlan'
import {validationApi,type ValidationPlan} from '../api/validation'
import {ruleCandidatesApi} from '../api/ruleCandidates'

const plan:ValidationPlan={project_id:'app',basis_id:'rb_'+'a'.repeat(64),fingerprint:'b'.repeat(64),candidate_id:null,candidate_revision:null,state:'CURRENT',scope:'只说明当前要求的准备依据。',requirements:[{
  item_id:'rule',intent_id:'pin_current',revision:2,action_id:'action',action_item_id:'item',action_label:'修改申请',sentence:'借用人不得修改他人的申请。',expectation:'DENY',relation:'SAME_ROLE_OTHER_ACCOUNT',conditions:null,normal_control:'需要正常功能对照。',preparation_requirements:['独立核对提交事实'],preparation_url:'/reports?view=plan&rule_id=pin_current',current_materials:[],effects:[{item_id:'effect',label:'申请内容被修改',kind:'STATE_MUTATION',requirement:'核对完整提交事实。',supported_paths:['TRANSACTION_HISTORY_V2'],protected_fields:['title'],material_status:'NEEDS_SOURCE',reason_codes:[]}]
}],questions:[{requirement_id:'req_question',fingerprint:'c'.repeat(64),action_item_id:'item',dimension:'OTHER_ACCOUNT:actor',question:'他人申请能否修改？',basis:'已有本人申请修改要求。',source_excerpt:'权限边界核对',status:'NEEDS_DECISION',review_url:null,decision_reason:null}]}
beforeEach(()=>{sessionStorage.clear();location.hash='#/permissions?project_id=app';vi.spyOn(validationApi,'read').mockResolvedValue(plan)})
afterEach(()=>{vi.restoreAllMocks();sessionStorage.clear()})

it('源码概览逐项保留所有要求及各自材料说明，不截断第四项',async()=>{
  const requirements=Array.from({length:4},(_,index)=>({...plan.requirements[0],item_id:'rule'+index,sentence:'业务要求'+index,preparation_summary:'该要求的材料说明'+index}))
  vi.mocked(validationApi.read).mockResolvedValue({...plan,requirements})
  render(<ValidationPlanPanel projectId="app" mode="summary"/>)
  expect(await screen.findByText('业务要求3')).toBeVisible()
  expect(screen.getByText('该要求的材料说明3')).toBeVisible()
  expect(screen.getByText('4 项要求')).toBeVisible()
  expect(screen.getByRole('link',{name:'核对权限与验证方案'})).toHaveAttribute('href',expect.stringContaining('return_to='))
})

it('把证明、正常对照和准确准备回程放在同一要求下',async()=>{
  render(<ValidationPlanPanel projectId="app" reference={{intent_id:'pin_current'}}/>)
  expect(await screen.findByText('申请内容被修改')).toBeVisible()
  expect(screen.getByText('需要正常功能对照。')).toBeVisible()
  const href=screen.getByRole('link',{name:'准备并核对这项要求'}).getAttribute('href')!
  const url=new URL(href.slice(1),'http://localhost')
  expect(url.searchParams.get('rule_id')).toBe('pin_current')
  expect(url.searchParams.get('project_id')).toBe('app')
  expect(url.searchParams.get('return_to')).toBe('/permissions?project_id=app')
})

it('多条要求只选择阅读对象，切换后准备入口保留该要求的准确引用',async()=>{
 const other={...plan.requirements[0],item_id:'other',intent_id:'pin_other',sentence:'管理员可以修改自己的申请。',normal_control:'管理员本人的正常操作。',preparation_url:'/reports?view=plan&rule_id=pin_other'}
 vi.mocked(validationApi.read).mockResolvedValue({...plan,requirements:[plan.requirements[0],other]})
 render(<ValidationPlanPanel projectId="app"/>)
 const select=await screen.findByRole('button',{name: /管理员可以修改自己的申请/})
 fireEvent.click(select)
 expect(select).toHaveAttribute('aria-pressed','true')
 expect(screen.getByRole('article',{name:other.sentence})).toBeVisible()
 expect(screen.queryByRole('article',{name:plan.requirements[0].sentence})).not.toBeInTheDocument()
 expect(screen.getByText('管理员本人的正常操作。')).toBeVisible()
 expect(screen.getByRole('link',{name:'准备并核对这项要求'})).toHaveAttribute('href',expect.stringContaining('rule_id=pin_other'))
})

it('刷新失败保留已有依据并停止基于旧方案开新核对',async()=>{
  vi.mocked(validationApi.read).mockResolvedValueOnce(plan).mockRejectedValue(new Error('读取中断'))
  const view=render(<ValidationPlanPanel projectId="app" mode="questions"/>)
  await screen.findByText('继续核对业务边界')
  fireEvent.click(screen.getByText('查看相关问题与已保存决定'))
  fireEvent.focus(window)
  await screen.findByText('读取中断')
  expect(screen.getByText('他人申请能否修改？')).toBeVisible()
  expect(screen.getByRole('button',{name:'核对这项要求'})).toBeDisabled()
  view.unmount()
})

it('未知保存先查原SAVE回执，找到后回同一候选且不重复创建',async()=>{
  const key='jiejian.validation-question:app:req_question:'+plan.questions[0].fingerprint
  sessionStorage.setItem(key,JSON.stringify({operation_id:'d'.repeat(32),expected_fingerprint:plan.fingerprint,question_fingerprint:plan.questions[0].fingerprint}))
  const receipt=vi.spyOn(ruleCandidatesApi,'receipt').mockResolvedValue({status:'FOUND',candidate:{candidate:{candidate_id:'candidate',revision:3}} as never})
  const write=vi.spyOn(validationApi,'open')
  render(<ValidationPlanPanel projectId="app" mode="questions"/>)
  await screen.findByText('继续核对业务边界')
  fireEvent.click(screen.getByText('查看相关问题与已保存决定'))
  fireEvent.click(screen.getByRole('button',{name:'核对这项要求'}))
  await waitFor(()=>expect(receipt).toHaveBeenCalledWith('app','d'.repeat(32),'SAVE'))
  await waitFor(()=>expect(location.hash).toContain('candidate_id=candidate'))
  expect(write).not.toHaveBeenCalled()
  expect(sessionStorage.getItem(key)).toBeNull()
})
