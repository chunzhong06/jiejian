// 只读阶段说明使用已保存的业务、候选和批准事实；不模拟 Agent 执行，也不替代批准门禁。
import type { RuleCandidateContext } from '../../api/boundaries/ruleCandidates'
import { RulePreparationStages } from '../../shared/ui/RulePreparationStages'

export function RulePreparationProgress({ context }: { context: RuleCandidateContext }) {
  const source = context.source_summary
  if (!source) return null
  const pending = context.candidates.filter(item => !item.decision && item.assessment !== 'ALREADY_CONFIRMED')
  const needsChanges = pending.some(item => item.assessment === 'NEEDS_CHANGES')
  const complete = (context.formal_permission_count ?? 0) > 0 && !pending.length && context.next_offset == null && source.pending === 0
  const businessKnown = source.roles > 0 && source.actions > 0 && source.pending === 0
  const phase = complete ? 4 : !businessKnown ? 0 : needsChanges || !pending.length ? 1 : 2
  const attention = phase === 0 && source.pending > 0 || phase === 1 && needsChanges
  const currentPhase = complete ? 3 : phase
  return <section className="rule-source-handoff" aria-label="业务信息与权限进度">
    <RulePreparationStages phase={currentPhase} complete={complete} attention={attention}/>
    <p className="rule-facts-heading">已保存的业务信息</p>
    <dl className="rule-candidate-counts"><div><dt>已确认角色</dt><dd>{source.roles} 个</dd></div><div><dt>已确认动作</dt><dd>{source.actions} 项</dd></div><div><dt>仍待核对</dt><dd>{source.pending} 项</dd></div><div><dt>正式权限</dt><dd>{context.formal_permission_count == null ? '尚未读取' : `${context.formal_permission_count} 条`}</dd></div></dl>
    <p>{complete ? '已保存的权限可以作为检查依据；新约定仍需重新整理、审阅并批准。' : '已有角色与动作会继续用于整理。候选尚未生效，批准后才会更新正式权限。'}</p>
  </section>
}
