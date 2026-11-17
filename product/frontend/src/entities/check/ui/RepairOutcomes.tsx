import type {RepairComparisonRow} from '../api/repairs'
import {groupRepairComparisons} from '../model/repairComparisons'
import {Badge,Notice} from '../../../shared/ui/feedback'
import './repair-outcomes.css'

/** 按原比较事实合并用途，缺少准确对应时保留待确认，不以总体完成代替逐项结果。 */
export function RepairOutcomes({rows}:{rows:RepairComparisonRow[]}){
  const entries=groupRepairComparisons(rows)
  if(!entries.length)return <Notice tone="caution">尚无可读取的逐项复验结果，请查看本次报告。</Notice>
  return <ul className="jj-repair-outcomes" aria-label="具名复验结果">{entries.map(({key,row,roles})=>{
    const matched=row.match_status==='MATCHED',safe=matched&&row.after_verdict==='SAFE'
    const label=safe?roles.includes('DENY')?'原问题已解决':'正常操作保留':!matched?'对应待核对':row.after_verdict==='VULNERABLE'?'不符合规则':'证据不足'
    return <li key={key} data-purpose={roles.includes('DENY')?'original':'normal'}><div className="jj-object-line"><strong>{row.subject_label??'原测试账号'} · {row.action_label}</strong><Badge tone={safe?'positive':matched&&row.after_verdict==='VULNERABLE'?'negative':'caution'}>{label}</Badge></div><p>{row.resource_owner_label??'原资源所有者'}的资源 · {row.resource_id}</p><small>{roles.includes('DENY')?'原权限问题':roles.includes('SELECTED_ALLOW')&&roles.includes('REGRESSION')?'正常对照与功能回归':roles.includes('SELECTED_ALLOW')?'正常操作对照':'正常功能回归'}</small></li>
  })}</ul>
}
