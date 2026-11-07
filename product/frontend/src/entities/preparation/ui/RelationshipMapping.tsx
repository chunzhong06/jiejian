import type {RelationshipRequirement} from '../../permission/api/businessBoundaries';
import type {RelationshipSourceMapping} from '../api/proofSources';
import {Field} from '../../../shared/ui/layout';
import {Choice} from '../../../shared/ui/Choice';

export const emptyRelationshipMapping:RelationshipSourceMapping={application_action:'',scope_complete_path:null,source_time_path:null,subject_organizations_path:null,
    resource_organization_path:null,organization_parents_path:null,subject_roles_path:null,role_inheritance_path:null,grants_path:null,clock_uncertainty_us:0};

export function relationshipMappingFields(requirements:RelationshipRequirement[]) {
    const kinds=new Set(requirements.map(item=>item.kind));
    return [
        {key:'scope_complete_path',label:'关系集合完整标记（布尔值）',resource:true},
        ...(kinds.has('SHARING')||kinds.has('DELEGATION')?[{key:'source_time_path',label:'应用时钟（微秒）',resource:true}]:[]),
        ...(kinds.has('ORGANIZATION')?[
            {key:'subject_organizations_path',label:'身份接口中的组织列表',resource:false},
            {key:'resource_organization_path',label:'资源所属组织',resource:true},
            ...(requirements.some(item=>item.kind==='ORGANIZATION'&&item.organization_scope!=='SAME')?[{key:'organization_parents_path',label:'组织层级记录',resource:true}]:[])]:[]),
        ...(kinds.has('ROLE_INHERITANCE')?[
            {key:'subject_roles_path',label:'身份接口中的角色列表',resource:false},
            {key:'role_inheritance_path',label:'角色继承记录',resource:true}]:[]),
        ...(kinds.has('SHARING')||kinds.has('DELEGATION')?[{key:'grants_path',label:'共享与委托记录',resource:true}]:[]),
        ...(kinds.has('SHARING')?[{key:'subject_groups_path',label:'身份接口中的组成员列表（组共享时填写）',resource:false,optional:true}]:[]),
    ] as Array<{key:Exclude<keyof RelationshipSourceMapping,'application_action'|'clock_uncertainty_us'>;label:string;resource:boolean;optional?:boolean}>;
}

export function relationshipMappingReady(requirements:RelationshipRequirement[],value:RelationshipSourceMapping,fields:string[]) {
    return !requirements.length||(Boolean(value.application_action.trim())&&relationshipMappingFields(requirements).every(item=>{
        const path=value[item.key];return Boolean(item.optional&&!path?.length||path?.length&&path.every(Boolean)&&(!item.resource||fields.includes(path[0])));
    }));
}

export function RelationshipMapping({requirements,value,fields,onChange}:{requirements:RelationshipRequirement[];value:RelationshipSourceMapping;fields:string[];onChange:(value:RelationshipSourceMapping)=>void}) {
    return <section className="jj-condition-source"><h3>关系事实从哪里取得</h3>
        <div className="jj-form-grid">
            <Field label="应用中的业务动作标识"><input value={value.application_action} placeholder="与授权记录中的动作保持一致" onChange={event=>onChange({...value,application_action:event.target.value})}/></Field>
            {requirements.some(item=>item.kind==='SHARING'||item.kind==='DELEGATION')&&<Field label="应用时钟误差上限（毫秒）" hint="到期或撤销边界位于误差内时，保留未知。"><input type="number" min={0} max={5000} value={value.clock_uncertainty_us/1000} onChange={event=>onChange({...value,clock_uncertainty_us:Number(event.target.value)*1000})}/></Field>}
            {relationshipMappingFields(requirements).map(item=><Field key={item.key} label={item.label}>
                {item.resource?<Choice value={value[item.key]?.[0]??''} placeholder="选择已声明的记录字段" onValueChange={column=>onChange({...value,[item.key]:column?[column]:null})}>
                    {fields.map(field=><option key={field} value={field}>{field}</option>)}
                </Choice>:<input value={value[item.key]?.join('.')??''} placeholder="例如 organizations" onChange={event=>onChange({...value,[item.key]:event.target.value?event.target.value.split('.'):null})}/>}
            </Field>)}
        </div>
        <p className="jj-small jj-muted">只读取这些已声明字段。组织与角色列表、层级边、授权有效期由实际来源核对，缺少记录时保留待确认。</p>
    </section>;
}
