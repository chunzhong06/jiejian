import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import {prefixedId as id} from '../../shared/lib/id'
import {useEffect,useRef,useState} from 'react'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined'
import PlusOutlined from '@ant-design/icons/PlusOutlined'
import {businessScenariosApi as api,type BusinessScenario,type ScenarioContext,type ScenarioExperiment,type ScenarioInvocation,type ScenarioItem} from '../../entities/preparation/api/businessScenarios'
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection,requestCollaboration,useHandoffContext} from '../../entities/runtime/model/handoff'
import {useRead} from '../../shared/lib/useRead'
import {go,scopedPath,withReturnDestination} from '../../shared/lib/navigation'
import {useDirectoryState} from '../../shared/lib/directoryState'
import {ApiError} from '../../shared/api/http'
import {assertProject,type PageProps} from '../../shared/model/page'
import {Button,ActionLink} from '../../shared/ui/actions'
import {ObjectTable} from '../../shared/ui/ObjectTable'
import {Inspector} from '../../shared/ui/Inspector'
import './scenario-directory.css'
import {Choice} from '../../shared/ui/Choice'
import {Tabs} from '../../shared/ui/Tabs'
import {IndexActions,IndexSelection} from '../../shared/ui/IndexSelection'
import {Field,Heading,SectionHeading} from '../../shared/ui/layout'
import {Empty,ErrorNote,Loading,PageError} from '../../shared/ui/feedback'
import {ScenarioResources,matchesScenarioItem} from './ScenarioResources'
import {ScenarioNodeTrial} from './ScenarioNodeTrial'
import {TestingSections} from './TestingSections'
import {scenarioDebugSnapshot} from './scenarioDebug'

const kinds={NORMAL:'正常业务',OMIT:'省略步骤',REORDER:'调整顺序',REPEAT:'重复动作',CHANGE_SUBJECT:'更换账号后继续',REVOKE:'撤销后继续'} as const
const canonical=(value:unknown):unknown=>Array.isArray(value)?value.map(canonical):value!==null&&typeof value==='object'?Object.fromEntries(Object.entries(value).sort(([left],[right])=>left.localeCompare(right)).map(([key,item])=>[key,canonical(item)])):value

export function BusinessScenarios(props:PageProps){
  const selected=props.route.query.get('scenario')
  const revision=Number(props.route.query.get('revision'))
  const listing=useRead('business-scenarios:'+props.projectId,signal=>api.list(props.projectId,signal))
  const latest=listing.data?.documents.find(item=>item.id===selected)
  const exactRevision=Number.isInteger(revision)&&revision>0?revision:latest?.revision
  const editing=selected!=='list'
  const state=useRead(editing?'business-scenario-context:'+props.projectId:null,signal=>api.context(props.projectId,signal))
  const history=useRead(editing&&selected?.startsWith('bsc_')&&exactRevision?'business-scenario:'+props.projectId+':'+selected+':'+exactRevision:null,()=>api.read(props.projectId,selected!,exactRevision!))
  if(listing.loading&&!listing.data)return <PageSkeleton view="/testing" title="业务场景"/>
  if(!listing.data)return <PageError title="业务场景" error={listing.error}/>
  if(editing){
    if(state.loading&&!state.data||selected!=='new'&&history.loading&&!history.data)return <PageSkeleton view="/testing" title="组合业务场景"/>
    if(!state.data||selected!=='new'&&!history.data)return <PageError title="组合业务场景" error={state.error??history.error??new Error('这份场景不存在，可返回测试目录选择当前修订。')}/>
    const document=history.data
    return <ScenarioEditor key={props.projectId+':'+(document?.id??'new')+':'+document?.revision} projectId={props.projectId} context={state.data} initial={document} historical={Boolean(document&&(!latest||document.revision<latest.revision))}/>
  }
  return <ScenarioDirectory {...props} documents={listing.data.documents} error={listing.error}/>
}

function ScenarioDirectory({projectId,documents,error}:PageProps&{documents:import('../../entities/preparation/api/businessScenarios').ScenarioSummary[];error?:unknown}){
 const root=useRef<HTMLElement>(null)
 const directory=useDirectoryState('jiejian.directory:'+projectId+':scenarios',{selectedId:'',open:true as boolean},true,root)
 const selected=documents.find(item=>item.id===directory.value.selectedId)??documents[0],open=Boolean(selected)&&directory.value.open
 const close=()=>{directory.update({open:false});requestAnimationFrame(()=>root.current?.querySelector<HTMLButtonElement>('.jj-object-select[aria-pressed=true]')?.focus({preventScroll:true}))}
 const contextPath='/testing?scenario=list'
 const actions=selected?<><ActionLink onClick={()=>directory.remember(selected.id)} href={'#'+scopedPath('/testing?'+new URLSearchParams({scenario:selected.id,revision:String(selected.revision)}),projectId)}>编辑场景</ActionLink><ActionLink kind="primary" onClick={()=>directory.remember(selected.id)} href={'#'+scopedPath(withReturnDestination('/reports?'+new URLSearchParams({view:'plan',scenario_id:selected.id,scenario_revision:String(selected.revision)}),contextPath),projectId)}>核对检查范围</ActionLink></>:null
 return <><Heading title="业务场景" actions={documents.length>0&&<ActionLink navigationScope="page" href={'#'+scopedPath('/testing?scenario=new')}  kind="default">组合业务场景<PlusOutlined aria-hidden="true"/></ActionLink>}>{documents.length>0?'组合业务操作，检查跳过步骤、重复操作或更换账号时的访问权限。':undefined}</Heading><TestingSections value="scenarios" projectId={projectId}/>{Boolean(error)&&<ErrorNote error={error}/>}
 {documents.length===1?<section ref={root} className="jj-scenario-single"><header><h2 tabIndex={-1} data-directory-id={selected.id}>{selected.label}</h2><span className="jj-small jj-muted">第 {selected.revision} 修订</span></header><ScenarioOverview projectId={projectId} id={selected.id} revision={selected.revision}/><footer>{actions}</footer></section>:documents.length?<section ref={root} className="jj-collection jj-scenario-directory" data-detail-open={open}><div className="jj-collection-layout"><div className="jj-collection-main"><ObjectTable selection={open?selected.id:''}><thead><tr><th>业务场景</th><th>实验</th></tr></thead><tbody>{documents.map(item=><tr key={item.id} data-selected={item.id===selected.id}><th scope="row"><button className="jj-object-select" data-directory-id={item.id} aria-pressed={item.id===selected.id} onClick={()=>directory.update({selectedId:item.id,open:true})}><strong>{item.label}</strong><small>第 {item.revision} 修订</small><small className="jj-object-summary">{item.description}</small></button></th><td className="jj-object-meta">{item.experiment_count} 项</td></tr>)}</tbody></ObjectTable></div>{open&&<Inspector identity={selected.id+':'+selected.revision} title={selected.label} caption={'第 '+selected.revision+' 修订'} status={null} onClose={close} actions={actions}><ScenarioOverview projectId={projectId} id={selected.id} revision={selected.revision}/></Inspector>}</div></section>:<Empty layout="section" title="还没有业务场景" action={<ActionLink navigationScope="page" href={'#'+scopedPath('/testing?scenario=new')} kind="primary">选择已有动作<ArrowRightOutlined aria-hidden="true"/></ActionLink>}>把多个已准备的操作排成业务流程，再验证跳步、重复操作或更换账号的影响。日常固定范围可保存为检查方案，单个请求在接口流程中设置。</Empty>}</>
}

function ScenarioOverview({projectId,id,revision}:{projectId:string;id:string;revision:number}){
 const [experimentId,setExperimentId]=useState('')
 const state=useRead('scenario-overview:'+projectId+':'+id+':'+revision,async()=>{
  const value=await api.read(projectId,id,revision);assertProject(value.project_id,projectId)
  if(value.id!==id||value.revision!==revision)throw new Error('业务场景内容与所选修订不一致。')
  return value
 })
 if(!state.data)return state.loading?<Loading/>:<div className="jj-scenario-overview"><ErrorNote error={state.error}/><Button onClick={state.reload}>重新读取场景</Button></div>
 // 多项变体逐项阅读，避免少量目录行被全部实验正文拉成长侧栏。
 const experiment=state.data.experiments.find(item=>item.id===experimentId)??state.data.experiments[0]
 return <div className="jj-scenario-overview">{state.data.description&&<p>{state.data.description}</p>}<Field label="查看实验安排"><Choice value={experiment.id} onValueChange={setExperimentId}>{state.data.experiments.map(item=><option key={item.id} value={item.id}>{item.label}</option>)}</Choice></Field><section><h3>{experiment.label}</h3><p className="jj-small jj-muted">{kinds[experiment.kind]}{experiment.kind==='NORMAL'?' · 保留完整流程作为正常对照':' · 与正常流程一起核对权限与业务结果'}</p><ol>{experiment.invocations.map(item=><li key={item.id}>{item.label}{item.batch?'（批量操作）':''}</li>)}</ol></section>{Boolean(state.error)&&<ErrorNote error={state.error}/>}</div>
}

function ScenarioEditor({projectId,context,initial,historical}:{projectId:string;context:ScenarioContext;initial?:BusinessScenario;historical:boolean}){
  const key='scenario-editor:'+projectId+':'+(initial?.id??'new')+':'+(initial?.revision??0)
  const restored=editorDraft<{document:BusinessScenario;basis:number;uncertain?:BusinessScenario;debugUncertain?:BusinessScenario}>(key,projectId)
  const [document,setDocument]=useState<BusinessScenario>(()=>restored?.document??initial??{document_type:'jiejian.business-scenario',schema_version:'1',id:'bsc_'+crypto.randomUUID().replaceAll('-',''),project_id:projectId,revision:1,label:'',description:'',experiments:[{id:'normal',label:'正常业务',kind:'NORMAL',control_experiment_id:null,invocations:[]}]})
  const [basis,setBasis]=useState(restored?.basis??initial?.revision??0),[uncertain,setUncertain]=useState(restored?.uncertain)
  const [experimentId,setExperimentId]=useState(document.experiments[0].id),[invocationId,setInvocationId]=useState('')
  const [trial,setTrial]=useState(false)
  const [debugUncertain,setDebugUncertain]=useState(restored?.debugUncertain)
  const [busy,setBusy]=useState(false),[error,setError]=useState<unknown>(),[variant,setVariant]=useState<ScenarioExperiment['kind']>('OMIT')
  const completed=useRef(false)
  const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[])
  const initialContent=useRef(JSON.stringify(document)).current
  useDraftProtection(JSON.stringify(document)!==initialContent)
  useEffect(()=>{if(!completed.current)rememberEditorDraft(key,{document,basis,uncertain,debugUncertain},projectId)},[key,projectId,document,basis,uncertain,debugUncertain])
  const experiment=document.experiments.find(item=>item.id===experimentId)??document.experiments[0]
  const current=experiment.invocations.find(item=>item.id===invocationId)??experiment.invocations[0]
  const available=context.actions.flatMap(action=>action.cases.map(value=>({action,value}))).filter((item,index,all)=>all.findIndex(other=>other.value.permission.intent_id===item.value.permission.intent_id&&other.value.subject_test_identity_id===item.value.subject_test_identity_id&&other.value.resource_id===item.value.resource_id)===index)
  const currentOption=current?.items.length===1?available.find(option=>matchesScenarioItem(current.items[0],option)):undefined
  const canTrial=Boolean(currentOption?.action.trial_flow&&!currentOption.action.creates_resource&&currentOption.value.subject_test_identity_id&&!current?.batch&&!current?.items[0].resource_from)
  const options=available.filter(item=>experiment.kind!=='NORMAL'||item.value.permission.expectation==='ALLOW')
  const disabled=busy||Boolean(uncertain)||Boolean(debugUncertain)||historical
  const update=(value:Partial<BusinessScenario>)=>setDocument(before=>({...before,...value}))
  const updateExperiment=(value:Partial<ScenarioExperiment>)=>update({experiments:document.experiments.map(item=>item.id===experiment.id?{...item,...value}:item)})
  const setInvocations=(values:ScenarioInvocation[])=>updateExperiment({invocations:experiment.kind==='NORMAL'?values.map((item,index)=>({...item,depends_on:index?[values[index-1].id]:[]})):values})
  const updateInvocation=(patch:Partial<ScenarioInvocation>)=>setInvocations(experiment.invocations.map(item=>item.id===current.id?{...item,...patch}:item))
  const newItem=(value=options[0]?.value):ScenarioItem=>({id:id('item_'),permission:{intent_id:value.permission.intent_id,revision:value.permission.revision,intent_hash:value.permission.intent_hash},subject_identity_id:value.subject_test_identity_id,resource_id:value.resource_id})
  const addInvocation=()=>{if(!options.length)return;const invocation={id:id('step_'),label:options[0].action.label,items:[newItem()],depends_on:[],batch:null};setInvocations([...experiment.invocations,invocation]);setInvocationId(invocation.id)}
  const ready=Boolean(document.label.trim()&&document.experiments.every(item=>item.invocations.length&&item.invocations.every(node=>{
    const matches=node.items.map(value=>available.find(option=>matchesScenarioItem(value,option)))
    return matches.length>0&&matches.every(Boolean)&&(!node.batch||node.batch.array_path.length&&node.batch.array_path.every(part=>typeof part==='number'||/^[A-Za-z_][A-Za-z0-9_]*$/.test(part))&&matches.every(option=>option!.action.action_id===matches[0]!.action.action_id&&option!.value.subject_test_identity_id===matches[0]!.value.subject_test_identity_id))
  })))
  const target={...document,revision:basis+1}
  const debug=async(through?:string)=>{
    setBusy(true);setError(undefined)
    try{
      const snapshot=debugUncertain??scenarioDebugSnapshot(document,experiment,'bsc_'+crypto.randomUUID().replaceAll('-',''),through)
      setDebugUncertain(snapshot)
      const saved=debugUncertain?await api.read(projectId,snapshot.id,snapshot.revision):await api.save(projectId,snapshot)
      if(JSON.stringify(canonical(saved))!==JSON.stringify(canonical(snapshot)))throw new Error('调试修订与草稿不一致，请保留草稿并核对已保存场景。')
      setDebugUncertain(undefined)
      go('/reports?'+new URLSearchParams({view:'plan',scenario_id:saved.id,scenario_revision:String(saved.revision),return_to:'/testing?scenario='+saved.id}))
    }catch(value){if(value instanceof ApiError&&!['API_VERSION_UNSUPPORTED','READ_TIMEOUT'].includes(value.code))setDebugUncertain(undefined);setError(value)}finally{setBusy(false)}
  }
  useHandoffContext({projectId,label:(document.label||'业务场景')+' · 组合草稿',references:{return_to:'/testing?scenario='+document.id},editor:{kind:'SCENARIO',document:target}})
  const save=async()=>{
    if(disabled||!ready)return
    setBusy(true);setError(undefined);setUncertain(target)
    const submitted=editorDraftGeneration(key,projectId);
    try{const saved=await api.save(projectId,target);setBasis(saved.revision);setUncertain(undefined);completed.current=true;clearSubmittedDraft(key,projectId,submitted);if(alive.current)go('/reports?'+new URLSearchParams({view:'plan',scenario_id:saved.id,scenario_revision:String(saved.revision),return_to:'/testing?scenario='+saved.id}))}
    catch(value){if(value instanceof ApiError&&!['API_VERSION_UNSUPPORTED','READ_TIMEOUT'].includes(value.code))setUncertain(undefined);setError(value)}finally{setBusy(false)}
  }
  const reconcile=async()=>{
    if(!uncertain)return
    setBusy(true)
    try{const saved=await api.read(projectId,uncertain.id,uncertain.revision);if(JSON.stringify(canonical(saved))!==JSON.stringify(canonical(uncertain)))throw new Error('草稿与所选修订不一致。请保留草稿，返回查看已保存的场景。');setBasis(saved.revision);setDocument(saved);setUncertain(undefined);setError(undefined)}catch(value){if(value instanceof ApiError&&value.code==='RECORD_NOT_FOUND')setUncertain(undefined);setError(value)}finally{setBusy(false)}
  }
  const addVariant=()=>{
    const normal=document.experiments.find(item=>item.kind==='NORMAL')!
    const value:ScenarioExperiment={...structuredClone(normal),id:id('experiment_'),kind:variant,label:kinds[variant],control_experiment_id:normal.id}
    if(variant==='OMIT'&&value.invocations.length>1)value.invocations.splice(value.invocations.length>2?1:0,1)
    if(variant==='REORDER'&&value.invocations.length>1)[value.invocations[0],value.invocations[1]]=[value.invocations[1],value.invocations[0]]
    if(variant==='REPEAT'&&value.invocations.length){const last=value.invocations.at(-1)!;value.invocations.push({...structuredClone(last),id:id('repeat_'),label:last.label+'（再次执行）'})}
    update({experiments:[...document.experiments,value]});setExperimentId(value.id);setInvocationId('')
  }
  return <><div hidden={trial}><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath('/testing?scenario=list')} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}业务场景目录</ActionLink></div><Heading title="组合业务场景">安排正常流程，再添加需要验证的变化。每一步使用已准备的账号、数据和权限规则。</Heading>
    <div hidden={Boolean(options.length||initial)}><Empty layout="section" title="先准备一个业务操作" action={<Button kind="primary" onClick={()=>go('/preparation?'+new URLSearchParams({return_to:'/testing?scenario=new'}))}>准备账号、数据和结果依据<ArrowRightOutlined aria-hidden="true"/></Button>}>场景用于检查同一业务流程中的跳步、重复操作或账号变化。先让一个操作可以执行，再回来组合步骤；场景草稿会保留。</Empty></div><fieldset disabled={disabled} className="jj-scenario-editor" hidden={!options.length&&!initial}><div className="jj-form-grid"><Field label="场景名称"><input maxLength={128} value={document.label} onChange={event=>update({label:event.target.value})}/></Field><Field label="业务目的（选填）"><input maxLength={1024} value={document.description} onChange={event=>update({description:event.target.value})}/></Field></div>
      <div className="jj-scenario-toolbar"><Tabs label="业务实验" value={experiment.id} onValueChange={value=>{setExperimentId(value);setInvocationId('')}} items={document.experiments.map(item=>({value:item.id,label:item.label}))}/><div><Choice disabled={disabled} aria-label="要创建的变体" value={variant} onValueChange={value=>setVariant(value as ScenarioExperiment['kind'])}>{Object.entries(kinds).filter(([key])=>key!=='NORMAL').map(([value,label])=><option key={value} value={value}>{label}</option>)}</Choice><Button disabled={!document.experiments[0].invocations.length||(['OMIT','REORDER'].includes(variant)&&document.experiments[0].invocations.length<2)||document.experiments.length>=16} onClick={addVariant}>创建变体</Button></div></div>
      <div className="jj-scenario-layout" data-empty={!experiment.invocations.length}><aside hidden={!experiment.invocations.length}><SectionHeading title="执行动作"/><IndexSelection label="执行顺序" identity={current?.id??''}>{experiment.invocations.map((item,index)=><button key={item.id} type="button" className="jj-index-item jj-step-select" aria-current={current?.id===item.id?'step':undefined} onClick={()=>setInvocationId(item.id)}><span className="jj-trace-order">{index+1}</span><strong>{item.label}</strong><ArrowRightOutlined aria-hidden="true"/></button>)}</IndexSelection><IndexActions><Button kind="quiet" disabled={!options.length||experiment.invocations.length>=16} icon={<PlusOutlined aria-hidden="true"/>} onClick={addInvocation}>添加动作</Button></IndexActions></aside>
        <section className="jj-scenario-reading">{current?<><header><h2>{current.label}</h2><div>{canTrial&&<Button kind="quiet" disabled={disabled} onClick={()=>setTrial(true)}>单独试运行</Button>}<Button kind="quiet" disabled={experiment.invocations.indexOf(current)===0} onClick={()=>{const values=[...experiment.invocations],index=values.indexOf(current);[values[index-1],values[index]]=[values[index],values[index-1]];setInvocations(values)}}>上移</Button><Button kind="quiet" onClick={()=>setInvocations(experiment.invocations.filter(item=>item.id!==current.id))}>移除此步</Button></div></header>
          <Field label="步骤说明"><input maxLength={128} value={current.label} onChange={event=>updateInvocation({label:event.target.value})}/></Field>
          <Field label="本步调用方式"><Choice disabled={disabled} value={current.batch?.strategy??'SINGLE'} onValueChange={value=>updateInvocation({items:current.items.slice(0,1).map(({resource_from,...item})=>value==='SINGLE'?{...item,...(resource_from?{resource_from}:{})}:item),batch:value==='SINGLE'?null:{strategy:value as 'ATOMIC'|'PER_ITEM',array_path:['ids'],response_items_path:null,response_resource_field:null}})}><option value="SINGLE">单项请求</option><option value="ATOMIC">一次批量 · 整批原子</option><option value="PER_ITEM">一次批量 · 逐项处理</option></Choice></Field>
          <ScenarioResources key={current.id} current={current} options={options} context={context} producers={experiment.invocations.slice(0,experiment.invocations.indexOf(current)).filter(node=>node.items.length===1&&!node.batch&&available.some(option=>matchesScenarioItem(node.items[0],option)&&option.action.creates_resource))} disabled={disabled} onChange={items=>updateInvocation({items})} onAdd={()=>updateInvocation({items:[...current.items,newItem()]})}/>
          {current.batch&&<><div className="jj-form-grid"><Field label="JSON 中的资源数组位置" hint="填写已有单项请求中的资源数组位置，例如 ids。保存后可在预览中核对。"><input value={current.batch.array_path.join('.')} onChange={event=>updateInvocation({batch:{...current.batch!,array_path:event.target.value.split('.').map(part=>/^(0|[1-9][0-9]*)$/.test(part)?Number(part):part)}})}/></Field><Field label="返回项数组位置（读取数据时必填）"><input placeholder="例如 $.items" value={current.batch.response_items_path??''} onChange={event=>updateInvocation({batch:{...current.batch!,response_items_path:event.target.value||null}})}/></Field><Field label="返回项中的资源编号字段"><input value={current.batch.response_resource_field??''} onChange={event=>updateInvocation({batch:{...current.batch!,response_resource_field:event.target.value||null}})}/></Field></div><p className="jj-small jj-muted">批量项必须使用同一真实账号。原子批量中混有禁止项时，所有项都不得产生业务效果；正常对照使用操作方式相同、所有资源均允许访问的批量请求。</p></>}
          <section className="jj-scenario-debug"><h3>核对执行范围</h3><p className="jj-small jj-muted">确认执行前，可预览整段流程的账号、数据和恢复安排。变体会保留完整的正常对照；只检查正常流程的前几步时，会单独保存所选范围。场景草稿继续保留。</p><footer>{experiment.kind==='NORMAL'&&<Button disabled={disabled||!ready} onClick={()=>void debug(current.id)}>预览到此步骤</Button>}<Button disabled={disabled||!ready} onClick={()=>void debug()}>预览本实验检查<ArrowRightOutlined aria-hidden="true"/></Button></footer></section>
        </>:<Empty title={options.length?'选择本实验的第一个动作':'先完成动作准备'} action={<Button onClick={()=>options.length?addInvocation():go('/preparation?'+new URLSearchParams({return_to:'/testing?scenario='+(initial?document.id:'new')}))}>{options.length?'添加已有动作':'准备账号、资源与证明'}<ArrowRightOutlined aria-hidden="true"/></Button>}>{options.length?'从已准备的业务操作中选择第一步，再继续安排后续操作与检查要求。':'场景复用已有业务操作。先准备一个操作的账号、测试资源和结果证明，完成后会返回这份场景草稿。'}</Empty>}</section>
      </div>
    </fieldset>
    </div>
    {trial&&current&&currentOption&&canTrial&&<ScenarioNodeTrial projectId={projectId} node={current} option={currentOption} context={context} onClose={()=>setTrial(false)}/>}
    {error&&<ErrorNote error={error}/>}
    {debugUncertain&&<div className="jj-scenario-actions"><Button busy={busy} onClick={()=>void debug()}>核对原调试范围</Button></div>}
    <footer className="jj-scenario-actions" hidden={!options.length&&!initial}><Button disabled={disabled} onClick={()=>requestCollaboration(projectId,'SETUP','沿用当前业务场景草稿与准确权限，整理正常对照及有意义的变体并保存候选；不要猜测缺少的业务规则，不运行目标。')}>请 Agent 整理</Button>{historical?<ActionLink navigationScope="page" href={'#'+scopedPath('/testing?scenario='+document.id)}  kind="default">打开当前修订<ArrowRightOutlined aria-hidden="true"/></ActionLink>:uncertain?<Button busy={busy} onClick={()=>void reconcile()}>查看上次保存结果</Button>:<Button kind="primary" busy={busy} disabled={!ready} onClick={()=>void save()}>保存并预览检查<ArrowRightOutlined aria-hidden="true"/></Button>}</footer>
  </>
}
