// 单条规则使用独立编辑副本；保存只交回本地草稿，取消不会修改其他规则或正式权限。
import { Alert, Button, Checkbox, Select, Segmented } from 'antd'
import { useId, useState } from 'react'
import type { BoundaryMaintenancePermissionDto } from '../../../api/boundaries/businessBoundaries'
import { relationLabels } from '../draft/boundaryLabels'
import { useTaskGuard } from '../../../shared/runtime/editGuard'

type NamedItem = { item_id: string; display_name: string }
export function PermissionRuleForm({ initial, actors, action: initialAction, actions, busy, onSave, onCancel }: {
  initial: BoundaryMaintenancePermissionDto
  actors: NamedItem[]
  action: NamedItem & { effects: { item_id: string; business_label: string }[] }
  actions?: Array<NamedItem & { effects: { item_id: string; business_label: string }[] }>
  busy: boolean
  onSave: (value: BoundaryMaintenancePermissionDto) => void
  onCancel: () => void
}) {
  const expectationId = useId()
  const [value, setValue] = useState(initial)
  const action = actions?.find(item=>item.item_id===value.business_action_item_id) ?? initialAction
  useTaskGuard(busy || JSON.stringify(value) !== JSON.stringify(initial))
  const [error, setError] = useState<string>()
  const patch = (change: Partial<BoundaryMaintenancePermissionDto>) => { setValue(current => ({ ...current, ...change })); setError(undefined) }
  const options = actors.map(item => ({ value:item.item_id, label:item.display_name || '尚未命名的主体' }))
  const subject = actors.find(item => item.item_id === value.subject_actor_item_id)?.display_name || '操作人'
  const owner = actors.find(item => item.item_id === value.resource_owner_actor_item_id)?.display_name || '资源所有者'
  const ownership = value.relation === 'OWNS' ? '自己' : value.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${owner}账号` : owner
  const save = () => {
    if (value.effective_state === 'ACTIVE' && !value.protected_effect_item_ids.length) { setError('至少选择一个这条规则保护的业务结果。'); return }
    onSave(value)
  }
  return <section className="permission-rule-form" aria-label="编辑单条权限规则">
    <p className="editorial-eyebrow">当前这条规则 · 草稿尚未生效</p>
    <h2>{subject}对{ownership}拥有的资源，{value.expectation === 'ALLOW' ? '可以' : '不得'}{action.display_name}。</h2>
    <div className="permission-form-fields">
      <label className="sentence-field"><span>操作人</span><Select aria-label="谁" disabled={busy} value={value.subject_actor_item_id} options={options} onChange={subject_actor_item_id => patch({subject_actor_item_id})}/></label>
      <label className="sentence-field"><span>资源所有者</span><Select aria-label="对谁拥有的资源" disabled={busy} value={value.resource_owner_actor_item_id} options={options} onChange={resource_owner_actor_item_id => patch({resource_owner_actor_item_id})}/></label>
      <label className="sentence-field"><span>资源关系</span><Select aria-label="资源关系" disabled={busy} value={value.relation} options={Object.entries(relationLabels).map(([value,label]) => ({value,label}))} onChange={relation => patch({relation})}/></label>
      <div className="sentence-field"><span id={expectationId}>权限要求</span><Segmented block aria-labelledby={expectationId} disabled={busy} value={value.expectation} options={[{value:'ALLOW',label:'允许'},{value:'DENY',label:'禁止'}]} onChange={expectation => patch({expectation:expectation as 'ALLOW' | 'DENY'})}/></div>
    </div>
    {!value.intent_id && actions ? <label className="sentence-field">业务动作<Select aria-label="业务动作" disabled={busy} value={value.business_action_item_id} options={actions.map(item=>({value:item.item_id,label:item.display_name}))} onChange={business_action_item_id=>patch({business_action_item_id,protected_effect_item_ids:actions.find(item=>item.item_id===business_action_item_id)?.effects.map(effect=>effect.item_id)??[]})}/></label> : <p className="editorial-muted">业务动作：{action.display_name}</p>}
    <div className="permission-effect-selection"><h3>这条规则保护的业务结果</h3><Checkbox.Group disabled={busy} aria-label="这条规则保护的业务结果" value={value.protected_effect_item_ids} options={action.effects.map(effect => ({value:effect.item_id,label:effect.business_label || '尚未命名的业务结果'}))} onChange={values => patch({protected_effect_item_ids:values.map(String)})}/><p className="editorial-muted">{value.expectation === 'DENY' ? '禁止时，不应产生选中的业务结果。' : '允许时，需要验证选中的正常业务结果。'}</p></div>
    {value.intent_id && <section className="permission-retirement"><h3>规则状态</h3><Checkbox disabled={busy} checked={value.effective_state === 'RETIRED'} onChange={event => patch({effective_state:event.target.checked ? 'RETIRED' : 'ACTIVE'})}>停用这条规则</Checkbox></section>}
    {error && <Alert className="flow-feedback" type="warning" showIcon message={error}/>}
    <div className="permission-form-actions"><Button disabled={busy} onClick={onCancel}>取消本次编辑</Button><Button type="primary" size="large" disabled={busy} onClick={save}>保存到草稿</Button></div>
    <p className="editorial-muted">保存草稿不会修改已生效规则。</p>
  </section>
}
