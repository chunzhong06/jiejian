// 独立核对问题与限制；不制造权限选项，决定与原问题一起保留，未知响应沿父级回执恢复。
import { useEffect, useState } from 'react'
import { Button, Input, Select } from 'antd'
import type { BoundaryChoice, BoundaryReview as ReviewItem, RuleCandidateView, CoverageChoice } from '../../api/boundaries/ruleCandidates'
import {CoverageReview} from './CoverageReview'
import { useTaskGuard } from '../../shared/runtime/editGuard'
import { StatusBadge } from '../../shared/ui/StatusBadge'

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

function ReviewQuestion({item, value, disabled, readOnly, onSave,onCoverage}: {item:ReviewItem; value:RuleCandidateView; disabled:boolean; readOnly:boolean; onSave:(choice:BoundaryChoice)=>void;onCoverage?:(choice:CoverageChoice)=>void}) {
  const [outcome,setOutcome] = useState<BoundaryChoice['outcome']|undefined>()
  const [reason,setReason] = useState('')
  const [requirement,setRequirement] = useState('')
  const [permissions,setPermissions] = useState<string[]>([])
  const [requirements,setRequirements] = useState<string[]>([])
  useTaskGuard(!readOnly && Boolean(outcome || reason || requirement || requirements.length))
  // 只清理本问题保存成功或依据失效的草稿，其他问题保存产生的新修订不丢弃当前输入。
  useEffect(()=>{setOutcome(undefined);setReason('');setRequirement('');setPermissions([]);setRequirements([])},[item.issue_fingerprint,item.decision?.output_revision])
  const id = item.issue_id
  const planned=value.coverage_review?.some(link=>link.issue_id===id&&link.status==='PLANNED')
  const resolved = outcome && ['NOT_SEPARATE_ACTION','AGENT_OVERINTERPRETATION','REPRESENTED_BY_RULES'].includes(outcome)
  return <article className="boundary-review-question">
    <div className="boundary-review-heading"><h3>{(item.suggestion||item.decision)&&<span className="editorial-eyebrow">原问题记录</span>}{item.text}</h3><StatusBadge kind="rule" tone={item.status==='RESOLVED'?'success':item.status==='STALE'?'danger':'warning'}>{planned?'已关联 · 待准备':item.status==='RESOLVED'&&item.decision?.outcome==='AGENT_OVERINTERPRETATION'?'原问题已纠正':({NEEDS_DECISION:'待核对',STALE:'需要重新确认',OPEN:'仍有缺口',RESOLVED:'边界已确认'})[item.status]}</StatusBadge></div>
    {item.invalidation_reason&&<p className="editorial-muted">{item.invalidation_reason}</p>}
    {!readOnly&&item.suggestion&&<section className="boundary-correction" aria-label="Agent 提出的纠正建议">
      <div><span className="editorial-eyebrow">Agent 提出的修正 · 等你核对</span><h4>{labels[item.suggestion.outcome]}</h4><p>{item.suggestion.reason}</p></div>
      <div><span className="editorial-eyebrow">修正后仍须满足</span><p className="boundary-correction-requirement">{item.suggestion.retained_requirement}</p>
        {!!item.suggestion.dependencies?.requirement_ids.length&&<p className="editorial-muted">关联要求：{item.suggestion.dependencies.requirement_ids.map(id=>value.candidate.content.requirement_sources?.find(source=>source.requirement_id===id)?.title??id).join('、')}。系统同时保留相关权限、角色和动作的关联。</p>}
        <Button type="primary" disabled={disabled||Boolean(outcome||reason||requirement||requirements.length)} onClick={()=>item.suggestion&&onSave({...item.suggestion,issue_fingerprint:item.issue_fingerprint})}>确认这项修正</Button>
      </div>
      <p className="editorial-muted boundary-correction-note">确认后保存原问题、修正依据和你的决定；真实的能力或证明缺口仍需补齐。若建议不符合原意，请展开下方填写意见。</p>
    </section>}
    {item.decision ? <>
      <div className="boundary-review-decision">
        <div><p className="editorial-muted">你的决定 · 修订 {item.decision.output_revision}</p><h4>{labels[item.decision.outcome]}</h4>{item.status==='STALE' && <p className="editorial-muted">业务依据已变化，以下保留上次决定，等待重新确认。</p>}</div>
        <div className="boundary-review-retained"><p className="editorial-muted">仍须满足的业务要求</p><p>{item.decision.retained_requirement}</p>{item.blocking && <p className="boundary-review-next">{planned?'规则审阅完成后进入材料准备；系统将在检查前重新核验关联入口与证明。':nextSteps[item.decision.outcome]}</p>}</div>
      </div>
      <details className="boundary-review-evidence"><summary>查看判断依据{item.decision.permission_item_ids?.length ? '与权限引用' : ''}</summary><p>{item.decision.reason}</p>{!!item.decision.permission_item_ids?.length && <p>对应权限：{item.decision.permission_item_ids.join('、')}</p>}</details>
    </> : !item.suggestion&&<p className="editorial-muted">{item.source==='unsupported_constraints' ? '请核对 Agent 记录的限制及实际业务要求。' : '请说明这条问题的实际含义。'}</p>}
    {!readOnly && <details className={`boundary-review-editor${item.decision ? '' : ' boundary-review-editor--new'}`}><summary>{item.decision ? '重新核对这条问题' : '填写核对意见'}</summary><div className="boundary-review-form">
      <label htmlFor={`${id}-kind`}>这条问题属于哪种情况</label>
      <Select id={`${id}-kind`} value={outcome} disabled={disabled} placeholder="请选择实际情况" onChange={setOutcome}
        options={Object.entries(labels).filter(([key])=>item.source!=='unsupported_constraints' || !['NOT_SEPARATE_ACTION','REPRESENTED_BY_RULES'].includes(key)).map(([key,label])=>({value:key,label}))}/>
      <label htmlFor={`${id}-reason`}>判断依据</label>
      <Input.TextArea id={`${id}-reason`} value={reason} onChange={event=>setReason(event.target.value)} disabled={disabled} maxLength={512} autoSize={{minRows:2,maxRows:5}} placeholder="说明为什么这样判断；没有原话或证据时请写暂不能确定。"/>
      <label htmlFor={`${id}-requirement`}>仍然需要满足的实际业务要求</label>
      <Input.TextArea id={`${id}-requirement`} value={requirement} onChange={event=>setRequirement(event.target.value)} disabled={disabled} maxLength={1024} autoSize={{minRows:2,maxRows:6}} placeholder="完整保留允许、禁止、过程要求及需要覆盖的入口，不能仅写接受风险。"/>
      {outcome==='REPRESENTED_BY_RULES' && <><label htmlFor={`${id}-rules`}>对应的候选权限</label><Select id={`${id}-rules`} mode="multiple" value={permissions} onChange={setPermissions} disabled={disabled} options={value.candidate.content.permissions.map(rule=>({value:rule.item_id,label: `${rule.expectation==='ALLOW'?'允许':'禁止'} · ${value.candidate.content.examples.find(example=>example.permission_item_id===rule.item_id)?.description ?? rule.item_id}`}))}/></>}
      {!!value.candidate.content.requirement_sources?.length&&<><label htmlFor={`${id}-dependencies`}>这项判断关联哪些业务要求（可选）</label><Select id={`${id}-dependencies`} mode="multiple" value={requirements} onChange={setRequirements} disabled={disabled} placeholder="不明确时留空，按整份业务要求核对" options={value.candidate.content.requirement_sources.map(source=>({value:source.requirement_id,label:source.title}))}/><p className="editorial-muted">保存关联后，修改无关规则无需重做这项决定。相关角色、动作、权限与要求由系统一起核对。</p></>}
      <p className="editorial-muted">{!outcome?'请选择实际情况；保存意见不会批准权限。':resolved ? '只确认业务边界，不代表证据齐全或检查通过。原问题与决定会保留。' : '此分类仍会阻止完整检查；需要补齐实际能力或材料，不能靠确认消除缺口。'}</p>
      <div className="boundary-review-actions"><Button disabled={disabled || !outcome || !reason.trim() || !requirement.trim() || outcome==='REPRESENTED_BY_RULES' && !permissions.length} onClick={()=>outcome && onSave({issue_id:id,issue_fingerprint:item.issue_fingerprint,outcome,reason,retained_requirement:requirement,permission_item_ids:outcome==='REPRESENTED_BY_RULES'?permissions:[],dependencies:requirements.length?{requirement_ids:requirements,permission_item_ids:permissions}:null})}>保存这条核对</Button></div>
    </div></details>}
    {!readOnly && onCoverage && <CoverageReview item={item} value={value} disabled={disabled} onSave={onCoverage}/>}
  </article>
}

export function BoundaryReview({value,readOnly,busy,onSave,onCoverage}: {value:RuleCandidateView;readOnly:boolean;busy:boolean;onSave:(choice:BoundaryChoice)=>void;onCoverage?:(choice:CoverageChoice)=>void}) {
  if (!value.boundary_reviews?.length) return null
  const pending=value.boundary_reviews.filter(item=>item.blocking)
  const saved=value.boundary_reviews.filter(item=>!item.blocking)
  const render=(item:ReviewItem)=><ReviewQuestion key={`${value.candidate.candidate_id}:${item.issue_id}`} item={item} value={value} readOnly={readOnly} disabled={busy} onSave={onSave} onCoverage={onCoverage}/>
  return <section className="boundary-review" aria-label="业务边界核对"><header className="boundary-review-intro"><div><h2>{pending.length?'核对这几处业务含义':'业务含义已核对'}</h2><p>{pending.length?'对照旧问题与修正建议，确认它是否符合你的原意。已确认的内容可在下方回看。':'已保存的决定继续沿用；相关依据变化时会明确列出需要重新确认的内容。'}</p></div><span className="editorial-muted">{saved.length} 项已确认 · {pending.length} 项待处理</span></header>
    <details className="boundary-review-help"><summary>这些决定如何影响后续检查</summary><p>业务含义不清时先确认含义。已明确的准备、证据或覆盖缺口可关联具体权限与入口，再审阅规则；关联不代表就绪，系统在检查前重新核验。任意历史能力限制仍阻塞。原文或权限变化时重新确认，历史记录保留。</p></details>
    {pending.map(render)}{!!saved.length&&<details className="scope-records"><summary>回看已确认的 {saved.length} 项</summary>{saved.map(render)}</details>}</section>
}
