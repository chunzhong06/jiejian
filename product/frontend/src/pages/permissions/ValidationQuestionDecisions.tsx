import {useState} from 'react'
import {ruleCandidatesApi,type RuleCandidateView,type ScopeReview,type ScopeChoice} from '../../entities/permission/api/ruleCandidates'
import {Choice} from '../../shared/ui/Choice'
import {Field,TaskActions,ObjectHeading} from '../../shared/ui/layout'
import {Button} from '../../shared/ui/actions'
import {Badge} from '../../shared/ui/feedback'

export function ValidationQuestionDecisions({projectId,value,busy,onChange,onRun}:{projectId:string;value:RuleCandidateView;busy:boolean;onChange:(value:RuleCandidateView)=>void;onRun:(callback:()=>Promise<unknown>)=>Promise<void>}){
  return <>{value.scope_review?.filter(item=>item.source.source_excerpt.startsWith('权限边界核对 ')).map(item=><QuestionDecision key={value.candidate.revision+':'+item.fingerprint} projectId={projectId} value={value} item={item} busy={busy} onChange={onChange} onRun={onRun}/>)}</>
}

function QuestionDecision({projectId,value,item,busy,onChange,onRun}:{projectId:string;value:RuleCandidateView;item:ScopeReview;busy:boolean;onChange:(value:RuleCandidateView)=>void;onRun:(callback:()=>Promise<unknown>)=>Promise<void>}){
  const [choice,setChoice]=useState<ScopeChoice['disposition']|''>(''),[meaning,setMeaning]=useState(item.decision?.requirement??''),[reason,setReason]=useState('')
  const candidate=value.candidate
  const key='jiejian.validation-answer:'+projectId+':'+candidate.candidate_id+':'+candidate.revision+':'+item.source.requirement_id
  const [pending,setPending]=useState<{operation:string;choice:ScopeChoice}|null>(()=>{
    const saved=sessionStorage.getItem(key);return saved?JSON.parse(saved):null
  })
  const save=()=>onRun(async()=>{
    if(!choice&&!pending)return
    // 未知响应保留原决定和原键；输入变化不能成为同一操作的新请求。
    const command=pending??{operation:crypto.randomUUID().replaceAll('-',''),choice:{requirement_id:item.source.requirement_id,requirement_fingerprint:item.fingerprint,disposition:choice as ScopeChoice['disposition'],requirement:meaning.trim(),reason:reason.trim(),time_scope:choice==='OUT_OF_SCOPE'?'NOT_APPLICABLE' as const:'CHECK_WINDOW' as const}}
    sessionStorage.setItem(key,JSON.stringify(command));setPending(command)
    const prior=pending?await ruleCandidatesApi.receipt(projectId,command.operation,'DECIDE'):undefined
    const updated=prior?.candidate??await ruleCandidatesApi.scope(projectId,candidate.candidate_id,candidate.revision,candidate.basis_id,command.operation,command.choice)
    sessionStorage.removeItem(key);setPending(null);onChange(updated)
  })
  return <article className="jj-review-rule jj-business-answer"><ObjectHeading level={3} title={item.source.title} status={<Badge>{item.status==='CONFIRMED'?'已保存决定':item.status==='DEFER'?'稍后决定':'待决定'}</Badge>}/>
    {item.status==='CONFIRMED'?<><p>{item.decision?.requirement}</p><p className="jj-small">{item.decision?.reason}</p>{item.decision?.disposition==='IN_SCOPE'&&!item.source.permission_item_ids.length&&<p>业务含义已保存。接下来由 Agent 沿同一候选补充权限、受保护结果和正常对照，再审阅提案。</p>}</>:<>
      <Field measure="short" label="如何处理"><Choice measure="short" disabled={busy} value={choice} onValueChange={selected=>setChoice(selected as ScopeChoice['disposition'])}><option value="">选择处理方式</option><option value="IN_SCOPE">补充为业务要求</option><option value="OUT_OF_SCOPE">当前业务不适用</option><option value="DEFER">暂不确定</option></Choice></Field>
      <div className="jj-business-answer-fields"><Field measure="long" label="实际业务含义"><textarea rows={4} value={meaning} disabled={busy} maxLength={1024} onChange={event=>setMeaning(event.target.value)}/></Field>
      <Field measure="long" label="判断依据" hint="说明这个判断来自哪项业务约定。暂不确定时保留问题，继续原候选核对。"><textarea rows={4} value={reason} disabled={busy} maxLength={512} onChange={event=>setReason(event.target.value)}/></Field></div>
      {pending&&<p>上次保存结果尚待确认。继续时先查询原决定，按原内容恢复。</p>}
      <TaskActions><Button busy={busy} disabled={busy||(!pending&&(!choice||!meaning.trim()||!reason.trim()))} onClick={()=>void save()}>{pending?'查询并接续原决定':'保存业务决定'}</Button></TaskActions>
    </>}
  </article>
}
