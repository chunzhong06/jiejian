// 只读阶段说明使用已保存的业务、候选和批准事实；不模拟 Agent 执行，也不替代批准门禁。
import type { RuleCandidateContext } from '../../api/boundaries/ruleCandidates'
import { RulePreparationStages } from '../../shared/ui/RulePreparationStages'

export function RulePreparationProgress({ context }: { context: RuleCandidateContext }) {
  const source = context.source_summary
  if (!source) return null
  if((context.formal_permission_count??0)>0)return <p className="rule-handoff-saved">沿用当前 {context.formal_permission_count} 条正式规则。本次只核对新增或调整，批准前现有规则保持生效。</p>
  const pending = context.candidates.filter(item => !item.decision && item.assessment !== 'ALREADY_CONFIRMED')
  const needsChanges = pending.some(item => item.assessment === 'NEEDS_CHANGES')
  const complete = (context.formal_permission_count ?? 0) > 0 && !pending.length && context.next_offset == null && source.pending === 0
  const businessKnown = source.roles > 0 && source.actions > 0 && source.pending === 0
  // 候选可读不等于已经打开正式提案；整理页始终留在权限整理，提案页负责推进批准阶段。
  const phase = complete ? 3 : !businessKnown ? 0 : 1
  const attention = phase === 0 && source.pending > 0 || phase === 1 && needsChanges
  const currentPhase = complete ? 3 : phase
  return <section className="rule-source-handoff" aria-label="业务信息与权限进度">
    <RulePreparationStages phase={currentPhase} complete={complete} attention={attention}/>
    <p className="rule-handoff-saved">沿用已保存的业务清单：{source.roles} 个角色 · {source.actions} 项动作{source.pending > 0 ? ` · ${source.pending} 项仍待核对` : ''}。{complete ? '新要求仍需重新审阅批准。' : '接下来确认谁可以对谁的资源做什么。'}</p>
  </section>
}
