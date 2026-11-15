import type {ResultStory,RequirementCoverage} from '../../../entities/check/api/currentChecks'
import {requirement} from '../../../entities/check/model/checks'
import {ActionLink,Button} from '../../../shared/ui/actions'
import {scopedPath,withReturnDestination} from '../../../shared/lib/navigation'

/** 逐要求读取服务端覆盖事实；共享列减少重复，具体主体与来源保留在样本阅读中。 */
export function SampleCoverage({story,origin,onInspect,readOnly=false}:{story:ResultStory;origin:string;onInspect:(id:string)=>void;readOnly?:boolean}){
  const coverage=story.sample_coverage
  const label=(item:RequirementCoverage)=>{
    const action=story.actions.find(action=>action.permission.intent_id===item.permission.intent_id&&action.permission.revision===item.permission.revision&&action.permission.intent_hash===item.permission.intent_hash)
    return action?requirement(action):'冻结权限要求 · 修订 '+item.permission.revision
  }
  const prepare=(item:RequirementCoverage)=>{
    const action=story.actions.find(action=>action.permission.intent_id===item.permission.intent_id&&action.permission.revision===item.permission.revision&&action.permission.intent_hash===item.permission.intent_hash)
    return '#'+scopedPath(withReturnDestination((action?'/preparation?':'/permissions?')+new URLSearchParams({
      rule_id:item.permission.intent_id,revision:String(item.permission.revision),intent_hash:item.permission.intent_hash,
      ...(action?{action_id:action.action_id,focus:'resource',target_state:item.unchecked_states.join('、')}:{})}),origin),story.project_id)
  }
  const conditional=coverage?.filter(item=>item.applicable_states.length||item.unknown_case_ids.length)??[]
  const observed=[...new Set(conditional.flatMap(item=>item.observed_states))],remaining=[...new Set(conditional.flatMap(item=>item.unchecked_states))]
  const resources=[...new Set(coverage?.flatMap(item=>item.samples.map(sample=>sample.resource_id))??[])]
  return <section className="jj-sample-coverage" aria-label="实际样本与未查条件">
    {!coverage?.length?<p>本报告未提供可核对的样本覆盖摘要，可从各项依据阅读实际条件。</p>:<>
      {conditional.length>0&&<div className="jj-report-coverage-focus"><div><h2 className="jj-title-caption">本次实际样本</h2><p><strong>{observed.join('、')||'条件观察尚不完整'}</strong><span>{resources.join('、')}</span></p></div><div><h2 className="jj-title-caption">仍需检查</h2><p><strong>{remaining.join('、')||'未记录其他状态缺项'}</strong>{remaining.length>0&&!readOnly&&<ActionLink href={prepare(conditional.find(item=>item.unchecked_states.length)!)}>准备剩余场景</ActionLink>}</p></div></div>}
      {conditional.length>0&&<details><summary>逐条权限的覆盖情况</summary><div className="jj-scroll-table"><table className="jj-content-table" data-density="compact">
        <thead><tr><th>权限要求</th><th>本次取得结论的状态</th><th>尚未取得结论的状态</th></tr></thead>
        <tbody>{conditional.map(item=><tr key={item.permission.intent_id+'@'+item.permission.revision}>
          <th scope="row">{label(item)}</th>
          <td>{item.concluded_states.join('、')||'尚无完整结论'}<small className="jj-table-secondary">规则适用：{item.applicable_states.join('、')||'没有限定状态枚举'}</small>{item.unknown_case_ids.length>0&&<small className="jj-table-secondary">{item.unknown_case_ids.length} 个样本条件观察不完整</small>}</td>
          <td className="jj-coverage-gap">{item.unchecked_states.join('、')||'未记录其他状态缺项'}{item.unchecked_states.length>0&&!readOnly&&<ActionLink href={prepare(item)}>准备剩余场景</ActionLink>}</td>
        </tr>)}</tbody>
      </table></div></details>}
      <details><summary>阅读实际样本与观察来源</summary>{coverage.map(item=><div className="jj-sample-coverage-item" key={item.permission.intent_id+'@'+item.permission.revision}>
        <h3>{label(item)}</h3><ul>{item.samples.map(sample=><li key={sample.case_id}>
          <Button kind="quiet" onClick={()=>onInspect(sample.case_id)}>资源 {sample.resource_id} · 阅读本项依据</Button>
          <p className="jj-small">执行条件核验：{sample.conditions.length?sample.conditions.map(condition=>[condition.principal==='ANONYMOUS'?'未登录':'已登录',condition.resource_state?'数据状态 '+condition.resource_state:null].filter(Boolean).join('，')).join('；'):'没有封存可读取的条件观察'}</p>
          <details><summary>准确引用</summary><p className="jj-small">样本：{sample.case_id}；计划主体：{sample.subject_identity_id??'未登录访客'}</p>{sample.conditions.map((condition,index)=><p key={index} className="jj-small">来源：{condition.source_id} · {condition.source_fingerprint}</p>)}<p className="jj-small">证据：{sample.evidence_refs.join('、')||'没有对应证据'}</p></details>
        </li>)}</ul>
      </div>)}</details>
    </>}
  </section>
}
