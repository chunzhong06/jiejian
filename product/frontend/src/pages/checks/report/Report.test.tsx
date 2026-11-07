import {fireEvent,render,screen,waitFor,within} from '@testing-library/react'
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

it('业务场景按资源比较，展开依据后索引收敛并保留准确资源与发生位置',()=>{
  const value=story(),first=value.actions[0]
  first.scenario_context={scenario_label:'混合批量',experiment_label:'成员混合处理',experiment_kind:'CHANGE_SUBJECT',invocation_label:'发布资料',item_index:1,item_count:2,same_resource_occurrences:1,batch_strategy:'PER_ITEM',expected_effect:'ABSENT'}
  first.fact_comparison.resource_id='alpha'
  value.actions.push({...structuredClone(first),case_id:'c3',scenario_context:{...first.scenario_context,item_index:2},fact_comparison:{...structuredClone(first.fact_comparison),resource_id:'beta'}})
  const view=render(<Report {...props(value)}/>)
  const table=screen.getByRole('table',{name:'逐项业务场景结果'})
  expect(within(table).getByText('alpha')).toBeVisible()
  expect(within(table).getByText('beta')).toBeVisible()
  expect(within(table).getByRole('columnheader',{name:'操作账号与归属'})).toBeVisible()
  fireEvent.click(within(table).getByRole('button',{name:/alpha/}))
  expect(location.hash).toContain('case_id=c1')
  view.rerender(<Report {...props(value)} selectedCaseId="c1"/>)
  expect(within(screen.getByRole('table',{name:'逐项业务场景结果'})).queryByRole('columnheader',{name:'操作账号与归属'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:/beta/})).toBeVisible()
})

it('归档状态归入报告信息，保留只读边界与两个明确返回入口',()=>{
  render(<Report {...props(story())} readOnly archiveName="展馆历史工作区" basePath="/archive?project_id=app" returnPath="/archive?project_id=app"/> )
  expect(screen.getByText('已归档')).toBeVisible()
  expect(screen.getByText('展馆历史工作区')).toBeVisible()
  expect(screen.getByRole('link',{name:'返回官方示例'})).toHaveAttribute('href','#/environment')
  expect(screen.queryByRole('button',{name:'处理权限问题'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'全部报告'}))
  expect(location.hash).toBe('#/archive?project_id=app')
})

it('展开依据后索引只保留定位信息，关闭后恢复完整摘要',()=>{
  const value=story(),p=props(value)
  const view=render(<Report {...p}/>),results=()=>view.container.querySelector('.jj-report-results')!
  expect(results().querySelector('.jj-result-actual')).toBeInTheDocument()
  view.rerender(<Report {...p} selectedCaseId="c1"/>)
  const index=within(results() as HTMLElement).getByRole('button',{name:'查看成员导出资料的依据'})
  expect(index).toHaveTextContent('成员不得导出资料')
  expect(index.querySelector('small')).toBeNull()
  expect(index.querySelector('.jj-case-outcome')).toBeNull()
  expect(screen.getByRole('complementary',{name:'检查依据'})).toBeVisible()
  view.rerender(<Report {...p}/>)
  expect(results().querySelector('.jj-result-actual')).toBeInTheDocument()
})

it('结果筛选保留对应检查项，空筛选可以返回全部结果',()=>{
  const value=story(),safe=structuredClone(value.actions[0]);safe.case_id='safe';safe.judgement='检查结果符合已批准的权限要求';safe.display_name='正常下载'
  value.actions.push(safe)
  render(<Report {...props(value)}/>)
  const filters=screen.getByRole('group',{name:'按检查结果筛选'})
  fireEvent.click(within(filters).getByRole('button',{name:/符合规则/}))
  expect(screen.getByRole('button',{name:'查看成员正常下载的依据'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'查看成员导出资料的依据'})).not.toBeInTheDocument()
  fireEvent.click(within(filters).getByRole('button',{name:/尚未确认/}))
  expect(screen.getByText('本次没有这类结果')).toBeVisible()
  fireEvent.click(screen.getByRole('button',{name:'查看全部结果'}))
  expect(screen.getByRole('button',{name:'查看成员导出资料的依据'})).toBeVisible()
})

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

it('复验先比较修改前后，原始依据只在选中项中查阅；缺少对应场景不能显示已解决',()=>{
  const value=story();value.verdict='PASS';value.actions[0].judgement='本次权限要求已得到验证';
  value.repair_verification={repair_reference:'repair',source_run_id:'before',run_id:'r1',status:'VERIFIED',reason_codes:[]};
  value.repair_comparison=[{role:'DENY',source_case_id:'old',action_label:'导出资料',subject_label:'成员',resource_owner_label:'负责人',resource_id:'resource',effect_labels:['完整交付包'],before_verdict:'VULNERABLE',before_evidence_refs:['original'],after_case_id:'c1',match_status:'MATCHED'}];
  const p=props(value),view=render(<Report {...p}/>);
  const table=screen.getByRole('table');
  expect(within(table).getByRole('columnheader',{name:'修改前'})).toBeVisible();
  expect(within(table).getByText('存在权限问题')).toBeVisible();
  expect(within(table).getByText('已解决')).toBeVisible();
  fireEvent.click(within(table).getByRole('button',{name:'查看成员不得导出资料的复验依据'}));
  expect(location.hash).toContain('run_id=r1&case_id=c1');
  view.rerender(<Report {...p} selectedCaseId="c1"/>);
  const inspector=screen.getByRole('complementary',{name:'检查依据'});
  const prior=within(inspector).getByText('修改前的结果与原检查').closest('details')!;
  expect(prior).not.toHaveAttribute('open');
  fireEvent.click(within(inspector).getByText('修改前的结果与原检查'));
  fireEvent.click(within(prior).getByRole('button',{name:'查看原检查依据'}));
  expect(location.hash).toContain('run_id=before&case_id=old');
  value.repair_comparison[0].match_status='NOT_FOUND';
  view.rerender(<Report {...p}/>);
  expect(screen.queryByText('已解决')).not.toBeInTheDocument();
  expect(screen.getByText('缺少对应场景')).toBeVisible();
});

it('连续查阅不同检查项后，关闭依据返回最后选中的检查项',()=>{
  const value=story(),second=structuredClone(value.actions[0]);second.case_id='c2';second.display_name='预览资料';value.actions.push(second);
  const p=props(value),view=render(<Report {...p}/>);
  screen.getByRole('button',{name:'查看成员导出资料的依据'}).focus();
  fireEvent.click(document.activeElement!);
  view.rerender(<Report {...p} selectedCaseId="c1"/>);
  const target=screen.getByRole('button',{name:'查看成员预览资料的依据'});target.focus();fireEvent.click(target);
  view.rerender(<Report {...p} selectedCaseId="c2"/>);
  fireEvent.click(screen.getByRole('button',{name:'关闭检查依据'}));
  view.rerender(<Report {...p}/>);
  expect(screen.getByRole('button',{name:'查看成员预览资料的依据'})).toHaveFocus();
});
