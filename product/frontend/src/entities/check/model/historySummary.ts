import type {CheckHistoryItem} from '../api/currentChecks'

/** 修改说明来自服务端准确引用；缺失时保留操作名，不以时间或当前源码补名。 */
export function historySummary(item:CheckHistoryItem){
  const operations=item.action_labels.join('、')||'权限检查'
  return {
    title:item.change_label||item.change_reason||operations,
    detail:item.change_label||item.change_reason?operations:item.change_id?'修改登记说明未保留':undefined,
    purpose:item.source_run_id?'原问题复验':item.change_id?'修改后检查':item.status.routine?'方案检查':'常规检查',
  }
}
