// 复用原有权限行的文案、状态与精确编辑引用；筛选由页面控制。
import { Button } from 'antd'
import type { BusinessBoundaryViewDto } from '../../api/boundaries/businessBoundaries'
import { StatusBadge } from '../../shared/ui/StatusBadge'

type Rule = BusinessBoundaryViewDto['permission_intents'][number]
type Action = BusinessBoundaryViewDto['actions'][number]

export function PermissionRuleRows({ boundary, action, rules, onRule, onEdit }: {
  boundary: BusinessBoundaryViewDto; action: Action; rules: Rule[]
  onRule?: (id: string, revision: number) => void
  onEdit?: (id?: string) => void
}) {
  const actors = new Map(boundary.actors.map(actor => [actor.actor_id, actor.display_name]))
  return <>
    {rules.length ? rules.map((rule, index) => <section className="permission-summary-row" key={rule.intent_id ?? index}>
      <StatusBadge kind="rule" className="permission-badge" tone={rule.expectation === 'ALLOW' ? 'success' : 'danger'}>{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</StatusBadge>
      <div><h3>{actors.get(rule.subject_actor_id) ?? '业务主体'}对{rule.relation === 'OWNS' ? '自己' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${actors.get(rule.resource_owner_actor_id) ?? '同权限组'}账号` : actors.get(rule.resource_owner_actor_id) ?? '资源主体'}拥有的资源，{rule.expectation === 'ALLOW' ? '可以' : '不得'}{action.display_name}。</h3>
        <p>保护结果：{rule.protected_effect_ids.map(id => action.effect_catalog.find(effect => effect.effect_id === id)?.business_label ?? '已确认的业务结果').join('、')}</p></div>
      <div className="light-permission-actions">
        {onRule && <Button type="link" disabled={!rule.intent_id || !rule.revision} onClick={() => onRule(rule.intent_id!, rule.revision!)}>详情</Button>}
        {onEdit && <Button type="link" aria-label={`编辑${rule.expectation === 'ALLOW' ? '允许' : '禁止'}规则 ${index + 1}`} onClick={() => onEdit(rule.intent_id ?? undefined)}>编辑或停用</Button>}
      </div>
    </section>) : <p className="editorial-muted">这项动作尚无当前权限规则。</p>}
  </>
}
