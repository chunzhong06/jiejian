import type { ActionResultStory, ResultStory } from '../api/currentChecks'
import {text} from '../../../shared/lib/format'

export type Tone='positive'|'negative'|'caution'|'neutral'
const published:Record<string,Tone>={
  '本次权限要求已得到验证':'positive','检查结果符合已批准的权限要求':'positive',
  '已确认不应发生的业务后果':'negative','已发现规则禁止的实际结果':'negative',
  '现有证据不足以完成判断':'caution','证据或检查条件不足，尚不能确定':'caution',
}
export function judgement(action:ActionResultStory){return published[action.judgement]??'neutral'}
export const judgementLabels={positive:'符合规则',negative:'不符合规则',caution:'尚未确认',neutral:'其他结果'}
export function subject(action:ActionResultStory){return text(action.fact_comparison.planned_identity.actor_label??action.fact_comparison.planned_identity.label??'测试账号')}
export function owner(action:ActionResultStory){const identity=action.fact_comparison.planned_resource_owner;return action.permission.relation==='OWNS'?'操作账号本人':action.permission.relation==='SAME_ROLE_OTHER_ACCOUNT'?`另一个${text(identity?.actor_label??'同角色')}账号`:text(identity?.actor_label??identity?.label??'其他账号')}
export function requirement(action:ActionResultStory){return `${subject(action)}${action.permission.expectation==='ALLOW'?'可以':'不得'}${text(action.display_name)}`}
export function resultTitle(story:ResultStory){
  const issues=story.actions.filter(item=>judgement(item)==='negative').length
  if(story.repair_verification?.status==='VERIFIED'&&story.verdict!=='PASS')return story.verdict==='BLOCK'?`原问题已修复，仍有 ${issues} 项违规`:'原问题已修复，其他结果尚未确认'
  if(story.repair_verification)return {VERIFIED:'原问题已修复，正常功能保留',NOT_VERIFIED:'原问题尚未解决',INCONCLUSIVE:'证据不足，无法验收修复',STALE:'规则已变化，需要重新确认修复范围'}[story.repair_verification.status]
  const count=story.actions.filter(item=>judgement(item)==='negative').length
  return story.verdict==='PASS'?'本次范围符合权限规则':story.verdict==='BLOCK'?count?`${count} 项结果不符合权限规则`:'存在不符合权限规则的结果':'仍有检查结果无法确认'
}

export function repairGap(reasons:string[]){
  const messages:Record<string,string>={
    REPAIR_STANDARD_CHANGED:'本次采用的证明要求与原检查不同。请核对参照文件和采集方式，再复验原问题。',
    REPAIR_RUNTIME_NOT_CONFIRMED:'尚未确认本次检查实际运行的代码，暂时无法验收修复。',
    REPAIR_CONTEXT_MISMATCH:'本次检查未对应原问题的修改记录，请从该规则下重新预览复验。',
    REPAIR_CASE_NOT_UNIQUELY_MATCHED:'未能完整对应原检查场景，请核对账号、资源和检查范围。',
    REPAIR_REQUIRED_CASE_NOT_SAFE:'原问题、正常操作或相关功能中，仍有场景未通过检查。',
    REPAIR_EVIDENCE_UNAVAILABLE:'缺少可读取的完整证明记录，暂时无法验收修复。',
    REPAIR_ATTRIBUTION_INCOMPLETE:'账号、资源、操作前状态或恢复结果仍有未确认项。',
    REPAIR_STANDARD_UNAVAILABLE:'未能核对原问题要求的证明标准。',
    REPAIR_POLICY_CHANGED:'权限要求已经变化，需要重新确认原问题的适用范围。',
  }
  return reasons.map(reason=>messages[reason]).filter(Boolean)[0]??'尚未具备完整的修复验收依据，请返回权限规则核对。'
}
const businessSentences:Record<string,[string,string,string]>={
  '内部完整包已被接收':['完整收到内部包','未完整收到内部包','内部包是否完整接收尚未确认'],
  '公开展示版已被接收':['完整收到公开展示版','未完整收到公开展示版','展示版是否完整接收尚未确认'],
  '内部包曾向操作账号开放':['内部包访问权曾被开放','本次未开放内部包访问权','内部包访问权是否开放尚未确认'],
  '公开作品说明可见':['读到了公开作品说明','未读到公开作品说明','公开说明是否可读尚未确认'],
}
export function actual(effect:ActionResultStory['fact_comparison']['effects'][number]){
  // “没有发生”须同时具备闭合观察的发布判断，不能只翻译 ABSENT 字段。
  const state=effect.observed_state==='ABSENT'&&!['在已闭合的观察范围内未发生这项业务结果','本次观察已完成，未发现这项结果'].includes(effect.judgement)?'UNKNOWN':effect.observed_state
  const known=businessSentences[effect.business_label]
  return known?known[state==='CONFIRMED'?0:state==='ABSENT'?1:2]:state==='CONFIRMED'?`已确认：${text(effect.business_label)}`:state==='ABSENT'?`本次未观察到“${text(effect.business_label)}”`:`尚不能确认“${text(effect.business_label)}”`
}
export function gaps(action:ActionResultStory){const comparison=action.fact_comparison
  const values=(action.proof_coverage??[]).filter(item=>item.required_level==='VERDICT_REQUIRED'&&item.observed_state==='UNKNOWN').flatMap(item=>item.limitations.length?item.limitations:[`缺少“${text(item.business_label)}”的有效记录。`])
  if(comparison.verified_actual_identity.verification_status!=='MATCH')values.push(comparison.verified_actual_identity.verification_status==='MISMATCH'?'实际操作账号与计划不一致。':'未确认实际操作账号。')
  if(!comparison.http_surface.run_correlated)values.push('记录尚未与本次请求对应。')
  if(!comparison.http_surface.resource_correlated)values.push('记录尚未与本次资源对应。')
  if(!comparison.http_surface.baseline_trusted)values.push('未确认操作前的业务状态。')
  if(!comparison.http_surface.recovery_verified)values.push('未确认操作后的恢复状态。')
  if(action.permission.expectation==='DENY'&&!comparison.allow_control)values.push('缺少相应正常操作的检查结果。')
  return [...new Set(values.map(text))]
}
