import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {Report} from './Report'
import {currentChecksApi} from '../../../entities/check/api/currentChecks'
import type {ResultStory} from '../../../entities/check/api/currentChecks'
import {story,outcome} from './Report.fixtures'

beforeEach(()=>vi.spyOn(window,'scrollTo').mockImplementation(()=>{}))
const props=(value:ResultStory)=>({story:value,selectedCaseId:null,tab:null,evidenceId:null,recordId:null,onError:vi.fn()})

it.each([
  ['PASS','本次权限要求已得到验证','本次范围符合权限规则'],
  ['BLOCK','已确认不应发生的业务后果','1 项结果不符合权限规则'],
  ['INCONCLUSIVE','现有证据不足以完成判断','仍有检查结果无法确认'],
] as const)('保留发布的 %s 结论及适用范围',(verdict,judgement,title)=>{
  const value=story();value.verdict=verdict;value.actions[0].judgement=judgement
  render(<Report {...props(value)}/>)
  expect(screen.getByRole('heading',{name:title,level:1})).toBeVisible()
  expect(screen.getByText('本次检查的适用范围')).toBeVisible()
  expect(screen.queryByRole('complementary',{name:'检查依据'})).not.toBeInTheDocument()
})

it('进入准确用例，未知用例不退回其他检查项',()=>{
  const value=story(),p=props(value)
  const view=render(<Report {...p}/>)
  fireEvent.click(screen.getByRole('button',{name:'查看成员导出资料的依据'}))
  expect(location.hash).toContain('run_id=r1&case_id=c1')
  view.rerender(<Report {...p} selectedCaseId="missing-case"/>)
  expect(screen.getByText('本报告没有这项检查')).toBeVisible()
  expect(screen.queryByRole('tab',{name:'业务结果'})).not.toBeInTheDocument()
})

function bundle(){return {project_id:'p1',run_id:'r1',case_id:'c1',items:[{
  document:{schema_version:'1',run_id:'r1',action_id:'a1',case:{case_id:'c1',resource_id:'resource'},evidence_id:'ev1',outcome,observations:[],trace:null},
  index:{project_id:'p1',run_id:'r1',case_id:'c1',action_id:'a1',evidence_id:'ev1',records:[]},
}]}}

it.each(['project','run','case','action','document'] as const)('不展示归属错误的 %s 证据',async kind=>{
  const response=bundle()
  if(kind==='project')response.project_id='other'
  else if(kind==='run')response.items[0].document.run_id='other'
  else if(kind==='case')response.items[0].document.case.case_id='other'
  else if(kind==='action')response.items[0].document.action_id='other'
  else response.items[0].document.evidence_id='other'
  vi.spyOn(currentChecksApi,'evidenceBundle').mockResolvedValue(response as never)
  const read=vi.spyOn(currentChecksApi,'evidenceRecord')
  render(<Report {...props(story())} selectedCaseId="c1" tab="records" evidenceId="ev1" recordId={null}/>)
  await waitFor(()=>expect(screen.getByRole('alert')).toBeInTheDocument())
  expect(read).not.toHaveBeenCalled()
})

it('未知记录不退回第一条，也不读取不存在的片段',async()=>{
  vi.spyOn(currentChecksApi,'evidenceBundle').mockResolvedValue(bundle() as never)
  const read=vi.spyOn(currentChecksApi,'evidenceRecord')
  render(<Report {...props(story())} selectedCaseId="c1" tab="records" evidenceId="ev1" recordId="missing-record"/>)
  await waitFor(()=>expect(screen.getByRole('alert')).toBeInTheDocument())
  expect(read).not.toHaveBeenCalled()
})
