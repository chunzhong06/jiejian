import type {PermissionConditions, RelationshipRequirement} from '../api/businessBoundaries';
import {useEffect, useState} from 'react';
import {Choice} from '../../../shared/ui/Choice';
import {Field} from '../../../shared/ui/layout';
import {Button} from '../../../shared/ui/actions';

export const relationshipNames: Record<RelationshipRequirement['kind'], string> = {
    ORGANIZATION:'组织成员与层级', ROLE_INHERITANCE:'角色继承', SHARING:'资源共享', DELEGATION:'有限委托',
};
const relationStates = {ACTIVE:'关系有效', ABSENT:'不存在该关系', EXPIRED:'授权已到期', REVOKED:'授权已撤销'};

export function conditionLabels(value?: PermissionConditions | null) {
    if (!value) return [];
    return [value.principal === 'ANONYMOUS' ? '未登录访问' : '', value.tenant === 'SAME' ? '同一租户' : value.tenant === 'DIFFERENT' ? '跨租户' : '',
        value.resource_states.length ? `数据状态：${value.resource_states.join('、')}` : '',
        ...(value.relationships??[]).map(item=>`${relationshipNames[item.kind]}：${relationStates[item.state]}${item.inherited_role?'（'+item.inherited_role+'）':''}`)].filter(Boolean);
}

export function RuleConditionsEditor({value, relation, disabled, onChange}: {
    value?: PermissionConditions | null; relation: string; disabled: boolean;
    onChange: (value: PermissionConditions | null) => void;
}) {
    return <details className="jj-rule-conditions"><summary>适用条件{value && <span className="jj-small jj-muted">{conditionLabels(value).join('，')}</span>}</summary>
        <RuleConditionFields value={value} relation={relation} disabled={disabled} onChange={onChange}/>
    </details>;
}

// 新建表单和规则表的整行编辑区共用字段，展开方式由各自的工作面决定。
export function RuleConditionFields({value, relation, disabled, onChange}: {
    value?: PermissionConditions | null; relation: string; disabled: boolean;
    onChange: (value: PermissionConditions | null) => void;
}) {
    const current:PermissionConditions = value ?? {principal:'AUTHENTICATED', tenant:null, resource_states:[]};
    const savedStates = current.resource_states.join('、');
    const [states, setStates] = useState(savedStates);
    useEffect(() => setStates(savedStates), [savedStates]);
    const change = (changes: Partial<PermissionConditions>) => {
        const next = {...current, ...changes};
        onChange(next.principal === 'AUTHENTICATED' && next.tenant === null && !next.resource_states.length && !next.relationships?.length ? null : next);
    };
    return <>
        <div className="jj-condition-fields">
            <Field label="访问身份"><Choice value={current.principal} disabled={disabled} onValueChange={principal => change({principal:principal as PermissionConditions['principal'], ...(principal === 'ANONYMOUS' ? {tenant:null,relationships:[]} : {})})}>
                <option value="AUTHENTICATED">已登录账号</option><option value="ANONYMOUS" disabled={relation !== 'OTHER_ROLE'}>未登录访客</option>
            </Choice></Field>
            <Field label="与资源的租户关系"><Choice value={current.tenant ?? ''} disabled={disabled || current.principal === 'ANONYMOUS'} onValueChange={tenant => change({tenant:tenant ? tenant as PermissionConditions['tenant'] : null})}>
                <option value="">不限定</option><option value="SAME">同一租户</option><option value="DIFFERENT" disabled={relation === 'OWNS'}>不同租户</option>
            </Choice></Field>
            <Field label="仅检查这些数据状态（选填）"><input disabled={disabled} value={states} placeholder="例如 OPEN、ARCHIVED" onChange={event => setStates(event.target.value)} onBlur={() => change({resource_states:[...new Set(states.split(/[、,，]/).map(item => item.trim()).filter(Boolean))]})}/></Field>
        </div>
        {current.principal!=='ANONYMOUS'&&<RelationshipConditions value={current.relationships??[]} disabled={disabled} onChange={relationships=>change({relationships})}/>}
    </>;
}

function RelationshipConditions({value,disabled,onChange}:{value:RelationshipRequirement[];disabled:boolean;onChange:(value:RelationshipRequirement[])=>void}) {
    const available=(Object.keys(relationshipNames) as RelationshipRequirement['kind'][]).filter(kind=>!value.some(item=>item.kind===kind));
    const update=(index:number,change:Partial<RelationshipRequirement>)=>onChange(value.map((item,i)=>i===index?{...item,...change}:item));
    return <section className="jj-relationship-conditions" aria-label="关系条件">
        {value.map((item,index)=><div className="jj-relationship-condition" key={item.kind}>
            <header><strong>{relationshipNames[item.kind]}</strong><Button kind="quiet" disabled={disabled} onClick={()=>onChange(value.filter((_,i)=>i!==index))}>移除条件</Button></header>
            <div className="jj-form-grid">
                <Field label="适用状态"><Choice value={item.state} disabled={disabled} onValueChange={state=>update(index,{state:state as RelationshipRequirement['state']})}>
                    <option value="ACTIVE">关系有效</option><option value="ABSENT">不存在该关系</option>
                    {['SHARING','DELEGATION'].includes(item.kind)&&<><option value="EXPIRED">授权已到期</option><option value="REVOKED">授权已撤销</option></>}
                </Choice></Field>
                {item.kind==='ORGANIZATION'&&<Field label="组织范围"><Choice value={item.organization_scope} disabled={disabled} onValueChange={organization_scope=>update(index,{organization_scope:organization_scope as RelationshipRequirement['organization_scope']})}>
                    <option value="SAME">属于资源所在组织</option><option value="SUBJECT_ANCESTOR">操作人组织是资源组织的上级</option><option value="RESOURCE_ANCESTOR">资源组织是操作人组织的上级</option>
                </Choice></Field>}
                {item.kind==='ROLE_INHERITANCE'&&<Field label="需要继承的业务角色"><input value={item.inherited_role??''} disabled={disabled} onChange={event=>update(index,{inherited_role:event.target.value})}/></Field>}
                {(['ROLE_INHERITANCE'].includes(item.kind)||item.kind==='ORGANIZATION'&&item.organization_scope!=='SAME')&&<Field label="最多经过的层级"><input type="number" min={1} max={8} value={item.max_depth} disabled={disabled} onChange={event=>update(index,{max_depth:Number(event.target.value)})}/></Field>}
            </div>
        </div>)}
        {available.length>0&&<Field label="补充关系条件"><Choice value="" disabled={disabled} placeholder="选择需要核对的关系" onValueChange={kind=>onChange([...value,{kind:kind as RelationshipRequirement['kind'],state:'ACTIVE',organization_scope:'SAME',inherited_role:kind==='ROLE_INHERITANCE'?'':null,max_depth:1}])}>
            <option value="" disabled>选择需要核对的关系</option>
            {available.map(kind=><option key={kind} value={kind}>{relationshipNames[kind]}</option>)}
        </Choice></Field>}
    </section>;
}
