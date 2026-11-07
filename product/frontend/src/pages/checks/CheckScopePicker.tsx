import {Segmented} from '../../shared/ui/Segmented'
import {conditionLabels} from '../../entities/permission/ui/RuleConditions';
import type {PermissionReference, PreparationView} from '../../entities/preparation/api/preparation';
import {text} from '../../shared/lib/format';
import {SavedChecks} from './SavedChecks';

export function CheckScopePicker({materials, selected, disabled, onChange}: {
    materials: PreparationView;
    selected: PermissionReference[] | null;
    disabled: boolean;
    onChange: (value: PermissionReference[] | null) => void;
}) {
    const direct = new Set(selected?.map(item => item.intent_id));
    const automatic = new Set(materials.actions.flatMap(action => (action.assurance_contract?.allow_controls ?? [])
        .filter(item => direct.has(item.deny_permission.intent_id))
        .flatMap(item => item.resolved_allow_permission ? [item.resolved_allow_permission.intent_id] : [])));
    const rules = materials.actions.flatMap(action => (action.permissions ?? [])
        .filter(rule => rule.effective_state === 'ACTIVE' && rule.intent_id && rule.revision && rule.intent_hash)
        .map(rule => ({action, rule})));
    const controls = rules.filter(({rule}) => automatic.has(rule.intent_id!) && !direct.has(rule.intent_id!));
    const option = ({action, rule}: typeof rules[number], added = false) => {
        const reference = {intent_id: rule.intent_id!, revision: rule.revision!, intent_hash: rule.intent_hash!};
        const actor = (id: string) => text(action.identity_requirements.slots.find(slot => slot.requirement.actor_id === id)?.actor_display_name ?? '所选角色');
        const owner = rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${actor(rule.resource_owner_actor_id)}账号的资源` : `${actor(rule.resource_owner_actor_id)}的资源`;
        return <label key={reference.intent_id} className="jj-scope-rule-option" data-selected={direct.has(reference.intent_id) || added}>
            <input type="checkbox" checked={direct.has(reference.intent_id) || added} disabled={disabled || added}
                onChange={event => onChange(event.target.checked ? [...(selected ?? []), reference].sort((a, b) => a.intent_id.localeCompare(b.intent_id)) : selected!.filter(item => item.intent_id !== reference.intent_id))}/>
            <span><strong>{rule.conditions?.principal === 'ANONYMOUS' ? '未登录访客' : actor(rule.subject_actor_id)}{rule.expectation === 'ALLOW' ? '可以' : '不得'}{text(action.display_name)}</strong><span className="jj-small jj-muted">{owner}</span>{conditionLabels(rule.conditions).length > 0 && <span className="jj-small jj-muted">{conditionLabels(rule.conditions).join('，')}</span>}</span>
        </label>;
    };
    return <section className="jj-panel jj-check-scope-picker" aria-label="选择检查范围">
        <header><h2 className="jj-title-group">要检查的规则</h2><Segmented label="检查方式" value={selected===null?'all':'selected'} disabled={disabled} items={[{value:'all',label:'全部规则'},{value:'selected',label:'选定规则'}]} onValueChange={value=>{if(value==='all')onChange(null);else if(selected===null)onChange([])}}/></header>
        {selected === null ? <p className="jj-scope-all-summary">检查全部 {rules.length} 条已批准规则。</p> : <div className="jj-scope-rule-options">{rules.filter(({rule}) => !controls.some(item => item.rule.intent_id === rule.intent_id)).map(item => option(item))}</div>}
        {selected !== null && controls.length > 0 && <section className="jj-scope-controls"><h3 className="jj-title-caption">必要正常对照</h3><p>同时确认原来允许的操作仍能完成。</p>{controls.map(item => option(item, true))}</section>}
        <details className="jj-scope-saved"><summary>保存与沿用检查范围</summary><SavedChecks key={materials.project_id} projectId={materials.project_id} selected={selected} disabled={disabled} onChange={onChange} name={materials.actions.filter(action=>action.permissions?.some(rule=>rule.intent_id&&direct.has(rule.intent_id))).map(action=>text(action.display_name)).join('、').slice(0,72)}/></details>
    </section>;
}
