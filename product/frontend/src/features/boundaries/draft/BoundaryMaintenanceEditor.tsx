// 业务边界维护编辑器：完整保留 stable identity，只提交 desired state，不让前端决定 write mode。
import { SearchField } from '../../../shared/ui/SearchField'

import { StatusBadge } from '../../../shared/ui/StatusBadge'
import { Alert, Button, Modal } from 'antd'
import { useMemo, useState } from 'react'
import type {
  BoundaryMaintenanceActionDto,
  BoundaryMaintenanceActorDto,
  BoundaryMaintenanceCommandDto,
  BoundaryMaintenanceDraftDto,
  BoundaryMaintenancePermissionDto,
} from '../../../api/boundaries/businessBoundaries'
import { PermissionRuleForm } from '../rules/PermissionRuleForm'
import { useTaskGuard } from '../../../shared/runtime/editGuard'
import { AgentWorkflowEntry } from '../../../shared/ui/AgentWorkflowEntry'

import type { BoundaryEditFocus } from '../definitions/CurrentBoundaryObjects'
import { BoundaryObjectsWorkspace, type DraftAction, type ObjectDrafts } from '../definitions/BoundaryObjectsWorkspace'

export function BoundaryMaintenanceEditor({ draft, initialCommand, busy, onSubmit, onCancel, focus }: {
  focus?: BoundaryEditFocus
  draft: BoundaryMaintenanceDraftDto
  initialCommand?: BoundaryMaintenanceCommandDto
  busy: boolean
  onSubmit: (command: BoundaryMaintenanceCommandDto) => void
  onCancel?: () => void
}) {
  const initial = useMemo(() => initialCommand ?? commandFromDraft(draft), [draft, initialCommand])
  const [actors, setActors] = useState<BoundaryMaintenanceActorDto[]>(initial.actors)
  const [actions, setActions] = useState<DraftAction[]>(initial.actions)
  const [permissions, setPermissions] = useState<BoundaryMaintenancePermissionDto[]>(initial.permissions)
  const [objectDrafts, setObjectDrafts] = useState<ObjectDrafts>({})
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const [ruleDirty, setRuleDirty] = useState(false)
  // 进入编辑产生的原样副本不算修改；退出时只对实际改变的内容确认丢弃。
  const dirty = JSON.stringify([actors, actions, permissions]) !== JSON.stringify([initial.actors, initial.actions, initial.permissions])
    || Object.entries(objectDrafts).some(([id, value]) => JSON.stringify(value) !== JSON.stringify([...actors, ...actions].find(item => item.item_id === id)))
  useTaskGuard(busy || ruleDirty || Object.keys(objectDrafts).length > 0 || JSON.stringify([actors, actions, permissions]) !== JSON.stringify([initial.actors, initial.actions, initial.permissions]))
  const [error, setError] = useState<string>()
  const [selectedActionId, setSelectedActionId] = useState<string>(initial.actions.find(item => item.action_id === focus?.actionId)?.item_id ?? initial.actions[0]?.item_id)
  const [mode, setMode] = useState<'rules' | 'actions' | 'actors'>(focus?.mode === 'actors' ? 'actors' : focus?.mode === 'objects' ? 'actions' : 'rules')
  const [query, setQuery] = useState('')
  const [editingRule, setEditingRule] = useState<BoundaryMaintenancePermissionDto | undefined>(() => {
    const existing = initial.permissions.find(item => item.intent_id === focus?.intentId)
    if (focus?.intentId && existing) return {...existing}
    const action = initial.actions.find(item => item.action_id === focus?.actionId) ?? initial.actions[0]
    const actor = initial.actors.find(item => item.effective_state === 'ACTIVE')
    return focus?.mode === 'new' && actor && action ? newPermission(actor.item_id, action.item_id, action.effects.map(effect => effect.item_id)) : undefined
  })
  const selectedAction = actions.find((item) => item.item_id === selectedActionId) ?? actions[0]

  const addPermission = () => {
    const actor = actors.find((item) => item.effective_state === 'ACTIVE')
    const action = selectedAction?.effective_state === 'ACTIVE' ? selectedAction : actions.find((item) => item.effective_state === 'ACTIVE')
    if (!actor || !action) {
      setError('先保留至少一个启用的业务主体和业务动作。')
      return
    }
    setEditingRule(newPermission(actor.item_id, action.item_id, action.effects.map(item => item.item_id)))
  }
  const submit = () => {
    const issue = validateDraft(actors, actions, permissions)
    if (issue) {
      setError(issue)
      return
    }
    setError(undefined)
    onSubmit({
      expected_boundary_state_fingerprint: initial.expected_boundary_state_fingerprint,
      actors: actors.map((item) => ({ ...item, display_name: item.display_name.trim(), description: item.description.trim() })),
      actions: actions.map(cleanAction),
      permissions,
      provenance: '本机界鉴用户在业务边界页面调整并提交',
    })
  }

  const matchesAction = (action: DraftAction) => {
    const text = query.trim().toLocaleLowerCase()
    return !text || [action.display_name, action.description, ...permissions.filter(rule => rule.business_action_item_id === action.item_id).flatMap(rule => [rule.expectation === 'ALLOW' ? '允许' : '禁止', ...actors.filter(actor => actor.item_id === rule.subject_actor_item_id || actor.item_id === rule.resource_owner_actor_item_id).map(actor => actor.display_name)])].join(' ').toLocaleLowerCase().includes(text)
  }
  const editedAction = actions.find(item => item.item_id === editingRule?.business_action_item_id)
  const changedCount = [...actors, ...actions, ...permissions].filter(item => {
    const original = [...draft.actors, ...draft.actions, ...draft.permissions].find(value => value.item_id === item.item_id)
    return JSON.stringify(item) !== JSON.stringify(original)
  }).length
  const editingDraft = Boolean(changedCount || editingRule || Object.keys(objectDrafts).length)
  const saveRule = (value: BoundaryMaintenancePermissionDto) => {
    setPermissions(items => items.some(item => item.item_id === value.item_id) ? items.map(item => item.item_id === value.item_id ? value : item) : [...items, value])
    setSelectedActionId(value.business_action_item_id); setEditingRule(undefined); setError(undefined)
  }
  const sentence = (rule: BoundaryMaintenancePermissionDto) => {
    const subject = actors.find(item => item.item_id === rule.subject_actor_item_id)?.display_name || '操作人'
    const owner = actors.find(item => item.item_id === rule.resource_owner_actor_item_id)?.display_name || '资源所有者'
    return `${subject}对${rule.relation === 'OWNS' ? '自己' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `另一个${owner}账号` : owner}拥有的资源，${rule.expectation === 'ALLOW' ? '可以' : '不得'}${selectedAction?.display_name || '执行这项动作'}。`
  }
  return <section className="boundary-draft" aria-label="权限规则草稿">
    <div className="boundary-draft-toolbar"><div><h1 id="boundary-maintenance-title">{editingRule ? '编辑权限规则' : '权限要求'}</h1>{changedCount > 0 && <StatusBadge kind="preparation">草稿 · {changedCount} 项修改</StatusBadge>}<p className="editorial-muted">{editingDraft ? '先将单项编辑保存到草稿，再统一核对并确认修改。' : '修改角色、动作或权限后统一确认；源码变化时，可单独核对代码关联。'}</p></div>
      {!editingRule && Object.keys(objectDrafts).length === 0 && <div className="boundary-draft-main-actions">{onCancel && <Button disabled={busy} onClick={() => dirty ? setConfirmDiscard(true) : onCancel()}>取消修改</Button>}<Button type={editingDraft ? 'primary' : 'default'} loading={busy} onClick={submit}>{editingDraft ? '核对修改' : '核对代码关联'}</Button></div>}
    </div>
    {!editingRule && <nav className="boundary-view-tabs" aria-label="权限要求视图">{([['rules','权限规则'],['actions','业务动作'],['actors','业务角色']] as const).map(([key,label])=><button key={key} type="button" aria-current={mode===key?'page':undefined} onClick={()=>setMode(key)}>{label}</button>)}</nav>}
    {editingRule && editedAction ? <PermissionRuleForm key={editingRule.item_id} initial={editingRule} actors={actors} action={editedAction} actions={actions.filter(item=>item.effective_state==='ACTIVE')} busy={busy} onSave={saveRule} onDirtyChange={setRuleDirty} onCancel={() => setEditingRule(undefined)}/> : mode !== 'rules' ? <BoundaryObjectsWorkspace kind={mode} createOnOpen={focus?.createObject} editOnOpen={focus?.editObject} initialId={mode === 'actors' ? actors.find(item => item.actor_id === focus?.actorId)?.item_id : selectedActionId} actors={actors} actions={actions} permissions={permissions} draft={draft} copies={objectDrafts} setCopies={setObjectDrafts} setActors={setActors} setActions={setActions} setPermissions={setPermissions} busy={busy}/> : <><div className="boundary-collection-toolbar"><SearchField aria-label="搜索草稿动作" placeholder="搜索动作、角色或规则" allowClear value={query} onChange={event => setQuery(event.target.value)}/><Button type="primary" disabled={busy} onClick={addPermission}>新增权限规则</Button></div><section className="boundary-document">
      <nav className="action-index" aria-label="编辑业务动作索引"><h3>业务动作</h3>{actions.filter(matchesAction).map(item => <button key={item.item_id} aria-current={item.item_id === selectedAction?.item_id ? 'true' : undefined} onClick={() => setSelectedActionId(item.item_id)}>{item.display_name || '尚未命名的动作'}<small>{permissions.filter(rule => rule.business_action_item_id === item.item_id && rule.effective_state === 'ACTIVE').length} 条启用规则</small></button>)}{!actions.some(matchesAction) && <p>没有匹配的动作</p>}</nav>
      <article className="boundary-action-document"><div className="boundary-action-heading"><div><h2>{selectedAction?.display_name || '尚无业务动作'}</h2><p className="editorial-muted">{selectedAction?.description}</p></div></div>
        {permissions.filter(item => item.business_action_item_id === selectedAction?.item_id).map(permission => <section className="permission-summary-row" key={permission.item_id}><StatusBadge kind="rule" className="permission-badge" tone={permission.effective_state === 'RETIRED' ? 'neutral' : permission.expectation === 'ALLOW' ? 'success' : 'danger'}>{permission.effective_state === 'RETIRED' ? '停用' : permission.expectation === 'ALLOW' ? '允许' : '禁止'}</StatusBadge><div><h3>{sentence(permission)}</h3><p>保护结果：{permission.protected_effect_item_ids.map(id => selectedAction?.effects.find(effect => effect.item_id === id)?.business_label || '已确认结果').join('、')}</p></div><Button type="link" disabled={busy} aria-label={`编辑规则：${sentence(permission)}`} onClick={() => setEditingRule({...permission})}>编辑</Button>{!permission.intent_id && <Button danger disabled={busy} onClick={() => setPermissions(items => items.filter(item => item.item_id !== permission.item_id))}>移除草稿规则</Button>}</section>)}
        {!permissions.some(item => item.business_action_item_id === selectedAction?.item_id) && <p className="boundary-empty-rules">这项动作还没有权限规则。点击“新增权限规则”开始填写。</p>}
        <section className="boundary-effect-overview"><h3>受保护的业务结果</h3>{selectedAction?.effects.map(effect => <p key={effect.item_id}>{effect.business_label} · {effect.resource_concept}</p>)}</section>
      </article>
    </section></>}
    {!editingRule && mode === 'rules' && !editingDraft && <AgentWorkflowEntry projectId={draft.project_id} stage="RULES"/>}
    {error && <Alert type="warning" showIcon message="草稿还不能生成提案" description={error}/>}
    {(changedCount > 0 || Object.keys(objectDrafts).length > 0) && <div className="boundary-draft-footer"><span>{changedCount ? `已有 ${changedCount} 项草稿修改` : '单项编辑尚未保存到草稿'}<small>修改仅保留在当前项目页面会话中，确认后才会生效。</small></span></div>}
    <Modal open={confirmDiscard} title="放弃当前草稿修改？" okText="放弃修改" cancelText="继续编辑" okButtonProps={{danger:true,disabled:busy}} onCancel={() => setConfirmDiscard(false)} onOk={() => { setConfirmDiscard(false); onCancel?.() }}><p>本页尚未确认的修改会被丢弃，已生效的权限保持原样。</p></Modal>
  </section>
}


function commandFromDraft(draft: BoundaryMaintenanceDraftDto): BoundaryMaintenanceCommandDto {
  return {
    expected_boundary_state_fingerprint: draft.boundary_state_fingerprint,
    actors: draft.actors,
    actions: draft.actions,
    permissions: draft.permissions,
    provenance: '本机界鉴用户打开当前业务边界维护草稿',
  }
}

let sequence = 0
function localId(prefix: 'pactr' | 'pactn' | 'peff' | 'pperm') {
  sequence += 1
  const value = (Date.now() + sequence).toString(16).padStart(16, '0').slice(-16)
  return `${prefix}_${value}`
}

function cleanAction(item: DraftAction): BoundaryMaintenanceActionDto { return { ...item, display_name: item.display_name.trim(), description: item.description.trim(), primary_resource_concept: item.primary_resource_concept.trim(), effects: item.effects.map((effect) => ({ ...effect, effect_kind: effect.effect_kind!, business_label: effect.business_label.trim(), resource_concept: effect.resource_concept.trim(), expected_state: effect.expected_state?.trim() || null, protected_projection: effect.effect_kind === 'DATA_DISCLOSURE' ? effect.protected_projection ?? [] : [], description: effect.description.trim() })) } }

function validateDraft(actors: BoundaryMaintenanceActorDto[], actions: DraftAction[], permissions: BoundaryMaintenancePermissionDto[]) {
  if (!actors.length || actors.some((item) => !item.display_name.trim() || !item.description.trim())) return '请完整保留并填写每个业务主体。'
  if (!actions.length || actions.some((item) => !item.display_name.trim() || !item.description.trim() || !item.primary_resource_concept.trim())) return '请完整保留并填写每个业务动作。'
  if (actions.some((item) => !item.effects.length || item.effects.some((effect) => !effect.business_label.trim() || !effect.effect_kind || !effect.resource_concept.trim() || !effect.description.trim()))) return '每个业务动作至少需要一个填写完整的业务结果。'
  if (actions.some((item) => item.effects.some((effect) => effect.effect_kind === 'DATA_DISCLOSURE' && !effect.protected_projection?.length))) return '受保护数据读取必须明确有限字段。'
  if (permissions.some((item) => item.effective_state === 'ACTIVE' && !item.protected_effect_item_ids.length)) return '每条启用的权限规则至少保护一个业务结果。'
  return undefined
}

function newPermission(actorId: string, actionId: string, effects: string[]): BoundaryMaintenancePermissionDto {
  return {item_id:localId('pperm'),intent_id:null,expected_current_revision:null,effective_state:'ACTIVE',subject_actor_item_id:actorId,resource_owner_actor_item_id:actorId,business_action_item_id:actionId,relation:'OWNS',expectation:'ALLOW',protected_effect_item_ids:effects}
}
