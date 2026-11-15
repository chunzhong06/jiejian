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

it('证明入口按真实业务名称识别，同一文件保留多项结果并定位原引用',()=>{
 const value=story(),action=value.actions[0],locate=vi.fn()
 action.proof_coverage=['已提交审批','记录归属正确'].map(label=>({effect_id:label,business_label:label,proof_fingerprint:label,required_level:'VERDICT_REQUIRED',source_label:'独立业务记录',observed_state:'CONFIRMED',evidence_refs:['ev-shared'],supporting_evidence_refs:[],limitations:[]}))
 action.decisive_proof_chain=[];action.evidence_explanations=[]
 render(<EvidenceInspector story={value} action={action} tab="records" evidenceId={null} recordId={null} onClose={vi.fn()} onLocate={locate} onError={vi.fn()}/>)
 const record=screen.getByRole('button',{name:/已提交审批、记录归属正确/})
 expect(screen.getAllByRole('button',{name:/查看内容/})).toHaveLength(1)
 fireEvent.click(record)
 expect(locate).toHaveBeenCalledWith('records','ev-shared',undefined,undefined,'')
})

it('结果之后完整呈现业务范围，结论旁保留未覆盖摘要且原说明直接可见',()=>{
 const value=story()
 value.discovery_coverage={fingerprint:'a'.repeat(64),pending_count:2,recheck_count:0,related_count:1,excluded_count:0,unexecuted_request_count:1,omitted_count:0,items:[]}
 const view=render(<Report {...props(value)}/>)
 const summary=screen.getByLabelText('本次结论之外的业务范围')
 const scope=screen.getByRole('region',{name:'本次检查的适用范围'})
 const results=view.container.querySelector('.jj-report-results')!
 expect(summary).toBeVisible()
 expect(summary).toHaveTextContent('2 项业务线索未形成权限验证结论')
 expect(scope).toBeVisible()
 fireEvent.click(within(scope).getByText('本次检查的适用范围'))
 expect(within(scope).getAllByRole('heading')).toHaveLength(1)
 expect(within(scope).getByText(/2 项线索当时尚未完成核对/)).toBeVisible()
 expect(within(scope).getByText(/1 个已关联接口未作为本次受检步骤执行/)).toBeVisible()
 expect(summary.compareDocumentPosition(results)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
 expect(results.compareDocumentPosition(scope)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
})

it('外部再次验证只解释一次代码边界，部署声明与检查范围各自保留',()=>{
 const value=story()
 value.runtime_status='UNCONFIRMED' as never
 value.environment={name:'本地测试连接'} as never
 value.repair_verification={verification_scope:'EXTERNAL_OBSERVATION',source_run_id:'before',status:'VERIFIED',reason_codes:[]} as never
 value.external_recheck={deployment_statement:'已限制他人读取订单备注'} as never
 value.selection={selected:[{}],added_controls:[{}],omitted:[],pending_review_ids:[]} as never
 value.actions[0].case_verdict='SAFE'
 value.actions.push({...structuredClone(value.actions[0]),case_id:'c2',permission:{expectation:'ALLOW',relation:'OWNS'}})
 value.repair_comparison=[{role:'DENY',source_case_id:'before1',after_case_id:'c1',before_verdict:'VULNERABLE',match_status:'MATCHED'},{role:'SELECTED_ALLOW',source_case_id:'before2',after_case_id:'c2',before_verdict:'SAFE',match_status:'MATCHED'}] as never
 render(<Report {...props(value)}/> )
 const boundary=screen.getByRole('complementary',{name:'本次验证的适用范围'})
 expect(boundary).toHaveTextContent('源码修改与部署版本的对应关系尚未独立核验')
 expect(boundary).toHaveTextContent('已限制他人读取订单备注')
 expect(screen.queryByText('应用声明的运行版本尚未核对')).not.toBeInTheDocument()
 expect(screen.queryByText(/本次检查尚未核对运行代码/)).not.toBeInTheDocument()
 expect(screen.queryByText(/另有 0 条规则未检查/)).not.toBeInTheDocument()
 expect(screen.getByLabelText('本次检查范围')).toHaveTextContent('另加正常对照 1 条')
 expect(screen.getByText('本次符合要求',{exact:true})).toBeVisible()
 expect(screen.queryByText('已解决',{exact:true})).not.toBeInTheDocument()
})

it('已选正常规则不被零条追加对照误写为没有正常对照',()=>{
 const value=story()
 value.selection={selected:[{},{}],added_controls:[],omitted:[],pending_review_ids:[]} as never
 render(<Report {...props(value)}/> )
 expect(screen.getByLabelText('本次检查范围')).toHaveTextContent('选定 2 条规则')
 expect(screen.queryByText('正常对照 0 条',{exact:true})).not.toBeInTheDocument()
 expect(screen.queryByText('另加正常对照 0 条',{exact:true})).not.toBeInTheDocument()
})

it('深入证据退出完整报告总览，返回同一业务事项并保留原回程',()=>{
  const value=story(),p={...props(value),selectedCaseId:'c1',tab:'trace',returnPath:'/issues?issue=original'};
  const view=render(<Report {...p}/>);
  expect(view.container.querySelector('.jj-report-hero')).not.toBeInTheDocument();
  expect(screen.queryByRole('tab',{name:'业务结果'})).not.toBeInTheDocument();
  expect(screen.queryByRole('group',{name:'按检查结果筛选'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'返回本项业务结果'}));
  const query=new URLSearchParams(location.hash.split('?')[1]);
  expect(query.get('case_id')).toBe('c1');expect(query.get('tab')).toBe('facts');
  expect(query.get('return_to')).toBe('/issues?issue=original');
  view.rerender(<Report {...p} tab="facts"/>);
  expect(view.container.querySelector('.jj-report-hero')).toBeVisible();
  expect(view.container.querySelector('.jj-report-results')).toBeVisible();
});

it('业务场景按操作人辨识，展开依据后索引收敛并保留准确资源与发生位置',()=>{
  const value=story(),first=value.actions[0]
  first.scenario_context={scenario_label:'混合批量',experiment_label:'成员混合处理',experiment_kind:'CHANGE_SUBJECT',invocation_label:'发布资料',item_index:1,item_count:2,same_resource_occurrences:1,batch_strategy:'PER_ITEM',expected_effect:'ABSENT'}
  first.fact_comparison.resource_id='alpha'
  value.actions.push({...structuredClone(first),case_id:'c3',scenario_context:{...first.scenario_context,item_index:2},fact_comparison:{...structuredClone(first.fact_comparison),resource_id:'beta'}})
  const view=render(<Report {...props(value)}/>)
  const table=screen.getByRole('table',{name:'逐项业务场景结果'})
  expect(within(table).getByText('alpha')).toBeVisible()
  expect(within(table).getByText('beta')).toBeVisible()
  expect(within(table).getByRole('columnheader',{name:'资源归属'})).toBeVisible()
  fireEvent.click(within(table).getByRole('button',{name:/alpha/}))
  expect(location.hash).toContain('case_id=c1')
  view.rerender(<Report {...props(value)} selectedCaseId="c1"/>)
  expect(within(screen.getByRole('table',{name:'逐项业务场景结果'})).queryByRole('columnheader',{name:'资源归属'})).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:/beta/})).toBeVisible()
})

it('归档状态归入报告信息，保留只读边界与两个明确返回入口',()=>{
  render(<Report {...props(story())} readOnly archiveName="展馆历史工作区" basePath="/archive?project_id=app" returnPath="/archive?project_id=app"/> )
  expect(screen.getByText('已归档')).toBeVisible()
  expect(screen.getByText('展馆历史工作区')).toBeVisible()
  expect(screen.getByRole('link',{name:'返回官方示例'})).toHaveAttribute('href','#/environment')
  expect(screen.queryByRole('button',{name:'处理权限问题'})).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('link',{name:'全部检查记录'}))
  expect(location.hash).toBe('#/archive?project_id=app')
})

it('大量结果展开依据后索引只保留定位信息，关闭后恢复完整摘要',()=>{
  const value=story();for(let i=0;i<4;i++)value.actions.push({...structuredClone(value.actions[0]),case_id:'extra-'+i,display_name:'其他操作'+i});const p=props(value)
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

it('结果筛选保留对应检查项，零项类别不占入口且可返回全部结果',()=>{
  const value=story(),safe=structuredClone(value.actions[0]);safe.case_id='safe';safe.case_verdict='SAFE';safe.judgement='检查结果符合已批准的权限要求';safe.display_name='正常下载'
  value.actions.push(safe);for(let i=0;i<3;i++)value.actions.push({...structuredClone(value.actions[0]),case_id:'other-'+i,display_name:'其他操作'+i});
  render(<Report {...props(value)}/>)
  const filters=screen.getByRole('group',{name:'按检查结果筛选'})
  fireEvent.click(within(filters).getByRole('button',{name:/^1 符合规则$/}))
  expect(screen.getByRole('button',{name:'查看成员正常下载的依据'})).toBeVisible()
  expect(screen.queryByRole('button',{name:'查看成员导出资料的依据'})).not.toBeInTheDocument()
  expect(within(filters).queryByRole('button',{name:/证据不足/})).not.toBeInTheDocument()
  fireEvent.click(within(filters).getByRole('button',{name:/全部结果/}))
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

it('记录先给出核对结果与已发布判断，数据与采集依据按需展开且不丢失未知判断',async()=>{
  render(<EvidenceRecord value={recordView()}/>)
  expect(screen.getByText('过程调用不能单独证明业务结果。')).toBeVisible()
  expect(screen.getByText('证据不足')).toBeVisible()
  expect(screen.getByText('业务结果的归属尚未确认。')).toBeVisible()
  expect(screen.getByText('app.mjs:9')).not.toBeVisible()
  expect(screen.getByText('宿主在请求内采集。')).not.toBeVisible()
  expect(screen.queryByText(/"operation": "GET"/)).not.toBeInTheDocument()
  fireEvent.click(screen.getByText('查看核对数据'))
  expect(screen.getByText('app.mjs:9')).toBeVisible()
  fireEvent.click(screen.getByText('核对依据与采集范围'))
  expect(screen.getByText('宿主在请求内采集。')).toBeVisible()
  fireEvent.click(screen.getByText('适用范围与封存原文'))
  await waitFor(()=>expect(screen.getByText(/"operation": "GET"/)).toBeVisible())
  expect(screen.getByText('仅覆盖已启用探针。')).toBeVisible()
})

it('业务证明保留前后值与各自含义，不混成过程状态',()=>{
  const value=recordView();value.role='PROOF';value.record.kind='FACT'
  value.values=[{label:'文件内容',before:'abc',after:'def',before_label:'参照文件',after_label:'实际收到'}]
  render(<EvidenceRecord value={value}/>)
  fireEvent.click(screen.getByText('查看核对数据'))
  for(const label of ['业务证明','参照文件','实际收到','abc','def'])expect(screen.getByText(label)).toBeVisible()
})

it('文件内容一致直接阅读服务端核对结果，所属禁止要求的失败结论仍保持原样',()=>{
  const value=recordView();value.role='PROOF';value.record.label='实际接收的文件内容';
  value.summary='实际完整收到的内容与已采用参照一致。';value.published_judgement='不符合规则';
  value.values=[{label:'内容指纹（SHA-256）',before:'a'.repeat(64),after:'a'.repeat(64)}];
  render(<EvidenceRecord value={value}/>);
  expect(screen.getByText(value.summary)).toBeVisible();
  expect(screen.getByText('不符合规则')).toBeVisible();
  expect(screen.getByText('内容指纹（SHA-256）')).not.toBeVisible();
});

it.each([
  ['PASS','本次权限要求已得到验证','本次已执行样本符合权限规则'],
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

it('证明片段按用途阅读，全部索引保留且同名记录进入各自的准确片段',async()=>{
  const response=bundle(),record=recordView().record;
  const records=[
    {...record,record_id:'after',kind:'OBSERVATION',label:'结果观察',phase:'AFTER'},
    {...record,record_id:'before',kind:'OBSERVATION',label:'结果观察',phase:'BEFORE'},
    {...record,record_id:'fact',kind:'FACT',label:'实际收到的文件',phase:null},
    {...record,record_id:'request',kind:'OUTCOME',label:'本次请求',phase:null},
  ];
  vi.spyOn(currentChecksApi,'evidenceBundle').mockResolvedValue({...response,items:[{...response.items[0],index:{...response.items[0].index,records}}]} as never);
  const onLocate=vi.fn();
  render(<EvidenceInspector story={story()} action={story().actions[0]} tab="records" evidenceId="ev1" recordId={null} onLocate={onLocate} onClose={vi.fn()} onError={vi.fn()}/>);
  expect(await screen.findByRole('button',{name:'实际收到的文件 阅读片段'})).toBeVisible();
  expect(screen.getAllByRole('button',{name:/阅读片段/})).toHaveLength(4);
  fireEvent.click(screen.getByRole('button',{name:'结果观察 操作前 阅读片段'}));
  expect(onLocate).toHaveBeenLastCalledWith('records','ev1','before',undefined);
  fireEvent.click(screen.getByRole('button',{name:'结果观察 操作后 阅读片段'}));
  expect(onLocate).toHaveBeenLastCalledWith('records','ev1','after',undefined);
});

it('独立记录只保留当前层级返回，回到片段列表时保留原报告与回程',async()=>{
  const response=bundle(),record=recordView();
  vi.spyOn(currentChecksApi,'evidenceBundle').mockResolvedValue({...response,items:[{...response.items[0],index:{...response.items[0].index,records:[record.record]},record}]} as never);
  render(<Report {...props(story())} selectedCaseId="c1" tab="records" evidenceId="ev1" recordId="call1" returnPath="/issues?issue=original"/>);
  expect(await screen.findByText(record.summary)).toBeVisible();
  fireEvent.click(screen.getByText('查看核对数据'));
  expect(screen.getByText('app.mjs:9')).toBeVisible();
  expect(screen.queryByRole('button',{name:'全部证明片段'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'返回本项业务结果'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'返回证明片段列表'}));
  const query=new URLSearchParams(location.hash.split('?')[1]);
  expect(query.get('run_id')).toBe('r1');expect(query.get('case_id')).toBe('c1');
  expect(query.get('tab')).toBe('records');expect(query.get('evidence_id')).toBe('ev1');
  expect(query.has('record_id')).toBe(false);expect(query.get('return_to')).toBe('/issues?issue=original');
})

it('准确记录与文档一起读取，不再先目录再串行读取详情',async()=>{
  const value=recordView(),response=bundle()
  const item={...response.items[0],index:{...response.items[0].index,records:[value.record]},record:value}
  const read=vi.spyOn(currentChecksApi,'evidenceBundle').mockResolvedValue({...response,items:[item]} as never)
  const separate=vi.spyOn(currentChecksApi,'evidenceRecord')
  render(<Report {...props(story())} selectedCaseId="c1" tab="records" evidenceId="ev1" recordId="call1"/>)
  await waitFor(()=>expect(screen.getByText(value.summary)).toBeVisible())
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
  const value=story();value.verdict='PASS';value.actions[0].case_verdict='SAFE';value.actions[0].judgement='本次权限要求已得到验证';
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
  fireEvent.click(within(prior).getByRole('link',{name:'查看原检查依据'}));
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


it('从比较进入报告后，打开依据仍保留准确比较记录及其上级回程',()=>{
  const value=story()
  const origin='/reports?'+new URLSearchParams({view:'compare',baseline:'run_'+'1'.repeat(32),current:'run_'+'2'.repeat(32),return_to:'/issues?issue=original'})
  render(<Report {...props(value)} returnPath={origin}/> )
  fireEvent.click(screen.getByRole('button',{name:'查看成员导出资料的依据'}))
  const query=new URLSearchParams(location.hash.split('?')[1])
  expect(query.get('run_id')).toBe(value.run_id)
  expect(query.get('case_id')).toBe(value.actions[0].case_id)
  expect(query.get('return_to')).toBe(origin)
})

it('少量结果在原行展开依据，要求与观察只出现一次，深入记录仍保留原报告',()=>{
 const value=story(),p=props(value),view=render(<Report {...p} selectedCaseId="c1"/>)
 expect(screen.queryByRole('group',{name:'按检查结果筛选'})).not.toBeInTheDocument()
 expect(screen.getAllByRole('heading',{name:'成员不得导出资料'})).toHaveLength(1)
 expect(view.container.querySelector('.jj-result-entry .jj-evidence-inspector.is-inline')).toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'操作经过'}))
 expect(location.hash).toContain('case_id=c1');expect(location.hash).toContain('tab=trace')
})

it('归档证据深读与返回始终定位同一归档，不提供写入或模型入口',()=>{
 const value=story(),origin='/archive?project_id='+value.project_id+'&query=内部包'
 render(<Report {...props(value)} readOnly archiveName="数字展馆" basePath={'/archive?project_id='+value.project_id} returnPath={origin}/>)
 expect(screen.queryByRole('button',{name:/Agent/})).not.toBeInTheDocument()
 expect(screen.queryByRole('link',{name:'处理权限问题'})).not.toBeInTheDocument()
 expect(screen.queryByRole('link',{name:'沿用本次范围继续检查'})).not.toBeInTheDocument()
 fireEvent.click(screen.getByRole('button',{name:'查看成员导出资料的依据'}))
 const query=new URLSearchParams(location.hash.split('?')[1])
 expect(location.hash.split('?')[0]).toBe('#/archive')
 expect(query.get('run_id')).toBe(value.run_id)
 expect(query.get('case_id')).toBe('c1')
 expect(query.get('return_to')).toBe(origin)
})

it('离开报告再返回保留原阅读筛选，不把视图偏好当成检查结果',()=>{
 const value=story()
 value.actions=Array.from({length:5},(_,index)=>({...structuredClone(value.actions[0]),case_id:'c'+index}))
 value.actions[0].case_verdict='SAFE'
 value.actions[0].fact_comparison.effects[0].observed_state='ABSENT'
 value.actions[0].fact_comparison.effects[0].assessment_state='ABSENT'
 const p=props(value),view=render(<Report {...p}/>)
 const filters=screen.getByRole('group',{name:'按检查结果筛选'})
 fireEvent.click(within(filters).getByRole('button',{name:'1 符合规则'}))
 expect(within(filters).getByRole('button',{name:'1 符合规则'})).toHaveAttribute('aria-pressed','true')
 expect(view.container.querySelectorAll('.jj-result-entry')).toHaveLength(1)
 view.unmount();render(<Report {...p}/>)
 expect(screen.getByRole('button',{name:'1 符合规则'})).toHaveAttribute('aria-pressed','true')
 expect(screen.getByRole('heading',{name:'4 项结果不符合权限规则'})).toBeVisible()
})
