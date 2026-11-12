import type {RepairComparisonRow} from '../api/repairs'

/** 合并同一实际用例的多个用途；对象、观察或前后引用不同的行继续分开。 */
export function groupRepairComparisons(rows:RepairComparisonRow[]){
  const entries=new Map<string,{row:RepairComparisonRow;roles:Set<RepairComparisonRow['role']>}>()
  for(const row of rows){
    const {role,...facts}=row
    const key=JSON.stringify(Object.entries({...facts,effect_labels:[...row.effect_labels].sort()}).sort(([left],[right])=>left.localeCompare(right)))
    const existing=entries.get(key)
    if(existing)existing.roles.add(role)
    else entries.set(key,{row,roles:new Set([role])})
  }
  return [...entries].map(([key,item])=>({key,row:item.row,roles:[...item.roles]}))
}
