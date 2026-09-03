// 业务边界本地草稿编辑器：只有“生成待审业务边界”才写入不可变 Proposal。

import { Alert, Button, Checkbox, Divider, Input, Select, Space, Typography } from 'antd'
import { useMemo, useState } from 'react'
import type {
  BoundaryDraftViewDto,
  BoundaryProposalCommandDto,
  BusinessEffectKind,
  ProposedActionDto,
  ProposedActorDto,
  ProposedPermissionDto,
} from '../../api/businessBoundaries'
import { confidenceLabels, effectKindLabels, expectationLabels, relationLabels } from './boundaryLabels'

type DraftEffect = Omit<ProposedActionDto['effect_catalog'][number], 'effect_kind'> & { effect_kind?: BusinessEffectKind }
type DraftAction = Omit<ProposedActionDto, 'effect_catalog'> & { effect_catalog: DraftEffect[] }

export function BoundaryProposalEditor({ preview, initialCommand, busy, onSubmit }: {
  preview: BoundaryDraftViewDto
  initialCommand?: BoundaryProposalCommandDto
  busy: boolean
  onSubmit: (command: BoundaryProposalCommandDto) => void
}) {
  const initial = useMemo(() => initialDraft(preview, initialCommand), [initialCommand, preview])
  const [actors, setActors] = useState<ProposedActorDto[]>(initial.actors)
  const [actions, setActions] = useState<DraftAction[]>(initial.actions)
  const [permissions, setPermissions] = useState<ProposedPermissionDto[]>(initial.permissions)
  const [error, setError] = useState<string>()
  const lowCandidates = preview.candidates.filter((item) => item.confidence === 'LOW')

  const addCandidate = (candidate: BoundaryDraftViewDto['candidates'][number]) => {
    if (candidate.candidate_kind === 'ROLE') {
      if (actors.some((item) => item.source_candidate_ids?.includes(candidate.candidate_id))) return
      setActors((items) => [...items, actorFromCandidate(candidate)])
      return
    }
    if (actions.some((item) => item.source_candidate_ids?.includes(candidate.candidate_id))) return
    setActions((items) => [...items, actionFromCandidate(candidate)])
  }
  const removeActor = (itemId: string) => {
    setActors((items) => items.filter((item) => item.item_id !== itemId))
    setPermissions((items) => items.filter((item) => item.subject_actor_item_id !== itemId && item.resource_owner_actor_item_id !== itemId))
  }
  const removeAction = (itemId: string) => {
    setActions((items) => items.filter((item) => item.item_id !== itemId))
    setPermissions((items) => items.filter((item) => item.business_action_item_id !== itemId))
  }
  const addPermission = () => {
    const actor = actors[0]
    const action = actions[0]
    if (!actor || !action) {
      setError('先添加至少一个业务主体和一个业务动作。')
      return
    }
    setPermissions((items) => [...items, {
      item_id: localId('pperm'), write_mode: 'CREATE', effective_state: 'ACTIVE',
      subject_actor_item_id: actor.item_id, business_action_item_id: action.item_id,
      resource_owner_actor_item_id: actor.item_id, relation: 'OWNS', expectation: 'ALLOW',
      protected_effect_item_ids: action.effect_catalog.map((item) => item.item_id),
    }])
  }
  const submit = () => {
    const issue = validateDraft(actors, actions, permissions)
    if (issue) {
      setError(issue)
      return
    }
    setError(undefined)
    onSubmit({
      proposed_actors: actors.map(cleanActor),
      proposed_actions: actions.map(cleanAction),
      proposed_permissions: permissions,
      unresolved_questions: [],
      provenance: '本机界鉴用户在业务边界页面整理并提交',
    })
  }

  return <section className="boundary-editor" aria-labelledby="boundary-editor-title">
    <div className="boundary-section-heading">
      <div><Typography.Title level={3} id="boundary-editor-title">从当前源码整理业务边界</Typography.Title><Typography.Paragraph type="secondary">源码候选只帮助识别名称。最终业务主体、动作、结果和权限均由你审阅后形成新提案。</Typography.Paragraph></div>
    </div>
    <div className="boundary-candidate-basis" aria-label="源码识别依据">
      <Typography.Text strong>当前识别依据</Typography.Text>
      <div>{preview.candidates.filter((item) => item.confidence !== 'LOW').map((item) => <span key={item.candidate_id} className="boundary-candidate-chip"><b>{item.display_name}</b><small>{confidenceLabels[item.confidence]}</small></span>)}</div>
      {lowCandidates.length > 0 && <details><summary>查看可能相关的候选</summary><Space wrap>{lowCandidates.map((item) => <Button key={item.candidate_id} onClick={() => addCandidate(item)}>加入“{item.display_name}”</Button>)}</Space></details>}
      {preview.candidates.length === 0 && <Typography.Text type="secondary">当前源码没有可靠候选；仍可手工建立稳定业务语义。</Typography.Text>}
    </div>

    <Divider orientation="left">谁在使用应用</Divider>
    <div className="boundary-editor-list">{actors.map((actor) => <article key={actor.item_id} className="boundary-editor-card">
      <Input aria-label="业务主体名称" value={actor.display_name} placeholder="业务主体名称" onChange={(event) => setActors((items) => items.map((item) => item.item_id === actor.item_id ? { ...item, display_name: event.target.value } : item))} />
      <Input.TextArea aria-label={`${actor.display_name || '业务主体'}说明`} value={actor.description} placeholder="用业务语言说明这个主体的职责" autoSize onChange={(event) => setActors((items) => items.map((item) => item.item_id === actor.item_id ? { ...item, description: event.target.value } : item))} />
      <Button danger type="text" onClick={() => removeActor(actor.item_id)}>移除主体</Button>
    </article>)}</div>
    <Button onClick={() => setActors((items) => [...items, manualActor()])}>手工补充业务主体</Button>

    <Divider orientation="left">做什么，会产生什么业务结果</Divider>
    <div className="boundary-editor-list">{actions.map((action) => <article key={action.item_id} className="boundary-editor-card boundary-action-editor">
      <div className="boundary-editor-row"><Input aria-label="业务动作名称" value={action.display_name} placeholder="业务动作名称" onChange={(event) => updateAction(setActions, action.item_id, { display_name: event.target.value })} /><Select aria-label={`${action.display_name || '业务动作'}类型`} value={action.operation_kind} options={operationOptions} onChange={(value) => updateAction(setActions, action.item_id, { operation_kind: value })} /></div>
      <Input.TextArea aria-label={`${action.display_name || '业务动作'}说明`} value={action.description} placeholder="说明用户完成的业务动作" autoSize onChange={(event) => updateAction(setActions, action.item_id, { description: event.target.value })} />
      <Input aria-label={`${action.display_name || '业务动作'}资源概念`} value={action.primary_resource_concept} placeholder="主要资源概念，例如项目交付空间" onChange={(event) => updateAction(setActions, action.item_id, { primary_resource_concept: event.target.value })} />
      <Typography.Text strong>业务结果</Typography.Text>
      {action.effect_catalog.map((effect) => <div className="boundary-effect-editor" key={effect.item_id}>
        <Input aria-label="业务结果名称" value={effect.business_label} placeholder="例如：完整项目交付包真实形成" onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { business_label: event.target.value })} />
        <Select aria-label={`${effect.business_label || '业务结果'}类型`} value={effect.effect_kind} placeholder="选择真实业务结果类型" options={effectOptions} onChange={(value) => updateEffect(setActions, action.item_id, effect.item_id, { effect_kind: value })} />
        <Input aria-label={`${effect.business_label || '业务结果'}资源概念`} value={effect.resource_concept} placeholder="资源概念" onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { resource_concept: event.target.value })} />
        {effect.effect_kind === 'DATA_DISCLOSURE' && <Input aria-label={`${effect.business_label || '业务结果'}有限字段`} value={(effect.protected_projection ?? []).join(', ')} placeholder="有限字段，例如 material.title, material.summary" onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { protected_projection: splitProjection(event.target.value) })} />}
        <Input.TextArea aria-label={`${effect.business_label || '业务结果'}说明`} value={effect.description} placeholder="说明用户真正得到或改变的业务结果" autoSize onChange={(event) => updateEffect(setActions, action.item_id, effect.item_id, { description: event.target.value })} />
        <Button danger type="text" onClick={() => updateAction(setActions, action.item_id, { effect_catalog: action.effect_catalog.filter((item) => item.item_id !== effect.item_id) })}>移除业务结果</Button>
      </div>)}
      <Space><Button onClick={() => updateAction(setActions, action.item_id, { effect_catalog: [...action.effect_catalog, emptyEffect()] })}>添加业务结果</Button><Button danger type="text" onClick={() => removeAction(action.item_id)}>移除动作</Button></Space>
    </article>)}</div>
    <Button onClick={() => setActions((items) => [...items, manualAction()])}>手工补充业务动作</Button>

    <Divider orientation="left">谁可以做什么</Divider>
    <div className="boundary-editor-list">{permissions.map((permission) => {
      const action = actions.find((item) => item.item_id === permission.business_action_item_id)
      return <article key={permission.item_id} className="boundary-editor-card boundary-permission-editor">
        <Select aria-label="谁" value={permission.subject_actor_item_id} options={actors.map(actorOption)} onChange={(value) => updatePermission(setPermissions, permission.item_id, { subject_actor_item_id: value })} />
        <Select aria-label="做什么" value={permission.business_action_item_id} options={actions.map(actionOption)} onChange={(value) => {
          const next = actions.find((item) => item.item_id === value)
          updatePermission(setPermissions, permission.item_id, { business_action_item_id: value, protected_effect_item_ids: next?.effect_catalog.map((item) => item.item_id) ?? [] })
        }} />
        <Select aria-label="对谁拥有的资源" value={permission.resource_owner_actor_item_id} options={actors.map(actorOption)} onChange={(value) => updatePermission(setPermissions, permission.item_id, { resource_owner_actor_item_id: value })} />
        <Select aria-label="资源关系" value={permission.relation} options={Object.entries(relationLabels).map(([value, label]) => ({ value, label }))} onChange={(value) => updatePermission(setPermissions, permission.item_id, { relation: value })} />
        <Select aria-label="允许或拒绝" value={permission.expectation} options={Object.entries(expectationLabels).map(([value, label]) => ({ value, label }))} onChange={(value) => updatePermission(setPermissions, permission.item_id, { expectation: value })} />
        <Checkbox.Group aria-label="这条规则保护的业务结果" value={permission.protected_effect_item_ids} options={(action?.effect_catalog ?? []).map((effect) => ({ value: effect.item_id, label: effect.business_label || '尚未命名的业务结果' }))} onChange={(values) => updatePermission(setPermissions, permission.item_id, { protected_effect_item_ids: values.map(String) })} />
        <Button danger type="text" onClick={() => setPermissions((items) => items.filter((item) => item.item_id !== permission.item_id))}>移除权限规则</Button>
      </article>
    })}</div>
    <Button onClick={addPermission}>添加权限规则</Button>
    {error && <Alert type="warning" showIcon message="草稿还不能生成提案" description={error} />}
    <div className="boundary-editor-submit"><Button type="primary" loading={busy} onClick={submit}>生成待审业务边界</Button></div>
  </section>
}

function initialDraft(preview: BoundaryDraftViewDto, command?: BoundaryProposalCommandDto) {
  if (command) return {
    actors: command.proposed_actors.map((item) => ({ ...item, write_mode: 'CREATE' as const, actor_id: null, expected_current_revision: null })),
    actions: command.proposed_actions.map((item) => ({ ...item, write_mode: 'CREATE' as const, action_id: null, expected_current_revision: null })),
    permissions: command.proposed_permissions.map((item) => ({ ...item, write_mode: 'CREATE' as const, intent_id: null, expected_current_revision: null })),
  }
  const selected = preview.candidates.filter((item) => item.confidence !== 'LOW')
  return {
    actors: selected.filter((item) => item.candidate_kind === 'ROLE').map(actorFromCandidate),
    actions: selected.filter((item) => item.candidate_kind === 'ACTION').map(actionFromCandidate),
    permissions: [],
  }
}

function actorFromCandidate(candidate: BoundaryDraftViewDto['candidates'][number]): ProposedActorDto {
  return { item_id: localId('pactr'), write_mode: 'CREATE', source_candidate_ids: [candidate.candidate_id], display_name: candidate.display_name, description: '由当前源码候选整理，业务含义由本次人工确认。', effective_state: 'ACTIVE' }
}
function actionFromCandidate(candidate: BoundaryDraftViewDto['candidates'][number]): DraftAction {
  return { item_id: localId('pactn'), write_mode: 'CREATE', source_candidate_ids: [candidate.candidate_id], display_name: candidate.display_name, description: '由当前源码候选整理，业务含义由本次人工确认。', primary_resource_concept: '', operation_kind: 'CUSTOM', state_changing: false, effect_catalog: [emptyEffect()], effective_state: 'ACTIVE' }
}
function manualActor(): ProposedActorDto { return { item_id: localId('pactr'), write_mode: 'CREATE', source_candidate_ids: [], display_name: '', description: '', effective_state: 'ACTIVE' } }
function manualAction(): DraftAction { return { item_id: localId('pactn'), write_mode: 'CREATE', source_candidate_ids: [], display_name: '', description: '', primary_resource_concept: '', operation_kind: 'CUSTOM', state_changing: false, effect_catalog: [emptyEffect()], effective_state: 'ACTIVE' } }
function emptyEffect(): DraftEffect { return { item_id: localId('peff'), business_label: '', resource_concept: '', description: '', protected_projection: [] } }

let sequence = 0
function localId(prefix: 'pactr' | 'pactn' | 'peff' | 'pperm') {
  sequence += 1
  const value = (Date.now() + sequence).toString(16).padStart(16, '0').slice(-16)
  return `${prefix}_${value}`
}

function updateAction(setter: React.Dispatch<React.SetStateAction<DraftAction[]>>, itemId: string, patch: Partial<DraftAction>) { setter((items) => items.map((item) => item.item_id === itemId ? { ...item, ...patch } : item)) }
function updateEffect(setter: React.Dispatch<React.SetStateAction<DraftAction[]>>, actionId: string, effectId: string, patch: Partial<DraftEffect>) { setter((items) => items.map((item) => item.item_id === actionId ? { ...item, effect_catalog: item.effect_catalog.map((effect) => effect.item_id === effectId ? { ...effect, ...patch } : effect) } : item)) }
function updatePermission(setter: React.Dispatch<React.SetStateAction<ProposedPermissionDto[]>>, itemId: string, patch: Partial<ProposedPermissionDto>) { setter((items) => items.map((item) => item.item_id === itemId ? { ...item, ...patch } : item)) }
function actorOption(item: ProposedActorDto) { return { value: item.item_id, label: item.display_name || '尚未命名的主体' } }
function actionOption(item: DraftAction) { return { value: item.item_id, label: item.display_name || '尚未命名的动作' } }
function splitProjection(value: string) { return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean) }
function cleanActor(item: ProposedActorDto): ProposedActorDto { return { ...item, display_name: item.display_name.trim(), description: item.description.trim() } }
function cleanAction(item: DraftAction): ProposedActionDto { return { ...item, display_name: item.display_name.trim(), description: item.description.trim(), primary_resource_concept: item.primary_resource_concept.trim(), effect_catalog: item.effect_catalog.map((effect) => ({ ...effect, effect_kind: effect.effect_kind!, business_label: effect.business_label.trim(), resource_concept: effect.resource_concept.trim(), expected_state: effect.expected_state?.trim() || null, protected_projection: effect.effect_kind === 'DATA_DISCLOSURE' ? effect.protected_projection ?? [] : [], description: effect.description.trim() })) } }

function validateDraft(actors: ProposedActorDto[], actions: DraftAction[], permissions: ProposedPermissionDto[]) {
  if (!actors.length) return '至少需要一个业务主体。'
  if (actors.some((item) => !item.display_name.trim() || !item.description.trim())) return '请完整填写每个业务主体的名称和说明。'
  if (!actions.length) return '至少需要一个业务动作。'
  if (actions.some((item) => !item.display_name.trim() || !item.description.trim() || !item.primary_resource_concept.trim())) return '请完整填写每个业务动作的名称、说明和主要资源概念。'
  if (actions.some((item) => !item.effect_catalog.length)) return '每个业务动作至少需要一个真实业务结果。'
  if (actions.some((item) => item.effect_catalog.some((effect) => !effect.business_label.trim() || !effect.effect_kind || !effect.resource_concept.trim() || !effect.description.trim()))) return '请完整填写每个业务结果的名称、类型、资源概念和说明。'
  if (actions.some((item) => item.effect_catalog.some((effect) => effect.effect_kind === 'DATA_DISCLOSURE' && !effect.protected_projection?.length))) return '受保护数据读取必须明确有限字段。'
  if (!permissions.length) return '至少需要一条允许或拒绝规则。'
  if (permissions.some((item) => !item.protected_effect_item_ids.length)) return '每条权限规则至少保护一个业务结果。'
  return undefined
}

const operationOptions: Array<{ value: ProposedActionDto['operation_kind']; label: string }> = [
  { value: 'READ', label: '读取' }, { value: 'CHANGE', label: '变更' }, { value: 'DELETE', label: '删除' },
  { value: 'EXPORT', label: '导出' }, { value: 'ADMIN', label: '管理' }, { value: 'CUSTOM', label: '其他业务动作' },
]
const effectOptions = Object.entries(effectKindLabels).map(([value, label]) => ({ value, label }))
