// 业务边界维护编辑器：完整保留 stable identity，只提交 desired state，不让前端决定 write mode。

import { Alert, Button, Checkbox, Divider, Input, Select, Space, Typography } from 'antd'
import { useMemo, useState } from 'react'
import type {
  BoundaryMaintenanceActionDto,
  BoundaryMaintenanceActorDto,
  BoundaryMaintenanceCommandDto,
  BoundaryMaintenanceDraftDto,
  BoundaryMaintenancePermissionDto,
  BusinessEffectKind,
  ProposedEffectDto,
} from '../../api/businessBoundaries'
import { confidenceLabels, effectKindLabels, expectationLabels, relationLabels } from './boundaryLabels'
import { AssistantPanel } from '../../components/AssistantPanel'
import { PermissionDraftAssist } from './PermissionDraftAssist'
import type { PermissionDraftSuggestion } from '../../api/permissionDrafts'

type DraftEffect = Omit<ProposedEffectDto, 'effect_kind'> & { effect_kind?: BusinessEffectKind }
type DraftAction = Omit<BoundaryMaintenanceActionDto, 'effects'> & { effects: DraftEffect[] }

export function BoundaryMaintenanceEditor({ draft, initialCommand, busy, onSubmit }: {
  draft: BoundaryMaintenanceDraftDto
  initialCommand?: BoundaryMaintenanceCommandDto
  busy: boolean
  onSubmit: (command: BoundaryMaintenanceCommandDto) => void
}) {
  const initial = useMemo(() => initialCommand ?? commandFromDraft(draft), [draft, initialCommand])
  const [actors, setActors] = useState<BoundaryMaintenanceActorDto[]>(initial.actors)
  const [actions, setActions] = useState<DraftAction[]>(initial.actions)
  const [permissions, setPermissions] = useState<BoundaryMaintenancePermissionDto[]>(initial.permissions)
  const [error, setError] = useState<string>()

  const applySuggestions = (suggestions: PermissionDraftSuggestion[]) => {
    let next = permissions
    for (const suggestion of suggestions) {
      const subject = actors.find((item) => item.actor_id === suggestion.subject_actor_id && item.expected_current_revision === suggestion.subject_actor_revision)
      const owner = actors.find((item) => item.actor_id === suggestion.resource_owner_actor_id && item.expected_current_revision === suggestion.resource_owner_actor_revision)
      const action = actions.find((item) => item.action_id === suggestion.business_action_id && item.expected_current_revision === suggestion.action_revision)
      // AI 只理解正式业务；本地已修改的主体/动作不能借旧 revision 接收建议。
      if (!subject || !owner || !action || [subject, owner].some((item) => item.effective_state !== 'ACTIVE'
        || JSON.stringify(item) !== JSON.stringify(draft.actors.find((value) => value.item_id === item.item_id)))
        || action.effective_state !== 'ACTIVE' || JSON.stringify(action) !== JSON.stringify(draft.actions.find((value) => value.item_id === action.item_id))) {
        setError('建议引用的主体或动作已在草稿中修改，请手工核对这些规则。'); return
      }
      const effects = action.effects.filter((item) => item.effect_id && suggestion.protected_effect_ids.includes(item.effect_id)).map((item) => item.item_id)
      if (!effects.length || effects.length !== suggestion.protected_effect_ids.length) { setError('建议的业务结果已变化，请手工核对。'); return }
      const matches = (item: BoundaryMaintenancePermissionDto) => item.effective_state === 'ACTIVE' && item.subject_actor_item_id === subject.item_id
        && item.resource_owner_actor_item_id === owner.item_id && item.business_action_item_id === action.item_id && item.relation === suggestion.relation
      const exact = next.find((item) => matches(item) && item.protected_effect_item_ids.length === effects.length && effects.every((id) => item.protected_effect_item_ids.includes(id)))
      if (exact) next = next.map((item) => item === exact ? { ...item, expectation: suggestion.suggested_expectation } : item)
      else {
        // 部分业务结果被新建议覆盖时保留原规则的其他结果，不覆盖无关手工输入。
        next = next.flatMap((item) => {
          if (!matches(item)) return [item]
          const remaining = item.protected_effect_item_ids.filter((id) => !effects.includes(id))
          if (remaining.length === item.protected_effect_item_ids.length) return [item]
          return remaining.length ? [{ ...item, protected_effect_item_ids: remaining }] : item.intent_id ? [{ ...item, effective_state: 'RETIRED' as const }] : []
        })
        next = [...next, { item_id: localId('pperm'), intent_id: null, expected_current_revision: null, effective_state: 'ACTIVE',
          subject_actor_item_id: subject.item_id, business_action_item_id: action.item_id, resource_owner_actor_item_id: owner.item_id,
          relation: suggestion.relation, expectation: suggestion.suggested_expectation, protected_effect_item_ids: effects }]
      }
    }
    setPermissions(next); setError(undefined)
  }

  const addPermission = () => {
    const actor = actors.find((item) => item.effective_state === 'ACTIVE')
    const action = actions.find((item) => item.effective_state === 'ACTIVE')
    if (!actor || !action) {
      setError('先保留至少一个启用的业务主体和业务动作。')
      return
    }
    setPermissions((items) => [...items, {
      item_id: localId('pperm'), intent_id: null, expected_current_revision: null,
      effective_state: 'ACTIVE', subject_actor_item_id: actor.item_id,
      business_action_item_id: action.item_id, resource_owner_actor_item_id: actor.item_id,
      relation: 'OWNS', expectation: 'ALLOW',
      protected_effect_item_ids: action.effects.map((item) => item.item_id),
    }])
  }
  const removeEffect = (actionId: string, effectId: string) => {
    updateAction(setActions, actionId, {
      effects: actions.find((item) => item.item_id === actionId)?.effects.filter((item) => item.item_id !== effectId) ?? [],
    })
    setPermissions((items) => items.map((item) => ({
      ...item,
      protected_effect_item_ids: item.protected_effect_item_ids.filter((value) => value !== effectId),
    })))
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

  return <section className="boundary-editor" aria-labelledby="boundary-maintenance-title">
    <div className="boundary-section-heading"><div>
      <Typography.Title level={3} id="boundary-maintenance-title">调整当前业务边界</Typography.Title>
      <Typography.Paragraph type="secondary">当前主体、动作和权限会完整保留。修改只会先形成一份不可变提案，批准后才追加正式业务版本 或更新实现映射。</Typography.Paragraph>
    </div></div>

    <Divider orientation="left">谁在使用应用</Divider>
    <div className="boundary-editor-list">{actors.map((actor) => <article key={actor.item_id} className="boundary-editor-card">
      <div className="boundary-editor-row">
        <Input aria-label="业务主体名称" value={actor.display_name} onChange={(event) => setActors((items) => items.map((item) => item.item_id === actor.item_id ? { ...item, display_name: event.target.value } : item))} />
        <Checkbox checked={actor.effective_state === 'RETIRED'} onChange={(event) => setActors((items) => items.map((item) => item.item_id === actor.item_id ? { ...item, effective_state: event.target.checked ? 'RETIRED' : 'ACTIVE' } : item))}>停用</Checkbox>
      </div>
      <Input.TextArea aria-label={`${actor.display_name || '业务主体'}说明`} value={actor.description} autoSize onChange={(event) => setActors((items) => items.map((item) => item.item_id === actor.item_id ? { ...item, description: event.target.value } : item))} />
      <ImplementationSelector kind="ROLE" item={actor} draft={draft} onChange={(source_candidate_ids) => setActors((items) => items.map((item) => item.item_id === actor.item_id ? { ...item, source_candidate_ids } : item))} />
      {!actor.actor_id && <Button danger type="text" onClick={() => {
        setActors((items) => items.filter((item) => item.item_id !== actor.item_id))
        setPermissions((items) => items.filter((item) => item.subject_actor_item_id !== actor.item_id && item.resource_owner_actor_item_id !== actor.item_id))
      }}>移除新主体</Button>}
    </article>)}</div>
    <Button onClick={() => setActors((items) => [...items, manualActor()])}>新增业务主体</Button>

    <Divider orientation="left">做什么，会产生什么业务结果</Divider>
    <div className="boundary-editor-list">{actions.map((action) => <article key={action.item_id} className="boundary-editor-card boundary-action-editor">
      <div className="boundary-editor-row">
        <Input aria-label="业务动作名称" value={action.display_name} onChange={(event) => updateAction(setActions, action.item_id, { display_name: event.target.value })} />
        <Select aria-label={`${action.display_name || '业务动作'}类型`} value={action.operation_kind} options={operationOptions} onChange={(value) => updateAction(setActions, action.item_id, { operation_kind: value })} />
        <Checkbox checked={action.effective_state === 'RETIRED'} onChange={(event) => updateAction(setActions, action.item_id, { effective_state: event.target.checked ? 'RETIRED' : 'ACTIVE' })}>停用</Checkbox>
      </div>
      <Input.TextArea aria-label={`${action.display_name || '业务动作'}说明`} value={action.description} autoSize onChange={(event) => updateAction(setActions, action.item_id, { description: event.target.value })} />
      <Input aria-label={`${action.display_name || '业务动作'}资源概念`} value={action.primary_resource_concept} onChange={(event) => updateAction(setActions, action.item_id, { primary_resource_concept: event.target.value })} />
      <ImplementationSelector kind="ACTION" item={action} draft={draft} onChange={(source_candidate_ids) => updateAction(setActions, action.item_id, { source_candidate_ids })} />
      <Typography.Text strong>业务结果</Typography.Text>
      {action.effects.map((effect) => <div className="boundary-effect-editor" key={effect.item_id}>
        <Input aria-label="业务结果名称" value={effect.business_label} onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { business_label: event.target.value })} />
        <Select aria-label={`${effect.business_label || '业务结果'}类型`} value={effect.effect_kind} options={effectOptions} onChange={(value) => updateEffect(setActions, action.item_id, effect.item_id, { effect_kind: value })} />
        <Input aria-label={`${effect.business_label || '业务结果'}资源概念`} value={effect.resource_concept} onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { resource_concept: event.target.value })} />
        {effect.effect_kind === 'DATA_DISCLOSURE' && <Input aria-label={`${effect.business_label || '业务结果'}有限字段`} value={(effect.protected_projection ?? []).join(', ')} onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { protected_projection: splitProjection(event.target.value) })} />}
        <Input.TextArea aria-label={`${effect.business_label || '业务结果'}说明`} value={effect.description} autoSize onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { description: event.target.value })} />
        <Button danger type="text" onClick={() => removeEffect(action.item_id, effect.item_id)}>移除业务结果</Button>
      </div>)}
      <Space><Button onClick={() => updateAction(setActions, action.item_id, { effects: [...action.effects, emptyEffect()] })}>添加业务结果</Button>{!action.action_id && <Button danger type="text" onClick={() => {
        setActions((items) => items.filter((item) => item.item_id !== action.item_id))
        setPermissions((items) => items.filter((item) => item.business_action_item_id !== action.item_id))
      }}>移除新动作</Button>}</Space>
    </article>)}</div>
    <Button onClick={() => setActions((items) => [...items, manualAction()])}>新增业务动作</Button>

    <Divider orientation="left">谁可以做什么</Divider>
    <PermissionDraftAssist projectId={draft.project_id} boundaryFingerprint={draft.boundary_state_fingerprint}
      draftKey={JSON.stringify([actors, actions, permissions])} disabled={busy} onApply={applySuggestions} />
    <div className="boundary-editor-list">{permissions.map((permission) => {
      const action = actions.find((item) => item.item_id === permission.business_action_item_id)
      return <article key={permission.item_id} className="boundary-editor-card boundary-permission-editor">
        <Select aria-label="谁" value={permission.subject_actor_item_id} options={actors.map(actorOption)} onChange={(value) => updatePermission(setPermissions, permission.item_id, { subject_actor_item_id: value })} />
        <Select aria-label="做什么" value={permission.business_action_item_id} options={actions.map(actionOption)} onChange={(value) => {
          const next = actions.find((item) => item.item_id === value)
          updatePermission(setPermissions, permission.item_id, { business_action_item_id: value, protected_effect_item_ids: next?.effects.map((item) => item.item_id) ?? [] })
        }} />
        <Select aria-label="对谁拥有的资源" value={permission.resource_owner_actor_item_id} options={actors.map(actorOption)} onChange={(value) => updatePermission(setPermissions, permission.item_id, { resource_owner_actor_item_id: value })} />
        <Select aria-label="资源关系" value={permission.relation} options={Object.entries(relationLabels).map(([value, label]) => ({ value, label }))} onChange={(value) => updatePermission(setPermissions, permission.item_id, { relation: value })} />
        <Select aria-label="允许或拒绝" value={permission.expectation} options={Object.entries(expectationLabels).map(([value, label]) => ({ value, label }))} onChange={(value) => updatePermission(setPermissions, permission.item_id, { expectation: value })} />
        <Checkbox.Group aria-label="这条规则保护的业务结果" value={permission.protected_effect_item_ids} options={(action?.effects ?? []).map((effect) => ({ value: effect.item_id, label: effect.business_label || '尚未命名的业务结果' }))} onChange={(values) => updatePermission(setPermissions, permission.item_id, { protected_effect_item_ids: values.map(String) })} />
        <Checkbox checked={permission.effective_state === 'RETIRED'} onChange={(event) => updatePermission(setPermissions, permission.item_id, { effective_state: event.target.checked ? 'RETIRED' : 'ACTIVE' })}>停用这条规则</Checkbox>
        {!permission.intent_id && <Button danger type="text" onClick={() => setPermissions((items) => items.filter((item) => item.item_id !== permission.item_id))}>移除新规则</Button>}
      </article>
    })}</div>
    <Button onClick={addPermission}>新增权限规则</Button>
    {error && <Alert type="warning" showIcon message="草稿还不能生成提案" description={error} />}
    <div className="boundary-editor-submit"><Button type="primary" loading={busy} onClick={submit}>生成待审调整提案</Button></div>
  </section>
}

function ImplementationSelector({ kind, item, draft, onChange }: {
  kind: 'ROLE' | 'ACTION'
  item: { actor_id?: string | null; action_id?: string | null; source_candidate_ids?: string[] }
  draft: BoundaryMaintenanceDraftDto
  onChange: (values: string[]) => void
}) {
  const identity = kind === 'ROLE' ? item.actor_id : item.action_id
  const inspection = draft.implementation_inspections.find((value) => kind === 'ROLE'
    ? 'actor_id' in value && value.actor_id === identity
    : 'action_id' in value && value.action_id === identity)
  const candidates = draft.candidate_options.filter((value) => value.candidate_kind === kind)
  const selected = item.source_candidate_ids ?? []
  const missingEvidence = candidates.some((candidate) => selected.includes(candidate.candidate_id) && !candidate.evidence_available)
  return <details className="boundary-candidate-basis" open={Boolean(inspection?.binding_exists && inspection.status !== 'CURRENT')}>
    <summary>当前代码实现{inspection ? ` · ${implementationLabel(inspection.status)}` : ''}</summary>
    <Typography.Paragraph type="secondary">推荐项来自 HIGH/MEDIUM 候选；LOW 只列在“其他可能”中。候选无需先确认，最终仍以本次提案批准为准。</Typography.Paragraph>
    <Select
      mode="multiple"
      aria-label="当前代码实现来源"
      value={selected}
      options={candidates.map((candidate) => ({
        value: candidate.candidate_id,
        label: `${candidate.confidence === 'LOW' ? '其他可能 · ' : ''}${candidate.display_name} · ${confidenceLabels[candidate.confidence]}`,
      }))}
      onChange={onChange}
      style={{ width: '100%' }}
      placeholder="尚未选择可验证的代码实现"
    />
    {missingEvidence && <Alert type="info" showIcon message="这条线索没有可验证源码证据，只能帮助描述业务，不能证明当前代码实现。" />}
    {identity && <AssistantPanel projectId={draft.project_id} surface="implementation-mapping" focus={kind === 'ROLE' ? { business_actor_id: identity } : { business_action_id: identity }} title="理解当前代码实现候选" actionLabel="解释候选" />}
  </details>
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

function manualActor(): BoundaryMaintenanceActorDto {
  return { item_id: localId('pactr'), actor_id: null, expected_current_revision: null, display_name: '', description: '', effective_state: 'ACTIVE', source_candidate_ids: [] }
}
function manualAction(): DraftAction {
  return { item_id: localId('pactn'), action_id: null, expected_current_revision: null, display_name: '', description: '', primary_resource_concept: '', operation_kind: 'CUSTOM', state_changing: false, effects: [emptyEffect()], effective_state: 'ACTIVE', source_candidate_ids: [] }
}
function emptyEffect(): DraftEffect {
  return { item_id: localId('peff'), effect_id: null, business_label: '', resource_concept: '', description: '', protected_projection: [] }
}

let sequence = 0
function localId(prefix: 'pactr' | 'pactn' | 'peff' | 'pperm') {
  sequence += 1
  const value = (Date.now() + sequence).toString(16).padStart(16, '0').slice(-16)
  return `${prefix}_${value}`
}

function updateAction(setter: React.Dispatch<React.SetStateAction<DraftAction[]>>, itemId: string, patch: Partial<DraftAction>) { setter((items) => items.map((item) => item.item_id === itemId ? { ...item, ...patch } : item)) }
function updateEffect(setter: React.Dispatch<React.SetStateAction<DraftAction[]>>, actionId: string, effectId: string, patch: Partial<DraftEffect>) { setter((items) => items.map((item) => item.item_id === actionId ? { ...item, effects: item.effects.map((effect) => effect.item_id === effectId ? { ...effect, ...patch } : effect) } : item)) }
function updatePermission(setter: React.Dispatch<React.SetStateAction<BoundaryMaintenancePermissionDto[]>>, itemId: string, patch: Partial<BoundaryMaintenancePermissionDto>) { setter((items) => items.map((item) => item.item_id === itemId ? { ...item, ...patch } : item)) }
function actorOption(item: BoundaryMaintenanceActorDto) { return { value: item.item_id, label: `${item.display_name || '尚未命名的主体'}${item.effective_state === 'RETIRED' ? '（停用）' : ''}` } }
function actionOption(item: DraftAction) { return { value: item.item_id, label: `${item.display_name || '尚未命名的动作'}${item.effective_state === 'RETIRED' ? '（停用）' : ''}` } }
function splitProjection(value: string) { return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean) }
function cleanAction(item: DraftAction): BoundaryMaintenanceActionDto { return { ...item, display_name: item.display_name.trim(), description: item.description.trim(), primary_resource_concept: item.primary_resource_concept.trim(), effects: item.effects.map((effect) => ({ ...effect, effect_kind: effect.effect_kind!, business_label: effect.business_label.trim(), resource_concept: effect.resource_concept.trim(), expected_state: effect.expected_state?.trim() || null, protected_projection: effect.effect_kind === 'DATA_DISCLOSURE' ? effect.protected_projection ?? [] : [], description: effect.description.trim() })) } }
function implementationLabel(status: string) { return status === 'CURRENT' ? '当前有效' : status === 'MISSING' ? '缺少可验证证据' : '需要重新确认' }

function validateDraft(actors: BoundaryMaintenanceActorDto[], actions: DraftAction[], permissions: BoundaryMaintenancePermissionDto[]) {
  if (!actors.length || actors.some((item) => !item.display_name.trim() || !item.description.trim())) return '请完整保留并填写每个业务主体。'
  if (!actions.length || actions.some((item) => !item.display_name.trim() || !item.description.trim() || !item.primary_resource_concept.trim())) return '请完整保留并填写每个业务动作。'
  if (actions.some((item) => !item.effects.length || item.effects.some((effect) => !effect.business_label.trim() || !effect.effect_kind || !effect.resource_concept.trim() || !effect.description.trim()))) return '每个业务动作至少需要一个填写完整的业务结果。'
  if (actions.some((item) => item.effects.some((effect) => effect.effect_kind === 'DATA_DISCLOSURE' && !effect.protected_projection?.length))) return '受保护数据读取必须明确有限字段。'
  if (permissions.some((item) => item.effective_state === 'ACTIVE' && !item.protected_effect_item_ids.length)) return '每条启用的权限规则至少保护一个业务结果。'
  return undefined
}

const operationOptions: Array<{ value: BoundaryMaintenanceActionDto['operation_kind']; label: string }> = [
  { value: 'READ', label: '读取' }, { value: 'CHANGE', label: '变更' }, { value: 'DELETE', label: '删除' },
  { value: 'EXPORT', label: '导出' }, { value: 'ADMIN', label: '管理' }, { value: 'CUSTOM', label: '其他业务动作' },
]
const effectOptions = Object.entries(effectKindLabels).map(([value, label]) => ({ value, label }))
