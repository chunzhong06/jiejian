// 独立核对问题与限制；不制造权限选项，决定与原问题一起保留，未知响应沿父级回执恢复。
import { useEffect, useState } from 'react'
import { Button, Input, Select } from 'antd'
import type { BoundaryChoice, BoundaryReview as ReviewItem, RuleCandidateView } from '../../api/boundaries/ruleCandidates'
import { useTaskGuard } from '../../shared/runtime/editGuard'

const labels: Record<BoundaryChoice['outcome'], string> = {
  NOT_SEPARATE_ACTION: '不作为独立业务动作', AGENT_OVERINTERPRETATION: 'Agent 扩大或误解了原要求',
  REPRESENTED_BY_RULES: '实际要求已由下列权限表达', BUSINESS_RULE: '真实要求，仍需补充规则',
  PREPARATION_DEPENDENCY: '执行前提，仍需核验准备条件', EVIDENCE_GAP: '真实要求，缺少证明',
  COVERAGE_GAP: '真实要求，检查入口尚未覆盖', DEFER: '暂不能确定',
}
const nextSteps: Partial<Record<BoundaryChoice['outcome'],string>> = {
  BUSINESS_RULE:'下一步：请 Agent 补充候选中的真实权限要求，再读取并确认对应权限。',
  PREPARATION_DEPENDENCY:'下一步：补齐执行前提的实现与核验依据。分类本身不表示前提已满足，接口冲突也不能当作权限拒绝。',
  EVIDENCE_GAP:'下一步：补齐覆盖所需过程、主体和资源的证明。不能把过程要求缩减成只看最终状态。',
  COVERAGE_GAP:'下一步：逐个入口补齐覆盖并保留合法对照。合并业务动作不代表多个接口已经取证。',
  DEFER:'下一步：核对原始业务约定。尚不确定时保留问题，确认实际要求后再处理。',
}

function ReviewQuestion({item, value, disabled, readOnly, onSave}: {item:ReviewItem; value:RuleCandidateView; disabled:boolean; readOnly:boolean; onSave:(choice:BoundaryChoice)=>void}) {
  const [outcome,setOutcome] = useState<BoundaryChoice['outcome']|undefined>()
  const [reason,setReason] = useState('')
  const [requirement,setRequirement] = useState('')
  const [permissions,setPermissions] = useState<string[]>([])
  useTaskGuard(!readOnly && Boolean(outcome || reason || requirement))
  // 只清理本问题保存成功或依据失效的草稿，其他问题保存产生的新修订不丢弃当前输入。
  useEffect(()=>{setOutcome(undefined);setReason('');setRequirement('');setPermissions([])},[item.issue_fingerprint,item.decision?.output_revision])
  const id = item.issue_id
  const resolved = outcome && ['NOT_SEPARATE_ACTION','AGENT_OVERINTERPRETATION','REPRESENTED_BY_RULES'].includes(outcome)
  return <article className="boundary-review-question">
    <div className="boundary-review-heading"><h3>{item.text}</h3><span>{({NEEDS_DECISION:'待核对',STALE:'依据变化，需重新确认',OPEN:'仍有缺口',RESOLVED:'边界已确认'})[item.status]}</span></div>
    <p className="editorial-muted">{item.source==='unsupported_constraints' ? 'Agent 记录的限制' : '待核对问题'}</p>
    {item.decision && <div className="boundary-review-decision"><p>修订 {item.decision.output_revision} 的决定：{labels[item.decision.outcome]}</p><p>判断依据：{item.decision.reason}</p><p>保留的实际要求：{item.decision.retained_requirement}</p>{!!item.decision.permission_item_ids?.length && <p>对应权限：{item.decision.permission_item_ids.join('、')}</p>}</div>}
    {item.decision && item.blocking && nextSteps[item.decision.outcome] && <p>{nextSteps[item.decision.outcome]}</p>}
    {!readOnly && <details><summary>{item.decision ? '重新核对这条问题' : '核对这条问题'}</summary>
      <label htmlFor={`${id}-kind`}>这条问题属于哪种情况</label>
      <Select id={`${id}-kind`} value={outcome} disabled={disabled} placeholder="请选择实际情况" onChange={setOutcome}
        options={Object.entries(labels).filter(([key])=>item.source!=='unsupported_constraints' || !['NOT_SEPARATE_ACTION','REPRESENTED_BY_RULES'].includes(key)).map(([key,label])=>({value:key,label}))}/>
      <label htmlFor={`${id}-reason`}>判断依据</label>
      <Input.TextArea id={`${id}-reason`} value={reason} onChange={event=>setReason(event.target.value)} disabled={disabled} maxLength={512} autoSize={{minRows:2,maxRows:5}} placeholder="说明为什么这样判断；没有原话或证据时请写暂不能确定。"/>
      <label htmlFor={`${id}-requirement`}>仍然需要满足的实际业务要求</label>
      <Input.TextArea id={`${id}-requirement`} value={requirement} onChange={event=>setRequirement(event.target.value)} disabled={disabled} maxLength={1024} autoSize={{minRows:2,maxRows:6}} placeholder="完整保留允许、禁止、过程要求及需要覆盖的入口，不能仅写接受风险。"/>
      {outcome==='REPRESENTED_BY_RULES' && <><label htmlFor={`${id}-rules`}>对应的候选权限</label><Select id={`${id}-rules`} mode="multiple" value={permissions} onChange={setPermissions} disabled={disabled} options={value.candidate.content.permissions.map(rule=>({value:rule.item_id,label: `${rule.expectation==='ALLOW'?'允许':'禁止'} · ${value.candidate.content.examples.find(example=>example.permission_item_id===rule.item_id)?.description ?? rule.item_id}`}))}/></>}
      <p className="editorial-muted">{resolved ? '只确认业务边界，不代表证据齐全或检查通过。原问题与决定会保留。' : '此分类仍会阻止完整检查；需要补齐实际能力或材料，不能靠确认消除缺口。'}</p>
      <div className="boundary-review-actions"><Button disabled={disabled || !outcome || !reason.trim() || !requirement.trim() || outcome==='REPRESENTED_BY_RULES' && !permissions.length} onClick={()=>outcome && onSave({issue_id:id,issue_fingerprint:item.issue_fingerprint,outcome,reason,retained_requirement:requirement,permission_item_ids:outcome==='REPRESENTED_BY_RULES'?permissions:[]})}>保存这条核对</Button></div>
    </details>}
  </article>
}

export function BoundaryReview({value,readOnly,busy,onSave}: {value:RuleCandidateView;readOnly:boolean;busy:boolean;onSave:(choice:BoundaryChoice)=>void}) {
  if (!value.boundary_reviews?.length) return null
  return <section className="boundary-review" aria-label="业务边界核对"><h2>业务边界核对</h2><p>这些问题可以直接核对。无需新增权限选项；真实的准备、证据和覆盖缺口会继续保留。</p><p className="editorial-muted">保存核对后，这份候选中的未决范围会持续阻止本项目的完整检查；归档或另建候选不会清除它们。例子补充可沿用决定，原文、角色、动作或权限变化后需要重新确认。</p>
    {value.boundary_reviews.map(item=><ReviewQuestion key={`${value.candidate.candidate_id}:${item.issue_id}`} item={item} value={value} readOnly={readOnly} disabled={busy} onSave={onSave}/>)}</section>
}
