import type {PermissionConditions} from '../api/businessBoundaries';
import {useEffect, useState} from 'react';
import {Choice} from '../../../shared/ui/Choice';
import {Field} from '../../../shared/ui/layout';

export function conditionLabels(value?: PermissionConditions | null) {
    if (!value) return [];
    return [value.principal === 'ANONYMOUS' ? '未登录访问' : '', value.tenant === 'SAME' ? '同一租户' : value.tenant === 'DIFFERENT' ? '跨租户' : '',
        value.resource_states.length ? `数据状态：${value.resource_states.join('、')}` : ''].filter(Boolean);
}

export function RuleConditionsEditor({value, relation, disabled, onChange}: {
    value?: PermissionConditions | null; relation: string; disabled: boolean;
    onChange: (value: PermissionConditions | null) => void;
}) {
    const current = value ?? {principal:'AUTHENTICATED' as const, tenant:null, resource_states:[]};
    const savedStates = current.resource_states.join('、');
    const [states, setStates] = useState(savedStates);
    useEffect(() => setStates(savedStates), [savedStates]);
    const change = (changes: Partial<PermissionConditions>) => {
        const next = {...current, ...changes};
        onChange(next.principal === 'AUTHENTICATED' && next.tenant === null && !next.resource_states.length ? null : next);
    };
    return <details className="jj-rule-conditions"><summary>适用条件{value && <span className="jj-small jj-muted">{conditionLabels(value).join('，')}</span>}</summary>
        <div className="jj-condition-fields">
            <Field label="访问身份"><Choice value={current.principal} disabled={disabled} onValueChange={principal => change({principal:principal as PermissionConditions['principal'], ...(principal === 'ANONYMOUS' ? {tenant:null} : {})})}>
                <option value="AUTHENTICATED">已登录账号</option><option value="ANONYMOUS" disabled={relation !== 'OTHER_ROLE'}>未登录访客</option>
            </Choice></Field>
            <Field label="与资源的租户关系"><Choice value={current.tenant ?? ''} disabled={disabled || current.principal === 'ANONYMOUS'} onValueChange={tenant => change({tenant:tenant ? tenant as PermissionConditions['tenant'] : null})}>
                <option value="">不限定</option><option value="SAME">同一租户</option><option value="DIFFERENT" disabled={relation === 'OWNS'}>不同租户</option>
            </Choice></Field>
            <Field label="仅检查这些数据状态（选填）"><input disabled={disabled} value={states} placeholder="例如 OPEN、ARCHIVED" onChange={event => setStates(event.target.value)} onBlur={() => change({resource_states:[...new Set(states.split(/[、,，]/).map(item => item.trim()).filter(Boolean))]})}/></Field>
        </div>
    </details>;
}
