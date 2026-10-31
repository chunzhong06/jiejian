import {fireEvent,render,screen,waitFor} from '@testing-library/react'
import {beforeEach,expect,it,vi} from 'vitest'
import {Report} from './Report'
import {EvidenceInspector} from './EvidenceInspector'
import {EvidenceRecord} from './EvidenceRecord'
import {currentChecksApi} from '../../../entities/check/api/currentChecks'
import type {EvidenceRecordView,ResultStory} from '../../../entities/check/api/currentChecks'
import {story,outcome} from './Report.fixtures'

it('普通应用展示自动调用，选择节点可读取对应发布记录且不冒充权限事件',()=>{
  const value=story(),action=value.actions[0],onLocate=vi.fn()
  action.request_activity={evidence_refs:['ev-auto'],capture:{collector:'CONTROLLED_NODE',adapters:['node:http','node:sqlite'],complete:true,dropped_count:0,events:[
    {event_id:'http',parent_event_id:null,kind:'HTTP_SERVER',operation:'REQUEST',started_at_us:10,duration_us:3000,outcome:'OK',source_location:null,http_method:'POST',http_status:403},
    {event_id:'sql',parent_event_id:'http',kind:'SQLITE',operation:'GET',started_at_us:12,duration_us:20,outcome:'OK',source_location:'app.mjs:15',http_method:null,http_status:null},
  ]}}
  const p={story:value,action,tab:'trace',evidenceId:null,recordId:null,onClose:vi.fn(),onLocate,onError:vi.fn()}
  const view=render(<EvidenceInspector {...p}/>)
  expect(screen.getByRole('region',{name:'自动采集的调用路径'})).toBeVisible()
  expect(screen.queryByText('执行权限判断')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'查询一条记录'}))
  expect(onLocate).toHaveBeenCalledWith('trace',undefined,undefined,undefined,'sql')
  view.rerender(<EvidenceInspector {...p} stepId="sql"/>)
  expect(screen.getByText('app.mjs:15')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'查看本次调用记录'}))
  expect(onLocate).toHaveBeenCalledWith('records','ev-auto',undefined,undefined,'sql')
})

beforeEach(()=>vi.spyOn(window,'scrollTo').mockImplementation(()=>{}))
const props=(value:ResultStory)=>({story:value,selectedCaseId:null,tab:null,evidenceId:null,recordId:null,onError:vi.fn()})

function recordView():EvidenceRecordView {
  return {project_id:'p1',run_id:'r1',case_id:'c1',action_id:'a1',evidence_id:'ev1',
    record:{record_id:'call1',kind:'ACTIVITY',label:'调用 SQLite',proof_fingerprint:null,observer_id:null,phase:null,event_id:'sql'},
    role:'SUPPORTING',summary:'过程调用不能单独证明业务结果。',published_judgement:'证据不足',
    verification:[{key:'method',title:'取证方式',status:'CONFIRMED',text:'宿主在请求内采集。',record_refs:[],source:{},fragment:{}},
      {key:'reason',title:'判断依据',status:'UNKNOWN',text:'业务结果的归属尚未确认。',record_refs:[],source:{},fragment:{}}],
    values:[{label:'代码位置',value:'app.mjs:9'}],location:{pointer:'/activity/events/1'},fragment:{operation:'GET'},related_records:[],limitations:['仅覆盖已启用探针。']}
}

it('记录先展示自身值，检查背景和原文分别按需展开且不丢失未知判断',async()=>{
  render(<EvidenceRecord value={recordView()}/>)
  expect(screen.getByText('app.mjs:9')).toBeVisible()
  expect(screen.getByText('宿主在请求内采集。')).toBeVisible()
  expect(screen.getByText('业务结果的归属尚未确认。')).not.toBeVisible()
  expect(screen.queryByText(/"operation": "GET"/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('检查背景与已发布判断'))
  expect(screen.getByText('业务结果的归属尚未确认。')).toBeVisible()
  fireEvent.click(screen.getByText('适用范围与封存原文'))
  await waitFor(()=>expect(screen.getByText(/"operation": "GET"/)).toBeVisible())
  expect(screen.getByText('仅覆盖已启用探针。')).toBeVisible()
})

it('业务证明保留前后值与各自含义，不混成过程状态',()=>{
  const value=recordView();value.role='PROOF';value.record.kind='FACT'
  value.values=[{label:'文件内容',before:'abc',after:'def',before_label:'参照文件',after_label:'实际收到'}]
  render(<EvidenceRecord value={value}/>)
  for(const label of ['业务证明','参照文件','实际收到','abc','def'])expect(screen.getByText(label)).toBeVisible()
})

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

it('准确记录与文档一起读取，不再先目录再串行读取详情',async()=>{
  const value=recordView(),response=bundle()
  const item={...response.items[0],index:{...response.items[0].index,records:[value.record]},record:value}
  const read=vi.spyOn(currentChecksApi,'evidenceBundle').mockResolvedValue({...response,items:[item]} as never)
  const separate=vi.spyOn(currentChecksApi,'evidenceRecord')
  render(<Report {...props(story())} selectedCaseId="c1" tab="records" evidenceId="ev1" recordId="call1"/>)
  await waitFor(()=>expect(screen.getByText('app.mjs:9')).toBeVisible())
  expect(read).toHaveBeenCalledWith('p1','r1','c1',['ev1'],'call1')
  expect(separate).not.toHaveBeenCalled()
})

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
