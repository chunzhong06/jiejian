// 只翻译已发布的节点、原因和定位精度，不从文案、时间或布局派生安全结论。
import type { ActionResultStory, StoryTraceEvent } from '../../api/currentChecks'

export const traceKindLabels = { ENTRY: '请求进入', IDENTITY: '身份识别', AUTHORIZATION: '权限判断', PERSISTENT_EFFECT: '持久业务变化', MESSAGE: '任务派发', DELEGATION: '委托执行', FINAL_EFFECT: '最终业务结果', RECOVERY: '恢复操作' }
export const breakpointLabels = {
  AUTHORIZATION_MISSING: '关键操作缺少权限检查', AUTHORIZATION_LATE: '权限检查介入过晚',
  AUTHORIZATION_BYPASS: '业务操作绕过了权限检查', IDENTITY_SUBSTITUTION: '执行身份发生替换',
  AUTHORITY_EXPANSION: '后台执行的权限范围扩大', COMPENSATION_MASKING: '后续恢复掩盖了已经发生的后果',
}
export const precisionLabels = { EXACT: '精确定位', RANGE: '范围定位', VIOLATION_ONLY: '仅确认后果' }
export const precisionDescriptions = {
  EXACT: '已发布证据支持定位到所标记的节点。',
  RANGE: '现有证据只能确定一个区间，不能指定其中某个节点。',
  VIOLATION_ONLY: '业务后果已确认，现有路径证据不足以进一步定位。',
}
const reasonLabels: Record<string, string> = {
  TRACE_PARENT_MISSING: '部分事件缺少前序记录，无法还原完整关联。',
  TRACE_SOURCE_INCOMPLETE: '审计来源没有提供完整记录。',
  TRACE_EVENT_CONFLICT: '来源中的事件记录存在冲突。',
  TRACE_CORRELATION_INVALID: '部分记录无法与本项检查可靠关联。',
  TRACE_EVENT_INVALID: '部分事件未通过格式核验。',
  TRACE_GRAPH_INVALID: '事件关系未通过完整性核验。',
  TRACE_BUDGET_EXCEEDED: '本轮采集达到记录上限，路径可能不完整。',
  TRACE_EVENTS_UNAVAILABLE: '本轮没有取得可展示的执行事件。',
  TRACE_EVIDENCE_INCOMPLETE: '定位所需的执行证据不完整。',
  BREAKPOINT_RANGE_ONLY: '已有证据仅支持区间，无法确定唯一节点。',
  BREAKPOINT_TRACE_UNRESOLVED: '已有路径不足以确定断裂位置。',
}
export function traceEventLabel(event: StoryTraceEvent) {
  return event.kind === 'AUTHORIZATION' && event.authorization_decision
    ? `权限判断 · ${event.authorization_decision === 'DENY' ? '拒绝' : '允许'}` : traceKindLabels[event.kind]
}
export function traceEventContext(event: StoryTraceEvent, action: ActionResultStory) {
  const effects = action.fact_comparison.effects.filter(item => item.effect_id === event.effect_id || event.dispatch_effect_ids.includes(item.effect_id))
  return effects.map(item => item.business_label).join('、') || event.source_component
}
export function traceLimitations(action: ActionResultStory) {
  const codes = [...(action.execution_path?.reason_codes ?? []), ...(action.breakpoint?.reason_codes ?? [])]
  const labels = [...new Set(codes.map(code => reasonLabels[code]).filter(Boolean))]
  if (!labels.length && (!action.execution_path?.complete || action.breakpoint?.precision !== 'EXACT'))
    labels.push('当前发布材料不足以还原更完整的执行关系；不根据时间或页面回应补画路径。')
  return labels
}
