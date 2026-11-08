import {useEffect,useRef,useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import {routinesApi,type CheckRoutine,type RoutineCatalog,type RoutineScope,type RoutineLimits,type SaveRoutine} from '../../entities/check/api/routines'
import {ruleWorkspaceApi,type RuleItem} from '../../entities/permission/api/ruleWorkspace'
import {businessScenariosApi,type ScenarioSummary} from '../../entities/preparation/api/businessScenarios'
import {editorDraft,rememberEditorDraft} from '../../entities/runtime/model/handoff'
import {useRead} from '../../shared/lib/useRead'
import {useDirectoryState} from '../../shared/lib/directoryState'
import {operationId,readPending,savePending} from '../../shared/lib/operations'
import {go,scopedPath,withReturnDestination,returnDestination,returnDestinationLabel} from '../../shared/lib/navigation'
import {ApiError} from '../../shared/api/http'
import {assertProject,type PageProps} from '../../shared/model/page'
import {date} from '../../shared/lib/format'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Heading,Field} from '../../shared/ui/layout'
import {TaskSurface} from '../../shared/ui/TaskSurface'
import {Choice} from '../../shared/ui/Choice'
import {ObjectTable} from '../../shared/ui/ObjectTable'
import {Inspector} from '../../shared/ui/Inspector'
import {SearchField} from '../../shared/ui/SearchField'
import {Empty,ErrorNote,Loading,Notice,PageError} from '../../shared/ui/feedback'
import {TestingSections} from './TestingSections'
import {RoutinePreparation} from '../../entities/check/ui/RoutinePreparation'
import './routines.css'

const planPath=(id?:string,revision?:number)=>'/testing?'+new URLSearchParams({view:'plans',...(id?{routine_id:id}:{}),...(revision?{routine_revision:String(revision)}:{})})
const runPath=(id:string,revision:number)=>'/reports?'+new URLSearchParams({view:'plan',routine_id:id,routine_revision:String(revision),return_to:planPath()})
type Draft={name:string;scope:RoutineScope;limits:RoutineLimits;section:string}
const values=(draft:Pick<Draft,'name'|'scope'|'limits'>)=>JSON.stringify({name:draft.name,scope:draft.scope,limits:draft.limits})

export function CheckRoutines(props:PageProps){
 const id=props.route.query.get('routine_id'),revision=Number(props.route.query.get('routine_revision'))
 const state=useRead('routine-workspace:'+props.projectId,async()=>{
  const [catalog,rules,scenarios]=await Promise.all([routinesApi.catalog(props.projectId),ruleWorkspaceApi.read(props.projectId),businessScenariosApi.list(props.projectId)])
  for(const item of [catalog,rules,scenarios])assertProject(item.project_id,props.projectId)
  return {catalog,rules:rules.rules,scenarios:scenarios.documents}
 })
 const document=useRead(id&&id!=='new'&&Number.isInteger(revision)&&revision>0?'routine:'+props.projectId+':'+id+':'+revision:null,async()=>{
  const value=await routinesApi.read(props.projectId,id!,revision);assertProject(value.project_id,props.projectId)
  if(value.routine_id!==id||value.revision!==revision||value.schema_version!=='2')throw new Error('检查方案修订与当前位置不一致。')
  return value
 })
 if(id&&id!=='new'&&(!Number.isInteger(revision)||revision<1))return <PageError title="检查方案" error={new Error('缺少准确的方案修订，请返回方案目录。')}/>
 if(state.loading||id&&id!=='new'&&document.loading)return <Loading page/>
 if(!state.data||state.error)return <PageError title="检查方案" error={state.error}/>
 if(id&&id!=='new'&&!document.data)return <PageError title="检查方案修订不存在" error={document.error}/>
 if(id)return <RoutineEditor key={props.projectId+':'+id+':'+revision} {...props} document={document.data} rules={state.data.rules} scenarios={state.data.scenarios} catalog={state.data.catalog}/>
 return <RoutineDirectory {...props} catalog={state.data.catalog} rules={state.data.rules} scenarios={state.data.scenarios}/>
}

function RoutineDirectory({projectId,catalog,rules,scenarios}:PageProps&{catalog:RoutineCatalog;rules:RuleItem[];scenarios:ScenarioSummary[]}){
 const root=useRef<HTMLElement>(null)
 const [extra,setExtra]=useState<RoutineCatalog['routines']>([]),[cursor,setCursor]=useState(catalog.next_cursor),[moreBusy,setMoreBusy]=useState(false),[moreError,setMoreError]=useState<unknown>()
 useEffect(()=>{setExtra([]);setCursor(catalog.next_cursor)},[catalog])
 const directory=useDirectoryState('jiejian.directory:'+projectId+':routines',{query:'',selectedId:'',open:true as boolean},true,root)
 const {query}=directory.value
 const loaded=[...catalog.routines,...extra],rows=loaded.filter(item=>item.name.includes(query))
 const selected=rows.find(item=>item.routine_id===directory.value.selectedId)??rows[0]
 const open=Boolean(selected)&&directory.value.open
 const single=loaded.length===1&&!cursor&&!query
 const close=()=>{directory.update({open:false});requestAnimationFrame(()=>root.current?.querySelector<HTMLButtonElement>('.jj-object-select[aria-pressed=true]')?.focus({preventScroll:true}))}
 const more=async()=>{if(!cursor||moreBusy)return;setMoreBusy(true);setMoreError(undefined);try{const value=await routinesApi.catalog(projectId,undefined,cursor);assertProject(value.project_id,projectId);setExtra(items=>[...items,...value.routines.filter(next=>!loaded.some(item=>item.routine_id===next.routine_id))]);setCursor(value.next_cursor)}catch(error){setMoreError(error)}finally{setMoreBusy(false)}}
 return <><Heading title="检查方案" actions={loaded.length>0&&<ActionLink navigationScope="page" href={'#'+scopedPath(planPath('new'),projectId)}  kind="default">新建方案</ActionLink>}>将经常检查的内容保存为方案。下次从这里继续，核对本次应用连接和材料后，再开始检查。</Heading><TestingSections value="plans" projectId={projectId}/>
  {Boolean(loaded.length>1||query||cursor)&&<div className="jj-workspace-toolbar"><SearchField label="查找已载入方案" placeholder="查找已载入方案名称" value={query} onValueChange={query=>directory.update({query})}/><span className="jj-small jj-muted">已载入 {loaded.length} 份方案{query?' · 匹配 '+rows.length+' 份':''}</span></div>}
  {single?<section ref={root} className="jj-routine-single"><header><h2 tabIndex={-1} data-directory-id={selected.routine_id}>{selected.name}</h2><span className="jj-small jj-muted">第 {selected.revision} 修订 · {date(selected.created_at_us)}</span></header><RoutineOverview projectId={projectId} id={selected.routine_id} revision={selected.revision} rules={rules} scenarios={scenarios}/><footer className="jj-routine-actions"><ActionLink onClick={()=>directory.remember(selected.routine_id)} href={'#'+scopedPath(planPath(selected.routine_id,selected.revision),projectId)}>编辑检查内容</ActionLink><ActionLink kind="primary" onClick={()=>directory.remember(selected.routine_id)} href={'#'+scopedPath(runPath(selected.routine_id,selected.revision),projectId)}>准备这次检查</ActionLink></footer></section>:rows.length?<section ref={root} className="jj-collection jj-routine-directory" data-detail-open={open}><div className="jj-collection-layout"><div className="jj-collection-main"><ObjectTable selection={open?selected.routine_id:''}><thead><tr><th>检查方案</th><th>检查内容</th><th className="jj-object-summary">保存时间</th></tr></thead><tbody>{rows.map(item=><tr key={item.routine_id} data-selected={item.routine_id===selected.routine_id}><th scope="row"><button className="jj-object-select" data-directory-id={item.routine_id} aria-pressed={item.routine_id===selected.routine_id} onClick={()=>directory.update({selectedId:item.routine_id,open:true})}><strong>{item.name}</strong><small>第 {item.revision} 修订</small></button></th><td className="jj-object-meta">{item.scope_kind==='SCENARIO'?'业务场景':item.permission_count+' 条权限规则'}</td><td className="jj-object-summary jj-object-meta">{date(item.created_at_us)}</td></tr>)}</tbody></ObjectTable></div>{open&&<Inspector identity={selected.routine_id+':'+selected.revision} title={selected.name} caption={'第 '+selected.revision+' 修订'} status={null} onClose={close} actions={<><ActionLink onClick={()=>directory.remember(selected.routine_id)} href={'#'+scopedPath(planPath(selected.routine_id,selected.revision),projectId)}>编辑检查内容</ActionLink><ActionLink kind="primary" onClick={()=>directory.remember(selected.routine_id)} href={'#'+scopedPath(runPath(selected.routine_id,selected.revision),projectId)}>准备这次检查</ActionLink></>}><RoutineOverview projectId={projectId} id={selected.routine_id} revision={selected.revision} rules={rules} scenarios={scenarios}/></Inspector>}</div></section>:<Empty title={query?'没有匹配的方案':'先保存一份日常检查方案'} action={!query&&<ActionLink navigationScope="page" href={'#'+scopedPath(planPath('new'),projectId)} kind="primary">新建方案</ActionLink>}>方案会保留每次保存的内容；更换应用地址或材料后，需要重新确认本次准备。</Empty>}
  {catalog.legacy_selections.length>0&&<details className="jj-routine-legacy"><summary>旧保存范围 · {catalog.legacy_selections.length} 份</summary><p>这些记录仅保存规则选择。另存为完整方案时会明确保存当前规则修订。</p>{catalog.legacy_selections.map(item=><div key={item.routine_id}><strong>{item.name}</strong><ActionLink navigationScope="page" href={'#'+scopedPath(planPath('new')+'&from_legacy='+encodeURIComponent(item.routine_id),projectId)}  kind="default">另存为完整方案</ActionLink></div>)}</details>}
  {Boolean(moreError)&&<ErrorNote error={moreError}/>}{cursor&&<footer className="jj-routine-actions"><span className="jj-small jj-muted">继续查看已保存的检查方案。</span><Button busy={moreBusy} onClick={()=>void more()}>载入更多方案</Button></footer>}
 </>
}

/** 浏览目录只读取准确保存内容；材料是否可用仍由准备工作面核对。 */
function RoutineOverview({projectId,id,revision,rules,scenarios}:{projectId:string;id:string;revision:number;rules:RuleItem[];scenarios:ScenarioSummary[]}){
 const state=useRead('routine-overview:'+projectId+':'+id+':'+revision,async()=>{
  const value=await routinesApi.read(projectId,id,revision);assertProject(value.project_id,projectId)
  if(value.routine_id!==id||value.revision!==revision||value.schema_version!=='2')throw new Error('保存内容与所选方案修订不一致。')
  return value
 })
 const value=state.data
 if(!value)return state.loading?<Loading/>:<div className="jj-routine-overview"><ErrorNote error={state.error}/><Button onClick={state.reload}>重新读取方案</Button></div>
 const scene=value.scope.scenario,scenario=scene&&scenarios.find(item=>item.id===scene.scenario_id&&item.revision===scene.revision)
 const labels=value.scope.permissions.map(ref=>({id:ref.intent_id,title:rules.find(item=>item.permission.intent_id===ref.intent_id&&item.permission.revision===ref.revision&&item.permission.intent_hash===ref.intent_hash)?.title??'保存时的权限要求（当前规则已变化，请编辑核对）'}))
 const requirements=value.requirements??[]
 return <div className="jj-routine-overview"><section><h3>这份方案检查什么</h3>{scene?<p>{scenario?.label??'保存时选定的业务场景'} · 第 {scene.revision} 修订</p>:<><ul className="jj-routine-scope-list">{labels.slice(0,6).map(item=><li key={item.id}>{item.title}</li>)}</ul>{labels.length>6&&<details><summary>其余 {labels.length-6} 条权限要求</summary><ul className="jj-routine-scope-list">{labels.slice(6).map(item=><li key={item.id}>{item.title}</li>)}</ul></details>}</>}</section><section><h3>开始前还要确认</h3><p>下一步核对本次应用连接、账号、操作步骤和结果证明。准备完成后，查看检查范围与执行安排，再开始检查。</p>{requirements.length>0&&<details><summary>方案所需的材料</summary><ul className="jj-routine-scope-list">{requirements.map(item=><li key={item.slot}>{item.label}{item.minimum_count>1?' · 至少 '+item.minimum_count+' 份':''}</li>)}</ul></details>}</section><p className="jj-small jj-muted">一次最多运行 {value.limits.max_duration_us/1_000_000} 秒、检查 {value.limits.max_cases} 个场景。浏览方案不会发送应用请求。</p>{Boolean(state.error)&&<ErrorNote error={state.error}/>}</div>
}

function RoutineEditor({projectId,route,refresh,document,rules,scenarios,catalog}:PageProps&{document?:CheckRoutine;rules:RuleItem[];scenarios:ScenarioSummary[];catalog:RoutineCatalog}){
 const origin=returnDestination(route.query.get('return_to'))
 const legacyId=route.query.get('from_legacy'),legacy=catalog.legacy_selections.find(item=>item.routine_id===legacyId)
 const identity=(document?.routine_id??'new')+':'+(document?.revision??0)+(legacyId?':'+legacyId:'')
 const draftKey='routine-draft:'+projectId+':'+identity,pendingKey='jiejian.routine-save:'+projectId+':'+identity
 const pendingInitial=readPending<SaveRoutine>(pendingKey)
 const restored=useRef(editorDraft<Draft>(draftKey,projectId))
 const invalidLegacy=Boolean(legacyId&&!legacy&&!pendingInitial&&!restored.current)
 const [draft,setDraft]=useState<Draft>(()=>({... (restored.current??{
  name:pendingInitial?.name??document?.name??legacy?.name??'日常权限检查',
  scope:pendingInitial?.scope??document?.scope??{permissions:legacy?.selected_permissions??rules.map(item=>item.permission),scenario:null},
  limits:pendingInitial?.limits??document?.limits??{max_duration_us:300_000_000,max_cases:8192},section:'content'}),section:route.query.get('section')??restored.current?.section??'content'}))
 const [pending,setPending]=useState(pendingInitial),[busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),lock=useRef(false)
 const [historyOpen,setHistoryOpen]=useState(draft.section==='history'),limitsRef=useRef<HTMLElement>(null),historyRef=useRef<HTMLDetailsElement>(null)
 const mounted=useRef(true)
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[])
 const dirty=!document||values(draft)!==values(document)
 // 同一对象的外部深链接也要切换实际工作面，不能只改变地址而沿用旧分类。
 const requestedSection=route.query.get('section')
 useEffect(()=>{if(requestedSection&&['content','binding','limits','history'].includes(requestedSection))setDraft(current=>current.section===requestedSection?current:{...current,section:requestedSection})},[requestedSection])
 // 保留旧分类深链接的定位语义；短配置已经合并进检查内容。
 useEffect(()=>{
  if(draft.section==='history')setHistoryOpen(true)
  const target=draft.section==='limits'?limitsRef.current:draft.section==='history'?historyRef.current:null
  if(target){target.focus({preventScroll:true});target.scrollIntoView?.({block:'nearest'})}
 },[draft.section])
 useEffect(()=>{if(!invalidLegacy)rememberEditorDraft(draftKey,draft,projectId)},[draftKey,draft,projectId,invalidLegacy])
 const change=(patch:Partial<Draft>)=>setDraft(current=>({...current,...patch}))
 const stale=draft.scope.permissions.filter(ref=>!rules.some(item=>item.permission.intent_id===ref.intent_id&&item.permission.revision===ref.revision&&item.permission.intent_hash===ref.intent_hash))
 const save=async()=>{
  if(lock.current)return;lock.current=true;setBusy(true);setError(undefined)
  const command=pending??{operation_id:operationId(),...(document||legacyId?{routine_id:document?.routine_id??legacyId!}:{}),expected_revision:document?.revision??0,name:draft.name.trim(),scope:draft.scope,limits:draft.limits}
  savePending(pendingKey,command);setPending(command)
  // 成功回执仍清理原草稿；离开工作面后不把用户强行导航回异步保存的对象。
  try{const saved=await routinesApi.save(projectId,command);assertProject(saved.project_id,projectId);savePending(pendingKey,undefined);rememberEditorDraft(draftKey,undefined);refresh();if(mounted.current)go(origin?withReturnDestination(planPath(saved.routine_id,saved.revision),origin):planPath(saved.routine_id,saved.revision),projectId)}
  catch(error){setError(error);if(error instanceof ApiError&&['INPUT_INVALID','STATE_PRECONDITION','RECORD_NOT_FOUND'].includes(error.code)){savePending(pendingKey,undefined);setPending(undefined)}}
  finally{lock.current=false;setBusy(false)}
 }
 if(invalidLegacy)return <PageError title="没有找到原来的检查范围" error={new Error('请返回方案目录核对原来的范围，本次仍保留原选择。')}/>
 const toggle=(rule:RuleItem,checked:boolean)=>change({scope:{permissions:checked?[...draft.scope.permissions,rule.permission]:draft.scope.permissions.filter(ref=>ref.intent_id!==rule.permission.intent_id),scenario:null}})
 const blocked=busy||Boolean(pending)
 if(draft.section==='binding')return <TaskSurface title="准备这次检查" context={document?.name} onBack={()=>{change({section:'content'});const query=new URLSearchParams(route.query);query.delete('section');go('/testing?'+query,projectId)}} backLabel="返回方案编辑">{document?<RoutinePreparation projectId={projectId} document={document} dirty={dirty} initialSlot={route.query.get('binding_slot')} origin={planPath(document.routine_id,document.revision)+'&section=binding'}/>:<Notice>先保存检查内容，再确认这次要检查的应用和所需材料。</Notice>}</TaskSurface>;
 return <><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin??planPath(),projectId)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{origin?returnDestinationLabel(origin):'返回检查方案'}</ActionLink></div><Heading title={document?.name??'新建检查方案'}>{document?(dirty?'这份方案有未保存的修改，保存后再继续检查。':'已保存。下次检查可以沿用这些要求，再核对本次使用的应用地址和材料。'):'为常用的检查内容起个名字，选择已经确认的权限要求。保存方案不会立即检查应用。'}</Heading>

  {pending&&!busy&&<Notice tone="caution">上次保存的结果还未确认。继续保存会沿用原内容和请求，当前草稿会保留。</Notice>}
  <div className="jj-routine-editor">
  {draft.section!=='binding'&&<div className="jj-routine-definition"><div className="jj-routine-definition-scope"><Field label="方案名称"><input value={draft.name} disabled={blocked} maxLength={80} onChange={e=>change({name:e.target.value})}/></Field>
   {legacyId&&<Notice>这份旧记录仅保存规则范围；保存后建立第一份完整方案修订。</Notice>}
   {!rules.length&&!draft.scope.scenario&&<Notice>还没有已批准的权限规则。请先到“权限与覆盖”确认检查要求。<ActionLink href={'#'+scopedPath('/permissions',projectId)}>维护权限规则</ActionLink></Notice>}
   <p className="jj-routine-explanation">权限要求已在“权限与覆盖”中确认。这里选择本方案需要检查的内容；要改变权限含义，请返回原规则审阅。</p><Field label="检查范围"><Choice value={draft.scope.scenario?'scenario':'permissions'} disabled={blocked} onValueChange={mode=>change({scope:mode==='scenario'?{permissions:[],scenario:scenarios[0]?{scenario_id:scenarios[0].id,revision:scenarios[0].revision}:null}:{permissions:rules.map(item=>item.permission),scenario:null}})}><option value="permissions">选定权限规则</option><option value="scenario" disabled={!scenarios.length}>已保存的业务场景</option></Choice></Field>
   {draft.scope.scenario?<Field label="业务场景"><Choice value={draft.scope.scenario.scenario_id+'@'+draft.scope.scenario.revision} disabled={blocked} onValueChange={value=>{const item=scenarios.find(item=>item.id+'@'+item.revision===value);if(item)change({scope:{permissions:[],scenario:{scenario_id:item.id,revision:item.revision}}})}}>{!scenarios.some(item=>item.id===draft.scope.scenario?.scenario_id&&item.revision===draft.scope.scenario?.revision)&&<option value={draft.scope.scenario.scenario_id+'@'+draft.scope.scenario.revision}>原场景 · 第 {draft.scope.scenario.revision} 修订</option>}{scenarios.map(item=><option key={item.id} value={item.id+'@'+item.revision}>{item.label} · 第 {item.revision} 修订</option>)}</Choice></Field>:<fieldset className="jj-routine-rules" disabled={blocked}><legend>本方案需要检查哪些权限要求</legend>{rules.map(rule=><label className="jj-checkbox" key={rule.permission.intent_id}><input type="checkbox" checked={draft.scope.permissions.some(ref=>ref.intent_id===rule.permission.intent_id)} onChange={e=>toggle(rule,e.target.checked)}/><span>{rule.title}</span></label>)}</fieldset>}
   {stale.length>0&&<Notice tone="caution">保存的范围中有 {stale.length} 条规则已变化。请核对当前规则并重新选择；保存前不会替换旧引用。<Button onClick={()=>change({scope:{permissions:draft.scope.permissions.filter(ref=>!stale.includes(ref)),scenario:null}})}>移除失效选择</Button></Notice>}
  </div><section ref={limitsRef} tabIndex={-1} className="jj-routine-definition-limits" aria-labelledby="routine-limits-title"><h2 id="routine-limits-title">运行上限</h2><p className="jj-routine-explanation">为检查设置执行上限，避免一次运行持续过久或包含过多场景。目标应用自身的超时、请求和恢复约束仍然有效。</p><Field label="最长运行时间（秒）" hint="请求次数、单次超时和响应大小继续受当前环境约束。"><input type="number" min={1} max={3600} disabled={blocked} value={draft.limits.max_duration_us/1_000_000} onChange={e=>change({limits:{...draft.limits,max_duration_us:Number(e.target.value)*1_000_000}})}/></Field><Field label="最多检查场景"><input type="number" min={1} max={8192} disabled={blocked} value={draft.limits.max_cases} onChange={e=>change({limits:{...draft.limits,max_cases:Number(e.target.value)}})}/></Field></section></div>}

  {draft.section!=='binding'&&document&&<details ref={historyRef} tabIndex={-1} className="jj-routine-history" open={historyOpen} onToggle={event=>setHistoryOpen(event.currentTarget.open)}><summary>查看这份方案的保存记录</summary>{historyOpen&&<RoutineHistory projectId={projectId} document={document}/>}</details>}
  </div>{Boolean(error)&&<ErrorNote error={error}/>}
  {(draft.section!=='binding'||dirty)&&<footer className="jj-routine-actions"><span className="jj-small jj-muted">{dirty?'离开后仍会保留这份草稿；保存不会开始检查。':'已保存的检查内容可以继续使用。'}</span>{!dirty&&document&&draft.section!=='binding'?<ActionLink kind="primary" href={'#'+scopedPath(runPath(document.routine_id,document.revision),projectId)}>准备这次检查</ActionLink>:<Button kind="primary" busy={busy} disabled={!pending&&(!dirty||!draft.name.trim()||!draft.scope.scenario&&!draft.scope.permissions.length||Boolean(stale.length))} onClick={()=>void save()}>{busy?'正在保存':pending?'继续上次保存':document?'保存修改':'保存方案'}</Button>}</footer>}
 </>
}

function RoutineHistory({projectId,document}:{projectId:string;document:CheckRoutine}){
 const state=useRead('routine-history:'+projectId+':'+document.routine_id+':'+document.revision,()=>routinesApi.history(projectId,document.routine_id))
 const [extra,setExtra]=useState<Array<{revision:number;name:string;created_at_us:number}>>([]),[busy,setBusy]=useState(false),[exhausted,setExhausted]=useState(false),[error,setError]=useState<unknown>()
 const rows=[...(state.data??[]),...extra],more=async()=>{if(!rows.length||busy)return;setBusy(true);setError(undefined);try{const values=await routinesApi.history(projectId,document.routine_id,rows[rows.length-1].revision);setExtra(items=>[...items,...values]);setExhausted(values.length<50)}catch(error){setError(error)}finally{setBusy(false)}}
 return <><h2>这份方案的保存记录</h2><p>每次保存都会保留当时的检查内容。查看旧记录不会覆盖后来的修改，也不会重写已有报告。</p>{rows.map(item=><div className="jj-routine-history-row" key={item.revision}><span>第 {item.revision} 修订 · {item.name}</span><ActionLink href={'#'+scopedPath(planPath(document.routine_id,item.revision),projectId)}>查看当时的内容</ActionLink></div>)}{Boolean(state.error??error)&&<ErrorNote error={state.error??error}/>}{!exhausted&&(state.data?.length??0)>=50&&<footer className="jj-routine-actions"><Button busy={busy} onClick={()=>void more()}>载入更早修订</Button></footer>}</>
}

