// 将已发布的阶段、来源原因和效果状态翻译为说明，不改变任何安全判断。
import type { CheckObservation } from '../../api/currentChecks'
export function observationStatus(value: CheckObservation): { label: string; detail: string } {
  const reasons = value.reason_codes ?? []
  if (reasons.includes('OBSERVER_PHASE_UNAVAILABLE')) return { label: '本阶段不采集', detail: '该来源只在其支持的阶段运行，并非读取失败。' }
  if (value.level !== 'VERDICT_REQUIRED' && reasons.includes('SOURCE_RECORDS_AVAILABLE')) return { label: '已取得关联过程记录', detail: '用于追踪执行或定位问题，不能单独证明最终业务结果。' }
  if (value.level !== 'VERDICT_REQUIRED' && reasons.includes('SOURCE_WINDOW_EMPTY')) return { label: '当前窗口未见关联消息', detail: '仅说明本次队列观察窗口，不代表交付包不存在。' }
  if (reasons.includes('AUDIT_TAG_NOT_FOUND') && ['BASELINE','BEFORE'].includes(value.phase)) return { label: '尚无本次操作事件', detail: '操作尚未开始；这一记录不用于证明业务后果。' }
  if (['BASELINE','BEFORE','RECOVERY'].includes(value.phase) && reasons.some(reason => ['OBSERVATION_UNINTERPRETED','DISCLOSURE_PROJECTION_INCOMPLETE'].includes(reason))) return { label: value.phase === 'RECOVERY' ? '恢复对照记录' : '初始对照记录', detail: '用于状态对照；初始与恢复是否核对完成，以本项检查的独立核对结果为准。' }
  if (reasons.includes('AZURE_QUEUE_MESSAGE_LIMIT')) return { label: '消息读取达到上限', detail: '本次只取得部分队列记录，不能据此确认完整消息窗口。' }
  if (reasons.includes('EFFECT_PROJECTOR_UNSUPPORTED')) return { label: '不能用于判断该业务后果', detail: '此来源用于过程追踪，当前没有把它转换为这类业务结果证明的能力。' }
  if (value.state === 'UNKNOWN') {
    if (reasons.includes('TEMPORAL_WINDOW_OPEN') || reasons.includes('OBSERVATION_WINDOW_INCOMPLETE')) return { label: '观察窗口尚未闭合', detail: '这一阶段尚不足以判断最终业务结果。' }
    return { label: '观察依据不完整', detail: '该记录未形成完整的业务结果证明；可能涉及读取、关联或解析缺口，具体原因保留在记录中。' }
  }
  if (value.state === 'ABSENT' && value.closure !== 'CLOSED') return { label: '暂未观察到', detail: '观察窗口尚未闭合，不能确认该业务后果不存在。' }
  return { label: value.state === 'CONFIRMED' ? '已观察到业务结果' : '闭合窗口内未发生', detail: value.level === 'VERDICT_REQUIRED' ? '是否构成权限问题，由本轮完整检查判断。' : '这是一项辅助观察，不能替代必要证明。' }
}
