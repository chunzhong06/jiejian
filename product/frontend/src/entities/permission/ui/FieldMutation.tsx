import type {FieldMutationRequirement} from '../api/businessBoundaries'
import {Choice} from '../../../shared/ui/Choice'
import {Field} from '../../../shared/ui/layout'

const names={CHANGE:'字段值改变',ASSIGN:'字段被赋为指定值',ADD:'新增字段并赋值',REMOVE:'移除字段'} as const
export function fieldMutationLabel(value:FieldMutationRequirement){
  return value.path.join('.')+' · '+names[value.operation]+(['ASSIGN','ADD'].includes(value.operation)?' '+JSON.stringify(value.expected_value):'')
}
export function validFieldMutation(value:FieldMutationRequirement|null|undefined){
  return !value||(value.path.length>0&&value.path.length<=8&&value.path.every(part=>/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(part))&&
    (typeof value.expected_value!=='number'||Number.isFinite(value.expected_value)))
}
export function FieldMutationEditor({value,disabled,onChange}:{value:FieldMutationRequirement|null|undefined;disabled:boolean;onChange:(value:FieldMutationRequirement|null)=>void}){
  const update=(patch:Partial<FieldMutationRequirement>)=>onChange({...value!,...patch})
  const scalarType=value?.expected_value===null?'null':typeof value?.expected_value
  return <div className="jj-field-stack">
    <Field label="状态证明范围"><Choice disabled={disabled} value={value?'FIELD':'STATE'} onValueChange={kind=>onChange(kind==='FIELD'?{path:[],operation:'CHANGE',expected_value:null}:null)}><option value="STATE">业务状态</option><option value="FIELD">准确字段的写入</option></Choice></Field>
    {value&&<>
      <Field label="业务字段路径" hint="例如 owner_id 或 profile.role。读取范围须与这里一致。"><input disabled={disabled} value={value.path.join('.')} onChange={event=>update({path:event.target.value.split('.')})}/></Field>
      <Field label="要观察的写入"><Choice disabled={disabled} value={value.operation} onValueChange={operation=>update({operation:operation as FieldMutationRequirement['operation'],expected_value:null})}>{Object.entries(names).map(([key,label])=><option key={key} value={key}>{label}</option>)}</Choice></Field>
      {['ASSIGN','ADD'].includes(value.operation)&&<>
        <Field label="赋值类型"><Choice disabled={disabled} value={scalarType} onValueChange={kind=>update({expected_value:kind==='null'?null:kind==='boolean'?false:kind==='number'?0:''})}><option value="string">文本</option><option value="number">数值</option><option value="boolean">布尔值</option><option value="null">JSON null</option></Choice></Field>
        {scalarType==='boolean'?<Field label="指定值"><Choice disabled={disabled} value={String(value.expected_value)} onValueChange={text=>update({expected_value:text==='true'})}><option value="true">true</option><option value="false">false</option></Choice></Field>:scalarType!=='null'&&<Field label="指定值"><input disabled={disabled} maxLength={256} type={scalarType==='number'?'number':'text'} value={String(value.expected_value)} onChange={event=>update({expected_value:scalarType==='number'?Number(event.target.value):event.target.value})}/></Field>}
      </>}
    </>}
  </div>
}
