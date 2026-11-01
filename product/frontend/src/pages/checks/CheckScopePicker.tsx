import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import type { PermissionReference, PreparationView } from '../../entities/preparation/api/preparation';
import { Badge } from '../../shared/ui/feedback';
import { text } from '../../shared/lib/format';

export function CheckScopePicker({ materials, selected, disabled, onChange }: {
    materials: PreparationView;
    selected: PermissionReference[] | null;
    disabled: boolean;
    onChange: (value: PermissionReference[] | null) => void;
}) {
    const direct = new Set(selected?.map(item => item.intent_id));
    const automatic = new Set(materials.actions.flatMap(action => (action.assurance_contract?.allow_controls ?? [])
        .filter(item => direct.has(item.deny_permission.intent_id))
        .flatMap(item => item.resolved_allow_permission ? [item.resolved_allow_permission.intent_id] : [])));
    return <section className="jj-panel jj-check-scope-picker" aria-label="选择检查范围">
        <header><h2>检查范围</h2><div className="jj-toggle-group" aria-label="检查方式">
            <button disabled={disabled} aria-pressed={selected === null} onClick={() => onChange(null)}>全部规则</button>
            <button disabled={disabled} aria-pressed={selected !== null} onClick={() => {if (selected === null) onChange([]);}}>选定规则</button>
        </div></header>
        {selected !== null && <div className="jj-scope-rule-options">{materials.actions.flatMap(action => (action.permissions ?? [])
            .filter(rule => rule.effective_state === 'ACTIVE' && rule.intent_id && rule.revision && rule.intent_hash)
            .map(rule => {
                const reference = {intent_id: rule.intent_id!, revision: rule.revision!, intent_hash: rule.intent_hash!};
                const actor = (id: string) => text(action.identity_requirements.slots.find(slot => slot.requirement.actor_id === id)?.actor_display_name ?? '所选角色');
                const owner = rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${actor(rule.resource_owner_actor_id)}账号的资源` : `${actor(rule.resource_owner_actor_id)}的资源`;
                const added = automatic.has(reference.intent_id) && !direct.has(reference.intent_id);
                return <label key={reference.intent_id} className="jj-scope-rule-option" data-selected={direct.has(reference.intent_id) || added}>
                    <input type="checkbox" checked={direct.has(reference.intent_id) || added} disabled={disabled || added}
                        onChange={event => onChange(event.target.checked ? [...selected, reference].sort((a, b) => a.intent_id.localeCompare(b.intent_id)) : selected.filter(item => item.intent_id !== reference.intent_id))}/>
                    <span><strong>{rule.conditions?.principal === "ANONYMOUS" ? "未登录访客" : actor(rule.subject_actor_id)}{rule.expectation === 'ALLOW' ? '可以' : '不得'}{text(action.display_name)}</strong><span className="jj-small jj-muted">{owner}</span>{conditionLabels(rule.conditions).length > 0 && <span className="jj-small jj-muted">{conditionLabels(rule.conditions).join("，")}</span>}</span>
                    {added && <Badge>必要正常对照</Badge>}
                </label>;
            }))}</div>}
    </section>;
}
