import {useRef,useState} from 'react'
import {businessScenariosApi,type ScenarioContext,type ScenarioItem} from '../api/businessScenarios'
import {assertProject} from '../../../shared/model/page'
import {useRead} from '../../../shared/lib/useRead'
import {Button} from '../../../shared/ui/actions'
import {SectionHeading} from '../../../shared/ui/layout'
import {ObjectTable} from '../../../shared/ui/ObjectTable'
import {ErrorNote,Loading} from '../../../shared/ui/feedback'
import './scenario-overview.css'

export const scenarioKindLabels={NORMAL:'正常业务',OMIT:'省略步骤',REORDER:'调整顺序',REPEAT:'重复动作',CHANGE_SUBJECT:'更换账号后继续',REVOKE:'撤销后继续'} as const

/** 只按完整规则引用查找预期；当前同名规则和最新版本不能解释旧场景。 */
function requirement(item:ScenarioItem,context:ScenarioContext|undefined){
 const exact=context?.requirements?.find(candidate=>candidate.permission.intent_id===item.permission.intent_id&&candidate.permission.revision===item.permission.revision&&candidate.permission.intent_hash===item.permission.intent_hash)
 if(exact)return exact.expectation
 return context?.actions?.flatMap(action=>action.cases).find(candidate=>candidate.subject_test_identity_id===item.subject_identity_id&&candidate.resource_id===item.resource_id&&candidate.permission.intent_id===item.permission.intent_id&&candidate.permission.revision===item.permission.revision&&candidate.permission.intent_hash===item.permission.intent_hash)?.permission.expectation
}

/** 阅读准确场景修订；上下文只补充名称及准确要求，不推测材料可用或触发执行。 */
export function ScenarioOverview({projectId,id,revision,layout='stack'}:{projectId:string;id:string;revision:number;layout?:'stack'|'split'}){
 const [experimentId,setExperimentId]=useState(''),root=useRef<HTMLDivElement>(null)
 const state=useRead('scenario-overview:'+projectId+':'+id+':'+revision,async()=>{
  const value=await businessScenariosApi.read(projectId,id,revision);assertProject(value.project_id,projectId)
  if(value.id!==id||value.revision!==revision)throw new Error('业务场景内容与所选修订不一致。')
  return value
 })
 const context=useRead('scenario-overview-context:'+projectId+':'+id+':'+revision,async()=>{const value=await businessScenariosApi.context(projectId,undefined,{scenario_id:id,revision});assertProject(value.project_id,projectId);if(value.scenario&&(value.scenario.id!==id||value.scenario.revision!==revision))throw new Error('场景依据与所选修订不一致。');return value})
 if(!state.data)return state.loading?<Loading/>:<div className="jj-scenario-overview"><ErrorNote error={state.error}/><Button onClick={state.reload}>重新读取场景</Button></div>
 const document=state.data,selected=document.experiments.find(item=>item.id===experimentId)
 const actor=(item:ScenarioItem)=>item.subject_identity_id===null?'匿名访问':context.data?.identities?.find(identity=>identity.identity_id===item.subject_identity_id)?.label??'账号名称待核对'
 const expected=(item:ScenarioItem)=>{const value=requirement(item,context.data);return value==='ALLOW'?'允许':value==='DENY'?'禁止':'要求待核对'}
 const close=()=>{const previous=experimentId;setExperimentId('');requestAnimationFrame(()=>root.current?.querySelector<HTMLButtonElement>('[data-experiment="'+CSS.escape(previous)+'"]')?.focus({preventScroll:true}))}
 return <div ref={root} className="jj-scenario-overview" data-layout={layout}>
  <ObjectTable selection={selected?.id??''} aria-label="业务实验与预期要求" className="jj-scenario-experiments"><thead><tr><th>业务实验</th><th>操作账号</th><th>测试资源</th><th>预期要求</th></tr></thead><tbody>{document.experiments.map(experiment=>{
   const items=experiment.invocations.flatMap(invocation=>invocation.items??[]),join=(values:string[])=>[...new Set(values)].join('、')
   return <tr key={experiment.id} data-selected={selected?.id===experiment.id}><th scope="row"><button className="jj-object-select" data-experiment={experiment.id} aria-expanded={selected?.id===experiment.id} onClick={()=>selected?.id===experiment.id?close():setExperimentId(experiment.id)}><strong>{experiment.label}</strong><small>{experiment.control_experiment_id?'对照：'+(document.experiments.find(item=>item.id===experiment.control_experiment_id)?.label??'对照实验待核对'):document.experiments.some(item=>item.control_experiment_id===experiment.id)?'正常对照':scenarioKindLabels[experiment.kind]}</small></button></th><td>{items.length?join(items.map(actor)):'步骤中未指定'}</td><td>{items.length?join(items.map(item=>item.resource_from?'沿用前序步骤生成的资源':item.resource_id)):'步骤中未指定'}</td><td>{items.length?join(items.map(expected)):'按步骤核对'}</td></tr>
  })}</tbody></ObjectTable>
  {selected&&<section className="jj-scenario-experiment-detail" aria-label={selected.label+'的实验安排'}>
   <SectionHeading title={selected.label} level={3} appearance="group" meta={selected.invocations.length+' 个步骤'} actions={<Button kind="quiet" size="compact" onClick={close}>收起实验安排</Button>}/>
   <div className="jj-scenario-experiment-columns"><section><h4>执行步骤</h4><ol>{selected.invocations.map(invocation=><li key={invocation.id}><strong>{invocation.label}</strong>{invocation.batch&&<small>批量操作</small>}{invocation.depends_on?.length>0&&<small>在{invocation.depends_on.map(step=>selected.invocations.find(item=>item.id===step)?.label??'前序步骤').join('、')}之后执行</small>}</li>)}</ol></section>
    <section><h4>账号、资源与要求</h4>{selected.invocations.flatMap(invocation=>(invocation.items??[]).map(item=><article key={invocation.id+':'+item.id}><strong>{actor(item)} · {expected(item)}</strong><p>{invocation.label}</p><p className="jj-small jj-muted">{item.resource_from?'使用前序步骤生成的资源':'测试资源：'+item.resource_id}</p></article>))}{!selected.invocations.some(invocation=>invocation.items?.length>0)&&<p className="jj-small jj-muted">这份场景没有可读取的账号与资源对应。</p>}</section></div>
  </section>}
  {document.description&&<details className="jj-scenario-description jj-reading-disclosure"><summary>场景补充说明</summary><p>{document.description}</p></details>}
  {context.error&&<div className="jj-scenario-context-error"><p>账号名称与预期要求暂未取得，已保存的实验与步骤继续保留。</p><Button kind="quiet" onClick={context.reload}>重新读取对应依据</Button></div>}
  {Boolean(state.error)&&<ErrorNote error={state.error} onRetry={state.reload} retryLabel="重新读取场景资料"/>}
 </div>
}
