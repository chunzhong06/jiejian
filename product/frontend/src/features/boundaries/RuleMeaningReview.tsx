// 同级选择展示业务解释、纠正和待定；这里只整理输入，人的决定由服务端保存。
import { Button, Checkbox, Input, Radio } from 'antd'
import { useEffect, useState } from 'react'
import type { MeaningChoice, RuleCandidateView } from '../../api/boundaries/ruleCandidates'
import { useTaskGuard } from '../../shared/runtime/editGuard'

type Draft = {choice?:string; correction:string; dismiss:boolean}
function savedDraft(value:RuleCandidateView, id:string):Draft {
  const record=value.scenario_decisions?.find(item=>item.scenario_id===id)
  return {choice:record?.status==='SELECT'?record.decision?.option_id??undefined:record?.status==='DEFER'?'DEFER':['CORRECT','DISMISS'].includes(record?.status??'')?'CORRECT':undefined,
    correction:record?.decision?.correction??'',dismiss:record?.status==='DISMISS'}
}
const sameDraft=(left:Draft,right:Draft)=>left.choice===right.choice&&(left.choice!=='CORRECT'||left.correction.trim()===right.correction.trim()&&left.dismiss===right.dismiss)

export function RuleMeaningReview({ value, busy, onSave, readOnly=false }: {value:RuleCandidateView; busy:boolean; onSave:(choice:MeaningChoice)=>void;readOnly?:boolean}) {
  const scenarios=value.candidate.content.scenarios??[]
  const [index,setIndex]=useState(0), [drafts,setDrafts]=useState<Record<string,Draft>>({})
  const scenario=scenarios[index]??scenarios[0]
  const recorded=value.scenario_decisions?.find(item=>item.scenario_id===scenario?.scenario_id)
  // 草稿按候选和情境依据保存；其他页保存导致修订变化时，不清空尚未提交的选择。
  const draftKey=(item:typeof scenarios[number])=>`${value.candidate.candidate_id}:${item.scenario_id}:${item.scenario_fingerprint}`
  const draft=scenario?(drafts[draftKey(scenario)]??savedDraft(value,scenario.scenario_id)):{correction:'',dismiss:false}
  const {choice,correction,dismiss}=draft
  const update=(change:Partial<Draft>)=>{if(scenario)setDrafts(current=>({...current,[draftKey(scenario)]:{...draft,...change}}))}
  const dirty=scenarios.filter(item=>drafts[draftKey(item)]&&!sameDraft(drafts[draftKey(item)],savedDraft(value,item.scenario_id))).length
  const currentDirty=Boolean(scenario&&!sameDraft(draft,savedDraft(value,scenario.scenario_id)))
  const saved=scenarios.filter(item=>value.scenario_decisions?.some(record=>record.scenario_id===item.scenario_id&&record.decision)).length
  useTaskGuard(!readOnly&&dirty>0)
  useEffect(()=>{
    if(readOnly||!dirty)return
    const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''}
    window.addEventListener('beforeunload',warn)
    return ()=>window.removeEventListener('beforeunload',warn)
  },[dirty,readOnly])
  useEffect(()=>setDrafts({}),[value.candidate.candidate_id])
  useEffect(()=>setIndex(current=>Math.min(current,Math.max(0,scenarios.length-1))),[value.candidate.candidate_id,scenarios.length])
  if(!scenario)return null
  if(readOnly)return <section className="rule-meaning" aria-label="当时的含义核对">{scenarios.map(item=>{
    const state=value.scenario_decisions?.find(state=>state.scenario_id===item.scenario_id)
    const choice=item.options.find(option=>option.option_id===state?.decision?.option_id)
    return <div key={item.scenario_id}><h3>{item.question}</h3><p>{state?.status==='SELECT'&&choice?`当时选择：${choice.label}`:state?.status==='DISMISS'?'当时已说明这处情境不适用。':'这份记录没有可核对的含义选择。'}</p>{state?.decision?.correction&&<p>{state.decision.correction}</p>}</div>
  })}</section>
  const option=scenario.options.find(item=>item.option_id===choice)
  const entities=value.meaning_context??value.candidate.content
  const actorNames=new Map(entities.actors.map(item=>[item.item_id,item.display_name]))
  const actions=new Map(entities.actions.map(item=>[item.item_id,item]))
  const correctionMode=choice==='CORRECT'
  const save=()=>onSave({scenario_id:scenario.scenario_id,scenario_fingerprint:scenario.scenario_fingerprint,
    action:correctionMode?(dismiss?'DISMISS':'CORRECT'):choice==='DEFER'?'DEFER':'SELECT',
    ...(option?{option_id:option.option_id}:{}),...(correctionMode?{correction:correction.trim()}:{})})
  return <section className="rule-meaning" aria-label="含义核对">
    <div className="rule-candidates-heading"><h3>含义核对</h3>{scenarios.length>1&&<span>{index+1} / {scenarios.length}</span>}</div>
    <p role="status">已保存 {saved} / {scenarios.length} 处{dirty>0?`；${dirty} 处修改尚未保存，切换情境会保留选择。`:''}</p>
    <p className="editorial-muted">对应原话：{scenario.original_excerpt}</p>
    <h3>{scenario.question}</h3>
    <p className="editorial-muted">按原始业务要求核对；选项不符合原意时，请选“不是这个意思”并说明。保存选择后仍需审阅完整变更。</p>
    {recorded?.status!=='NEEDS_DECISION'&&recorded?.decision&&<p role="status">{recorded.status==='SELECT'?'已保存你的选择，可在下方修改。':recorded.status==='DEFER'?'已标记为暂不确定，明确后再继续审阅。':recorded.status==='DISMISS'?'你已说明这处情境不适用。':`你的纠正：${recorded.decision.correction}`}</p>}
    {currentDirty&&<p role="status">当前选择尚未保存，请点击下方保存按钮。</p>}
    <Radio.Group className="rule-meaning-options product-choice-cards" aria-label={scenario.question} value={choice} disabled={busy} onChange={event=>update({choice:event.target.value})}>
      {scenario.options.map(item=><Radio value={item.option_id} key={item.option_id}><strong>{item.label}</strong><span>{item.explanation}</span></Radio>)}
      <Radio value="CORRECT"><strong>不是这个意思</strong><span>说明实际要求，让 Agent 重新整理。</span></Radio>
      <Radio value="DEFER"><strong>暂不确定</strong><span>保留问题，明确后再继续。</span></Radio>
    </Radio.Group>
    {correctionMode&&<div className="rule-meaning-correction"><label htmlFor="rule-meaning-correction">请说明你的意思</label><Input.TextArea id="rule-meaning-correction" value={correction} maxLength={2048} autoSize={{minRows:3,maxRows:8}} disabled={busy} onChange={event=>update({correction:event.target.value})}/><Checkbox checked={dismiss} disabled={busy} onChange={event=>update({dismiss:event.target.checked})}>这处情境不适用，保存原因并结束这个问题</Checkbox></div>}
    {option&&<div className="rule-meaning-preview"><h4>你的选择将形成的要求</h4>{option.replacements.map(item=>{
      const owner=actorNames.get(item.resource_owner_actor_item_id)??'资源所属角色'
      const resourceOwner=item.relation==='OWNS'?'自己':item.relation==='SAME_ROLE_OTHER_ACCOUNT'?`另一个${owner}账号`:owner
      return <div key={item.item_id}><p>{actorNames.get(item.subject_actor_item_id)??'该角色'}对{resourceOwner}拥有的资源，{item.expectation==='ALLOW'?'可以':'不得'}{actions.get(item.business_action_item_id)?.display_name??'执行这项动作'}。</p><p>针对的结果：{item.protected_effect_item_ids.map(id=>actions.get(item.business_action_item_id)?.effect_catalog.find(effect=>effect.item_id===id)?.business_label??'结果名称待核对').join('、')}</p></div>
    })}</div>}
    <div className="rule-meaning-actions">{scenarios.length>1&&<div><Button disabled={busy||index===0} onClick={()=>setIndex(index-1)}>上一处</Button><Button disabled={busy||index===scenarios.length-1} onClick={()=>setIndex(index+1)}>下一处</Button></div>}<Button disabled={busy||!choice||!currentDirty||(correctionMode&&!correction.trim())} loading={busy} onClick={save}>{option?'保存这个含义':choice==='DEFER'?'保存待定':'保存说明'}</Button></div>
  </section>
}
