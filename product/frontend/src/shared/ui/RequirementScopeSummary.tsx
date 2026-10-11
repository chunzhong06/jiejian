// 展示预览或已发布快照中的范围；未纳入项持续可见，不把准备和业务建议说成检查通过。
import type {RequirementScope} from '../../api/checks/currentChecks'
import './requirement-scope.css'

export function RequirementScopeSummary({scopes,historical=false}:{scopes:RequirementScope[];historical?:boolean}) {
  if(!scopes.length)return null
  const items=scopes.flatMap(scope=>scope.requirements.map(item=>({...item,candidate:scope.candidate_id,revision:scope.revision})))
  const included=items.filter(item=>item.disposition==='IN_SCOPE'),other=items.filter(item=>item.disposition!=='IN_SCOPE')
  return <section className="requirement-scope-summary" aria-label="已确认的业务检查范围"><header><div><h3>{historical?'这份结果适用于哪些要求？':'这些业务动作要满足什么要求？'}</h3><p>{historical?'按本轮保存的范围解读结果；每项是否通过，请看对应检查结论。':'下列要求说明本轮检查的目标；开始前还会核对材料是否齐全。'}</p></div><span><strong>{included.length}</strong> 项已纳入</span></header>
    <div className="requirement-scope-columns" aria-hidden="true"><span>保留的业务要求</span><span>观察范围</span><span>对应权限</span></div>
    <ul>{included.map(item=><li key={`${item.candidate}:${item.requirement_id}`}><p>{item.requirement}</p><span className="requirement-scope-time">{item.time_scope==='CHECK_WINDOW'?'本次检查过程':item.time_scope==='HISTORY'?'包含此前历史':'对应业务结果'}</span><span className="requirement-scope-count">{item.permissions.length} 条</span></li>)}</ul>
    {!!other.length&&<details><summary>哪些内容不包含在本轮结论中？ · {other.length} 项</summary><p>以下内容仍保留在业务范围记录中，本轮结果不能证明它们通过。</p>{other.map(item=><div className="requirement-scope-other" key={`${item.candidate}:${item.requirement_id}`}><strong>{item.disposition==='PREPARATION'?'仅用于准备':'本轮未检查'}</strong><p>{item.requirement}</p></div>)}</details>}
  </section>
}
