// 将已发布的阶段、来源原因和效果状态翻译为说明，不改变任何安全判断。
import type { CheckObservation, EvidenceExplanation, ObservationReading } from '../../api/currentChecks'

export const phaseLabels = { BASELINE: '初始状态', BEFORE: '操作前', AFTER: '操作后', EVENTUAL: '最终观察', RECOVERY: '恢复后' }
export const sourceLabels: Record<string, string> = { OWNER_API: '资源服务', READ_ONLY_SQLITE: '业务数据', STRUCTURED_AUDIT_LOG: '审计记录', ASYNC_TASK_STATUS: '后台任务', AZURE_QUEUE_PEEK: '消息队列' }

// 新结果由服务端统一解释；旧响应只能保守回退，不把未知状态改成采集成功。
export function sourceReading(source: EvidenceExplanation): ObservationReading {
  if (source.reading) return source.reading
  const fact = source.observed_fact
  const known = fact.complete && fact.reliable && fact.correlated && fact.authoritative && (fact.state === 'CONFIRMED' || fact.state === 'ABSENT' && fact.closure === 'CLOSED')
  return { ...observationStatus(fact), kind: known ? 'OBSERVED' : 'INCOMPLETE', attention: !known }
}

export function observationGroups(sources: EvidenceExplanation[]) {
  const grouped = new Map<string, EvidenceExplanation[]>()
  const order = { BASELINE: 0, BEFORE: 1, AFTER: 2, EVENTUAL: 3, RECOVERY: 4 }
  for (const source of sources) {
    const fact = source.observed_fact
    const key = JSON.stringify([fact.observer_id, fact.effect_id, fact.proof_fingerprint, fact.level])
    grouped.set(key, [...(grouped.get(key) ?? []), source])
  }
  return [...grouped.entries()].map(([key, values]) => {
    const stages = [...values].sort((a,b) => order[a.observed_fact.phase] - order[b.observed_fact.phase] || a.observed_fact.window_end_us - b.observed_fact.window_end_us)
    // 恢复不能覆盖本次操作的最终记录；不按“最好状态”挑选，也不跳过失败的最终阶段。
    const execution = stages.filter(item => ['AFTER','EVENTUAL'].includes(item.observed_fact.phase))
    const latest = execution.at(-1) ?? stages.at(-1)!
    const gaps = stages.filter(item => sourceReading(item).attention)
    return { key, latest, stages, gaps }
  })
}
export function observationStatus(value: CheckObservation): { label: string; detail: string } {
  const reasons = value.reason_codes ?? []
  if (reasons.includes('OBSERVER_PHASE_UNAVAILABLE')) return { label: '本阶段不采集', detail: '该来源只在其支持的阶段运行，并非读取失败。' }
  if (value.level !== 'VERDICT_REQUIRED' && reasons.includes('SOURCE_RECORDS_AVAILABLE')) return { label: '已取得关联过程记录', detail: '用于追踪执行或定位问题，不能单独证明最终业务结果。' }
  if (value.level !== 'VERDICT_REQUIRED' && reasons.includes('SOURCE_WINDOW_EMPTY')) return { label: '当前窗口未见关联消息', detail: '仅说明本次队列观察窗口，不代表交付包不存在。' }
  if (reasons.includes('AUDIT_TAG_NOT_FOUND') && ['BASELINE','BEFORE'].includes(value.phase)) return { label: '尚无本次操作事件', detail: '操作尚未开始；这一记录不用于证明业务后果。' }
  if (['BASELINE','BEFORE','RECOVERY'].includes(value.phase) && reasons.some(reason => ['OBSERVATION_UNINTERPRETED','DISCLOSURE_PROJECTION_INCOMPLETE'].includes(reason))) return { label: value.phase === 'RECOVERY' ? '恢复对照记录' : '初始对照记录', detail: '用于状态对照；初始与恢复是否核对完成，以本项检查的独立核对结果为准。' }
  if (reasons.includes('AZURE_QUEUE_MESSAGE_LIMIT')) return { label: '消息读取达到上限', detail: '本次只取得部分队列记录，不能据此确认完整消息窗口。' }
  if (reasons.includes('EFFECT_PROJECTOR_UNSUPPORTED')) return { label: '不能用于判断该业务后果', detail: '此来源用于过程追踪，当前没有把它转换为这类业务结果证明的能力。' }
  if (value.state === 'UNKNOWN' || !(value.complete && value.reliable && value.correlated && value.authoritative)) {
    if (reasons.includes('TEMPORAL_WINDOW_OPEN') || reasons.includes('OBSERVATION_WINDOW_INCOMPLETE')) return { label: '观察窗口尚未闭合', detail: '这一阶段尚不足以判断最终业务结果。' }
    return { label: '观察依据不完整', detail: '该记录未形成完整的业务结果证明；可能涉及读取、关联或解析缺口，具体原因保留在记录中。' }
  }
  if (value.state === 'ABSENT' && value.closure !== 'CLOSED') return { label: '暂未观察到', detail: '观察窗口尚未闭合，不能确认该业务后果不存在。' }
  return { label: value.state === 'CONFIRMED' ? '已观察到业务结果' : '闭合窗口内未发生', detail: value.level === 'VERDICT_REQUIRED' ? '是否构成权限问题，由本轮完整检查判断。' : '这是一项辅助观察，不能替代必要证明。' }
}
