import {useState} from 'react'
import {validationApi,type ValidationReference,type ValidationQuestion,type ValidationRequirement,type OpenQuestionRequest} from '../api/validation'
import {ruleCandidatesApi} from '../api/ruleCandidates'
import {useRead} from '../../../shared/lib/useRead'
import {assertProject} from '../../../shared/model/page'
import {readRoute,scopedPath,withReturnDestination,go} from '../../../shared/lib/navigation'
import {ActionLink,Button} from '../../../shared/ui/actions'
import {Badge,ErrorNote} from '../../../shared/ui/feedback'
import {ObjectHeading,SectionHeading,Field} from '../../../shared/ui/layout'
import {Choice} from '../../../shared/ui/Choice'
import {IndexSelection} from '../../../shared/ui/IndexSelection'
import {conditionLabels} from './RuleConditions'
import type {PermissionConditions,BoundaryMaintenanceCommandDto} from '../api/businessBoundaries'
import './validation-plan.css'

const statuses:Record<string,string>={SATISFIED:'当前材料已满足',STALE:'材料需重核',NEEDS_USER:'需要补齐',BLOCKED:'当前有阻塞',NEEDS_SOURCE:'需要证明来源',UNSUPPORTED:'缺少通用证明合同',NOT_REQUIRED:'无需准备'}
const capabilities:Record<string,string>={CONFIGURED:'已有对应配置',NEEDS_CONFIGURATION:'需准备证明配置',NEEDS_RECHECK:'原配置需重核',UNSUPPORTED:'当前来源不支持这项证明'}
const proofMethods:Record<string,string>={HTTP_ENTITY_QUERY:'查询业务结果',RECORDED_OBSERVATION:'流程中的结果观察',REGISTERED_OBSERVER:'已登记的证明来源'}
const questions:Record<ValidationQuestion['status'],string>={NEEDS_DECISION:'待核对',DEFERRED:'稍后决定',EXCLUDED:'本次不纳入',IN_REVIEW:'继续审阅',RECHECK:'依据变化，需重核'}

/** 业务要求、验证路径和准备事实来自同一读取；错误时保留旧阅读并关闭基于旧依据的写入。 */
export function ValidationPlanPanel({projectId,reference={},command,mode='requirements'}:{projectId:string;reference?:ValidationReference;command?:BoundaryMaintenanceCommandDto;mode?:'questions'|'requirements'|'summary'}){
  const route=readRoute(),origin=route.path+'?'+route.query
  const state=useRead('validation-plan:'+projectId+':'+JSON.stringify(command??reference),async signal=>{
    const value=command?await validationApi.preview(projectId,command,signal):await validationApi.read(projectId,reference,signal);assertProject(value.project_id,projectId);return value
  })
  const [busy,setBusy]=useState(false),[error,setError]=useState<Error>()
  const [selectedId,setSelectedId]=useState('')
  const data=state.data
  // 选择只定位本次读取中的要求；依据更新后不保留已经不存在的对象正文。
  const selected=data?.requirements.find(item=>item.item_id===selectedId)??data?.requirements[0]
  const href=(path:string)=>'#'+scopedPath(withReturnDestination(path,origin),projectId)
  const open=async(question:ValidationQuestion)=>{
    if(!data||state.error||busy)return
    setBusy(true);setError(undefined)
    const key='jiejian.validation-question:'+projectId+':'+question.requirement_id+':'+question.fingerprint
    try{
      const saved=sessionStorage.getItem(key)
      const command:OpenQuestionRequest=saved?JSON.parse(saved):{operation_id:crypto.randomUUID().replaceAll('-',''),expected_fingerprint:data.fingerprint,question_fingerprint:question.fingerprint,...(reference.candidate_id?{candidate_id:reference.candidate_id,revision:reference.revision}:{})}
      sessionStorage.setItem(key,JSON.stringify(command))
      // 保存响应未知时先读取原SAVE；只有原结果未找到才沿原内容继续同一操作。
      const receipt=saved?await ruleCandidatesApi.receipt(projectId,command.operation_id,'SAVE'):undefined
      const value=receipt?.candidate??await validationApi.open(projectId,question.requirement_id,command)
      sessionStorage.removeItem(key)
      go(scopedPath(withReturnDestination('/permissions?candidate_id='+value.candidate.candidate_id+'&revision='+value.candidate.revision,origin),projectId))
    }catch(value){setError(value instanceof Error?value:new Error('暂时无法打开核对，请查询原操作后继续。'))}
    finally{setBusy(false)}
  }
  if(mode==='summary'&&!state.error&&data&&!data.requirements.length)return null
  return <section className="jj-validation-plan" aria-label={mode==='questions'?'业务边界核对':'要求的验证方案'}>
    {(state.error||error)&&<><ErrorNote error={state.error??error}/><Button kind="quiet" onClick={state.reload}>重新读取验证方案</Button></>}
    {!data&&state.loading&&<p className="jj-small jj-muted">正在核对要求的验证方式与现有材料…</p>}
    {data&&mode==='summary'&&<div className="jj-validation-summary"><SectionHeading level={3} appearance="group" title="检查要求与材料" meta={data.requirements.length+' 项要求'} actions={<ActionLink href={href('/permissions')}>核对权限与验证方案</ActionLink>}/><div className="jj-validation-summary-items">{data.requirements.map(item=><article key={item.item_id}><h4>{item.sentence}</h4><p>{item.preparation_summary??item.environment_summary}</p></article>)}</div></div>}
    {data&&mode!=='summary'&&<>
      {mode==='questions'&&data.questions.length>0&&<><div className="jj-object-line"><h3>继续核对业务边界</h3><Badge>{data.questions.filter(item=>item.status!=='EXCLUDED').length} 项待处理</Badge></div><p className="jj-small jj-muted">以下问题来自已有归属、条件和关系；你的回答进入原业务要求审阅。</p><details><summary>查看相关问题与已保存决定</summary><div className="jj-validation-questions">{data.questions.map(item=><article key={item.requirement_id}><header className="jj-object-line"><h4>{item.question}</h4><Badge>{questions[item.status]}</Badge></header><p>{item.basis}</p>{item.decision_reason&&<p className="jj-small">已保存依据：{item.decision_reason}</p>}<footer>{item.review_url?<ActionLink href={href(item.review_url)}>{item.status==='EXCLUDED'?'查看原决定':'继续核对这项要求'}</ActionLink>:<Button kind="quiet" busy={busy} disabled={busy||Boolean(state.error)} onClick={()=>void open(item)}>{item.status==='RECHECK'?'按新依据重新核对':'核对这项要求'}</Button>}</footer></article>)}</div></details></>}
      {mode==='requirements'&&<><SectionHeading level={3} appearance="group" title="怎样验证这项要求"/>{!selected?<p>这份候选仍需明确具体权限和受保护结果。先保存业务含义，再由原候选流程补齐规则。</p>:<div className="jj-validation-workspace" data-multiple={data.requirements.length>1}>
        {data.requirements.length>1&&<><IndexSelection as="nav" label="选择验证要求" className="jj-validation-index" identity={selected.item_id}>{data.requirements.map(item=><button key={item.item_id} type="button" className="jj-index-item" aria-pressed={selected.item_id===item.item_id} onClick={()=>setSelectedId(item.item_id)}><span>{item.sentence}</span></button>)}</IndexSelection><div className="jj-validation-picker"><Field measure="standard" label="选择验证要求"><Choice value={selected.item_id} onValueChange={setSelectedId}>{data.requirements.map(item=><option key={item.item_id} value={item.item_id}>{item.sentence}</option>)}</Choice></Field></div></>}
        <RequirementReading key={selected.item_id} item={selected} preparationHref={!reference.candidate_id&&!command?href(selected.preparation_url):undefined}/>
      </div>}{reference.candidate_id&&data.questions.length>0&&<details className="jj-validation-boundaries"><summary>批准前还应核对的业务边界</summary>{data.questions.map(item=><article key={item.requirement_id}><h4>{item.question}</h4><p>{item.basis}</p>{item.review_url?<ActionLink href={href(item.review_url)}>继续原业务核对</ActionLink>:<Button kind="quiet" disabled={busy||Boolean(state.error)} onClick={()=>void open(item)}>补充到本候选核对</Button>}</article>)}</details>}<p className="jj-small jj-muted">{data.scope}</p></>}
    </>}
  </section>
}

/** 一项要求的证明、正常对照与准备事实保持同组；不从材料状态推导权限结论。 */
function RequirementReading({item,preparationHref}:{item:ValidationRequirement;preparationHref?:string}){
 const conditions=conditionLabels(item.conditions as PermissionConditions|null)
 return <article className="jj-validation-requirement" aria-label={item.sentence}>
  <ObjectHeading level={4} title={item.sentence} description={conditions.length?conditions.join('，'):undefined}/>
  <div className="jj-validation-reading"><section className="jj-validation-outcomes"><h4 className="jj-title-caption">需要核对的业务结果</h4><div className="jj-validation-effects">{item.effects.map(effect=><section key={effect.item_id}>
   <ObjectHeading level={4} title={effect.label} status={<Badge tone={effect.material_status==='SATISFIED'?'positive':effect.material_status==='UNSUPPORTED'?'caution':'neutral'}>{statuses[effect.material_status]??'待核对'}</Badge>}/><p>{effect.requirement}</p>{effect.capability_status&&<p className="jj-small jj-muted">{capabilities[effect.capability_status]}{effect.configured_path&&proofMethods[effect.configured_path]?' · '+proofMethods[effect.configured_path]:''}</p>}{effect.protected_fields.length>0&&<p className="jj-small jj-muted">受保护字段：{effect.protected_fields.join('、')}</p>}
  </section>)}</div></section><section className="jj-validation-preparation">
   <div><h4 className="jj-title-caption">正常功能对照</h4><p>{item.normal_control}</p></div>
   {(item.environment_summary||item.preparation_summary)&&<div><h4 className="jj-title-caption">当前准备</h4>{item.environment_summary&&<p>{item.environment_summary}</p>}{item.preparation_summary&&<p>{item.preparation_summary}</p>}</div>}
   {Boolean(item.definition_changes?.length)&&<div><h4 className="jj-title-caption">本次定义变化</h4><ul>{item.definition_changes!.map(change=><li key={change}>{change}</li>)}</ul></div>}
  </section></div>
  <div className="jj-validation-supplement">{item.current_materials.length>0&&<details><summary>核对已有材料与变化后的处理</summary><ul>{item.current_materials.map((material,index)=><li key={index}><strong>{material.member_label||({identity:'测试账号',execution:'操作流程',resource:'具体资源',evidence:'结果证明',recovery:'恢复方式'} as Record<string,string>)[material.kind]}</strong>：{material.compatible_with_definition===false?'原配置保留，新定义需重核':statuses[material.status]??'待核对'}<p>{material.explanation} {material.next_step}</p></li>)}</ul></details>}<details><summary>需要哪些准备</summary><ul>{item.preparation_requirements.map(value=><li key={value}>{value}</li>)}</ul></details></div>
  {preparationHref&&<footer><ActionLink href={preparationHref}>准备并核对这项要求</ActionLink></footer>}
 </article>
}
