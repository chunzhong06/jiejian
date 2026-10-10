// 汇总与详细表格共用当前材料状态文案；批次执行成功不能替代当前依赖核验。
import type { PreparationItem } from '../../../api/preparation/preparation'

export function materialStatus(items: PreparationItem[]): string {
  if (!items.length || items.every(item => item.status === 'NOT_REQUIRED')) return '无需准备'
  if (items.every(item => ['SATISFIED', 'NOT_REQUIRED'].includes(item.status))) return '可复用'
  if (items.some(item => item.status === 'BLOCKED')) return '需要先确认'
  if (items.some(item => item.binding_fingerprint || item.status === 'STALE')) return '已保存，需复核'
  return '需要准备'
}
