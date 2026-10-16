// 候选工作面保持权限整理阶段；源码识别统计只作提示，不冒充已保存业务或倒推页面进度。
import type { RuleCandidateContext } from '../../api/boundaries/ruleCandidates'
import { RulePreparationStages } from '../../shared/ui/RulePreparationStages'

export function RulePreparationProgress({ context }: { context: RuleCandidateContext }) {
  const source = context.source_summary
  if((context.formal_permission_count??0)>0)return <p className="rule-handoff-saved">沿用当前 {context.formal_permission_count} 条正式规则。本次只核对新增或调整，批准前现有规则保持生效。</p>
  const pending = context.candidates.filter(item => !item.decision && item.assessment !== 'ALREADY_CONFIRMED')
  const needsChanges = pending.some(item => item.assessment === 'NEEDS_CHANGES')
  // 官方草稿和手工业务不以源码候选全部确认作为前提。缺口仍显示，提案门禁仍由服务端核对。
  const attention = needsChanges || (source?.pending ?? 0) > 0
  return <section className="rule-source-handoff" aria-label="业务信息与权限进度">
    <RulePreparationStages phase={1} attention={attention}/>
    <p className="rule-handoff-saved">{source
      ? source.roles > 0 || source.actions > 0
        ? `源码识别项中已确认 ${source.roles} 个角色、${source.actions} 项动作。${source.pending > 0 ? `另有 ${source.pending} 项待核对。` : ''}`
        : source.pending > 0 ? `源码识别中有 ${source.pending} 项候选待核对。` : '角色与动作请在本轮权限候选中核对。'
      : '角色与动作请在本轮权限候选中核对。'} 本轮权限仍需审阅并批准后生效。</p>
  </section>
}
