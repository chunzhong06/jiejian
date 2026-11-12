import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import {requirement} from '../../entities/check/model/checks'
import {issueDestination} from '../../entities/check/issueDestination'
import {ComparePair} from '../../shared/ui/ComparePair'
import {DisclosureMarker} from '../../shared/ui/DisclosureMarker'
import {Fragment,useRef,useState,type ReactNode} from 'react'
import CloseOutlined from '@ant-design/icons/CloseOutlined'
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined'
import {comparisonApi,type ChangeKind,type ComparisonItem,type ComparisonRun} from '../../entities/check/api/comparison'
import {currentChecksApi,type ActionResultStory} from '../../entities/check/api/currentChecks'
import {useRead} from '../../shared/lib/useRead'
import {useDirectoryState} from '../../shared/lib/directoryState'
import {go,scopedPath,returnDestination,returnDestinationLabel,withReturnDestination} from '../../shared/lib/navigation'
import {date,text} from '../../shared/lib/format'
import {assertProject} from '../../shared/model/page'
import {Heading,Field} from '../../shared/ui/layout'
import {Choice} from '../../shared/ui/Choice'
import {ObjectTable} from '../../shared/ui/ObjectTable'
import {useContentTransition} from '../../shared/lib/contentTransition'
import {Button,ActionLink} from '../../shared/ui/actions'
import {Badge,Empty,ErrorNote,Loading,Notice,PageError,ResultSummary,ContextNote} from '../../shared/ui/feedback'
import type {ReportsProps} from './types'
import './comparison.css'

export const changeLabels:Record<ChangeKind,string>={NEW:'相较参照新增',PERSISTING:'持续存在',FIXED:'已验证修复',NO_LONGER_OBSERVED:'本次未再观察到',RECURRED:'再次出现',UNCHANGED:'保持符合',INSUFFICIENT:'证据不足',INCOMPARABLE:'不可直接比较'}
const reasonLabels:Record<string,string>={BASELINE_NOT_COVERED:'参照检查未覆盖这项内容',CURRENT_NOT_COVERED:'这次检查未覆盖这项内容',CHECK_CONTRACT_CHANGED:'规则、业务含义或证明方法已变化',PUBLISHED_FACTS_INCOMPLETE:'至少一轮缺少可用的逐项结论',NORMAL_CONTROL_NOT_RETAINED:'本轮正常业务对照尚未确认',DEPLOYMENT_UNCONFIRMED:'实际运行的代码版本未核对，只能说明这次观察结果',RELATIVE_TO_BASELINE:'参照检查中没有这项问题，不能据此认定它是首次出现',SUBJECT_OR_RESOURCE_BINDING_CHANGED:'两次检查使用的账号或资源不同，尚未核对它们是否可以对应'}
const tone=(state:ChangeKind)=>['NEW','PERSISTING','RECURRED'].includes(state)?'negative':state==='FIXED'||state==='UNCHANGED'?'positive':'caution'
const verificationReasons:Record<string,string>={REPAIR_CONTEXT_NOT_LINKED:'这次检查尚未关联原问题，请从问题记录继续复验。',REPAIR_CONTEXT_MISMATCH:'这次检查与原问题或代码修改的关联尚未核对。',REPAIR_POLICY_CHANGED:'原问题使用的规则已经变化，需要重新确认适用要求。',REPAIR_RUNTIME_NOT_CONFIRMED:'尚未确认实际运行的代码与这次修改对应。',REPAIR_CASE_NOT_UNIQUELY_MATCHED:'尚未找到唯一对应的原问题与正常对照。',REPAIR_REQUIRED_CASE_NOT_SAFE:'必要的原问题或正常回归尚未全部符合要求。',REPAIR_STANDARD_CHANGED:'两次检查的业务证明标准已变化。',REPAIR_STANDARD_UNAVAILABLE:'原问题的业务证明标准暂不可用。',REPAIR_ATTRIBUTION_INCOMPLETE:'账号、资源或业务结果的对应依据尚未齐全。'}
const comparisonLabel=(item:ComparisonItem)=>item.state==='FIXED'&&item.verification_scope==='EXTERNAL_OBSERVATION'?'本次行为符合要求':changeLabels[item.state]
const path=(baseline:string,current:string,earlier?:string)=>'/reports?'+new URLSearchParams({view:'compare',baseline,current,...(earlier?{earlier}:{})})

export function Comparison(props:ReportsProps){
 const baseline=props.route.query.get('baseline'),current=props.route.query.get('current'),earlier=props.route.query.get('earlier')??undefined
 if(!baseline||!current||[baseline,current,...(earlier?[earlier]:[])].some(value=>!/^run_[0-9a-f]{32}$/.test(value)))return <PageError title="本轮变化" error={new Error('请选择参照记录和本次记录。此处会保留所选对象，不自动改用最近记录。')}/>
 return <ComparisonWorkspace key={[props.projectId,baseline,current,earlier].join(':')} {...props} baseline={baseline} current={current} earlier={earlier}/>
}

function ComparisonWorkspace({projectId,route,baseline,current,earlier}:ReportsProps&{baseline:string;current:string;earlier?:string}){
 const root=useRef<HTMLElement>(null),origin=returnDestination(route.query.get('return_to'))??'/reports',here=path(baseline,current,earlier)+'&return_to='+encodeURIComponent(origin)
 const [cursor,setCursor]=useState<string>(),[stack,setStack]=useState<Array<string|undefined>>([]),[setup,setSetup]=useState(false)
 const state=useRead('comparison:'+projectId+':'+baseline+':'+current+':'+earlier+':'+cursor,async signal=>{const value=await comparisonApi.read(projectId,baseline,current,earlier,cursor,signal);assertProject(value.project_id,projectId);return value})
 const directory=useDirectoryState('jiejian.directory:'+projectId+':comparison:'+baseline+':'+current,{selectedId:'',open:true as boolean},Boolean(state.data),root)
 if(state.loading)return <PageSkeleton view="/reports" title="本轮变化"/>
 if(state.error||!state.data)return <PageError title="本轮变化" error={state.error}/>
 const value=state.data,item=value.items.find(item=>item.key===directory.value.selectedId)??value.items.find(item=>!['UNCHANGED','PERSISTING'].includes(item.state))??value.items[0]
 const close=()=>{root.current?.querySelector<HTMLButtonElement>('[aria-pressed=true]')?.focus({preventScroll:true});directory.update({open:false})}
 return <><div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin,projectId)} kind="quiet">{<ArrowLeftOutlined aria-hidden="true"/>}{returnDestinationLabel(origin)}</ActionLink></div>
  <Heading title="本轮变化" actions={<Button onClick={()=>setSetup(value=>!value)}>{setup?'收起记录选择':'更换比较记录'}</Button>}>比较原问题、正常访问和检查条件的变化。</Heading>
  {setup&&<ComparisonSetup projectId={projectId} baseline={baseline} current={current} earlier={earlier} origin={origin}/>}
  <div className="jj-comparison-overview"><dl className="jj-facts jj-comparison-identities" data-layout="columns" aria-label="本次比较的两份检查"><div><dt>参照检查</dt><dd><time dateTime={new Date(value.baseline.created_at_us/1000).toISOString()}>{date(value.baseline.created_at_us)}</time>{value.baseline.environment&&<small>{value.baseline.environment.name}</small>}</dd></div><div><dt>这次检查</dt><dd><time dateTime={new Date(value.current.created_at_us/1000).toISOString()}>{date(value.current.created_at_us)}</time>{value.current.environment&&<small>{value.current.environment.name}</small>}</dd></div></dl>
  <details className="jj-comparison-context"><summary>检查时间、连接与代码对应</summary><section className="jj-comparison-runs" aria-label="比较前提"><RunFacts label="作为参照的检查" run={value.baseline}/><RunFacts label="这次检查" run={value.current}/></section></details>
  {value.limitations.includes('UNPUBLISHED_OR_INVALID_RUN')&&<Notice tone="caution">至少一次检查还没有完整、有效的报告。请先核对执行情况，再判断问题是否发生变化。</Notice>}
  {value.limitations.includes('DEPLOYMENT_VERSION_UNCONFIRMED')&&<ContextNote label="运行代码核对情况"><p>至少一次检查尚未核对运行代码。这里会比较实际观察结果；确认源码修复有效，还需要核对对应的运行版本。</p></ContextNote>}
  <p className="jj-small jj-muted" data-motion-text>{Object.entries(value.counts).filter(([,count])=>count>0).map(([kind,count])=>(kind==='FIXED'?'原问题验证完成':changeLabels[kind as ChangeKind])+' '+count+' 项').join(' · ')||'尚无可比较事项'}{value.earlier?' · 已核对更早的问题记录':''}</p>
  </div>
  {value.items.length?<section ref={root} className="jj-collection jj-comparison-results" aria-label="逐项比较结果"><ObjectTable appearance="contained" selection={item?.key??''} className="jj-comparison-table"><thead><tr><th>业务事项</th><th>参照结果</th><th>这次变化</th></tr></thead><tbody>{[...value.items].sort((a,b)=>Number(a.state==='UNCHANGED')-Number(b.state==='UNCHANGED')).map(row=>{
   const expanded=directory.value.open&&row===item,detailId='comparison-detail-'+row.key;
   return <Fragment key={row.key}><tr data-selected={row===item}><th scope="row"><button className="jj-object-select" aria-pressed={row===item} aria-expanded={expanded} aria-controls={expanded?detailId:undefined} data-directory-id={row.key} onClick={()=>directory.update({selectedId:row.key,open:row===item?!directory.value.open:true})}><span className="jj-comparison-object"><DisclosureMarker expanded={expanded}/><span><strong>{row.action_label}</strong><small>{row.subject_label}</small></span></span></button></th><td>{resultLabel(row.before?.verdict)}</td><td><Badge tone={tone(row.state)}>{comparisonLabel(row)}</Badge></td></tr>
    {expanded&&<tr className="jj-comparison-detail-row"><td colSpan={3}><ExpandedComparison id={detailId} item={row} deploymentExplained={value.limitations.includes('DEPLOYMENT_VERSION_UNCONFIRMED')} onClose={close}>
      <ComparisonDetail key={row.key} projectId={projectId} baseline={baseline} current={current} item={row}/>
      <footer>{row.origin_repair&&<ActionLink onClick={()=>directory.remember(row.key)} href={'#'+scopedPath(issueDestination(row.origin_repair,here,{section:'repair',run_id:current}),projectId)}>处理这项原问题</ActionLink>}{row.before&&<ActionLink onClick={()=>directory.remember(row.key)} href={'#'+scopedPath(withReturnDestination('/reports?'+new URLSearchParams({run_id:baseline,case_id:row.before.case_id}),here),projectId)}>阅读参照报告</ActionLink>}{row.after&&<ActionLink kind="primary" onClick={()=>directory.remember(row.key)} href={'#'+scopedPath(withReturnDestination('/reports?'+new URLSearchParams({run_id:current,case_id:row.after.case_id}),here),projectId)}>阅读这次证据</ActionLink>}</footer>
    </ExpandedComparison></td></tr>}
   </Fragment>
  })}</tbody></ObjectTable></section>:<Empty title="还没有可逐项比较的检查结果">请核对两次检查的范围，并确认报告是否完整。原记录继续保留。</Empty>}
  <div className="jj-pagination"><Button disabled={!stack.length} onClick={()=>{setCursor(stack.at(-1));setStack(value=>value.slice(0,-1))}}>上一页</Button><span>第 {stack.length+1} 页</span><Button disabled={!value.next_cursor} onClick={()=>{setStack(value=>[...value,cursor]);setCursor(value.next_cursor!);directory.update({selectedId:'',open:true})}}>下一页</Button></div>
 </>
}

// 只解释服务端已发布的变化分类，不依据说明文字或页面展开状态重算修复结论。
const changeExplanation:Record<ChangeKind,string>={
 NEW:'相较所选参照，这次检查新发现了违反要求的结果；这不表示它是历史上首次出现。',
 PERSISTING:'两次检查都发现了违反要求的结果，原问题仍然存在。',
 FIXED:'按已核对的可比条件，这次检查验证原问题已消失，正常业务对照也符合要求。',
 NO_LONGER_OBSERVED:'这次检查没有再观察到原问题；当前事实尚不足以将其认定为已验证修复。',
 RECURRED:'更早的检查曾发现这项问题，参照检查中未再发现，这次又出现了违反要求的结果。',
 UNCHANGED:'两次检查都符合要求，当前没有观察到这项结果发生变化。',
 INSUFFICIENT:'尚不能确认问题是否解决，请先补齐缺少的执行记录或结果证明。',
 INCOMPARABLE:'两次检查的条件不能直接对应，当前无法据此判断问题是否发生变化。',
}

// 共同的运行版本限制在比较前提中说明一次；逐项保留其余实际缺口。
function ExpandedComparison({id,item,deploymentExplained,onClose,children}:{id:string;item:ComparisonItem;deploymentExplained:boolean;onClose:()=>void;children:ReactNode}){
 const content=useContentTransition<HTMLElement>(item.key)
 return <section id={id} ref={content} className="jj-comparison-inline" aria-label={item.subject_label+'的'+item.action_label+'比较说明'} onKeyDown={event=>{if(event.key==='Escape'&&!event.defaultPrevented){event.preventDefault();onClose()}}}>
  <header><h2 className="jj-title-group">前后检查的依据</h2><Button kind="quiet" aria-label="收起比较说明" icon={<CloseOutlined aria-hidden="true"/>} onClick={onClose}/></header>
  <div className="jj-compare-intro"><p>{item.state==='FIXED'&&item.verification_scope==='EXTERNAL_OBSERVATION'?'这次复验按原账号、资源和证明要求验证了原问题及正常功能。该结果确认本次部署的行为。':changeExplanation[item.state]}</p>{item.reasons.filter(reason=>(item.state!=='NEW'||reason!=='RELATIVE_TO_BASELINE')&&(!deploymentExplained||reason!=='DEPLOYMENT_UNCONFIRMED')).map(reason=><p className="jj-small jj-muted" key={reason}>{reasonLabels[reason]??verificationReasons[reason]??'需要核对比较依据'}</p>)}</div>{children}
 </section>
}

const resultLabel=(verdict?:string|null)=>verdict==='VULNERABLE'?'不符合规则':verdict==='SAFE'?'符合规则':verdict?'证据不足':'未覆盖或未执行'

function RunFacts({label,run}:{label:string;run:ComparisonRun}){
 const time=date(run.created_at_us)+':'+String(new Date(run.created_at_us/1000).getSeconds()).padStart(2,'0');
 return <div><h2>{label}</h2><p>{time}</p><p>{run.environment?'检查使用“'+run.environment.name+'”中的应用连接。':'这次检查未记录使用的应用连接。'}</p><p className="jj-small jj-muted">{run.deployment==='MATCHED'?'实际运行的代码版本已核对。':'实际运行的代码版本尚未核对。'}</p><details><summary>代码版本与运行记录</summary><dl className="jj-facts"><div><dt>运行记录</dt><dd>{run.run_id}</dd></div><div><dt>声明的版本</dt><dd>{run.environment?.deployment_label??'未声明'}</dd></div><div><dt>源码身份</dt><dd>{run.source_fingerprint??'未记录源码身份'}</dd></div></dl></details></div>
}

function ComparisonDetail({projectId,baseline,current,item}:{projectId:string;baseline:string;current:string;item:ComparisonItem}){
 const state=useRead('comparison-detail:'+projectId+':'+baseline+':'+current+':'+item.key,async()=>{const value=await comparisonApi.detail(projectId,baseline,current,item.key);assertProject(value.project_id,projectId);return value})
 if(state.loading)return <Loading/>
 if(state.error)return <ErrorNote error={state.error}/>
 const before=state.data?.before,after=state.data?.after,common=Boolean(before&&after&&requirement(before)===requirement(after))
 return <>{common&&<p className="jj-comparison-requirement">共同要求：{requirement(before!)}</p>}<ComparePair className="jj-comparison-observations"><Observation label="参照检查中的结果" item={before} showRequirement={!common}/><Observation label="这次观察到的结果" item={after} showRequirement={!common}/></ComparePair></>
}

function Observation({label,item,showRequirement=true}:{label:string;item?:ActionResultStory|null;showRequirement?:boolean}){
 const facts=item?.fact_comparison
 return <section><h3>{label}</h3>{!facts||!item?<p className="jj-small jj-muted">这项内容还没有已发布的事实记录。</p>:<>{showRequirement&&<p>按已确认的要求，{text(facts.planned_identity.label??'记录中的账号')}{item.permission.expectation==='DENY'?'不得':'可以'}{text(item.display_name)}。</p>}{facts.effects.map(effect=><p key={effect.effect_id}>{effect.assessment_state==='CONFIRMED'?'检查中已观察到':effect.assessment_state==='ABSENT'?'检查中没有观察到':'检查尚未确认是否出现'}“{text(effect.business_label)}”。</p>)}{item.permission.expectation==='DENY'&&<ResultSummary label="正常业务对照" status={<Badge tone={facts.allow_control?.verdict==='SAFE'?'positive':facts.allow_control?.verdict==='VULNERABLE'?'negative':facts.allow_control?'caution':'neutral'}>{facts.allow_control?.verdict==='SAFE'?'符合规则':facts.allow_control?.verdict==='VULNERABLE'?'不符合规则':facts.allow_control?'尚未确认':'无可用结果'}</Badge>}/>}<details><summary>核对测试对象</summary><p className="jj-small jj-muted">测试资源：{facts.resource_id}</p></details></>}</section>
}

function ComparisonSetup({projectId,baseline,current,earlier,origin}:{projectId:string;baseline:string;current:string;earlier?:string;origin:string}){
 const state=useRead('comparison-options:'+projectId,()=>currentChecksApi.history(projectId))
 const [selection,setSelection]=useState({baseline,current,earlier:earlier??''})
 const options=state.data?.items??[]
 const choose=(key:keyof typeof selection,label:string,optional=false)=><Field label={label}><Choice value={selection[key]} onValueChange={value=>setSelection(current=>({...current,[key]:value}))}>{optional&&<option value="">不指定更早问题记录</option>}{selection[key]&&!options.some(item=>item.status.run.run_id===selection[key])&&<option value={selection[key]}>原选定记录 · {selection[key].slice(-8)}</option>}{options.map(item=><option key={item.status.run.run_id} value={item.status.run.run_id}>{date(item.status.run.created_at_us)} · {item.status.run.verdict??item.status.run.lifecycle} · {item.status.run.run_id.slice(-8)}</option>)}</Choice></Field>
 return <section className="jj-comparison-setup"><div>{choose('baseline','用作参照的检查记录')}{choose('current','这次检查记录')}{choose('earlier','更早的问题记录（用于核对再次出现）',true)}</div><p className="jj-small jj-muted">显示最近一页记录；其他记录可从检查记录中选定。比较按时间递增，更早记录用于核对同一问题曾经出现。</p>{state.error&&<ErrorNote error={state.error}/>}<footer><Button kind="primary" disabled={selection.baseline===selection.current||Boolean(selection.earlier&&[selection.baseline,selection.current].includes(selection.earlier))} onClick={()=>go(withReturnDestination(path(selection.baseline,selection.current,selection.earlier||undefined),origin),projectId)}>比较选定记录</Button></footer></section>
}
