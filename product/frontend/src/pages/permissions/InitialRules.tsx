import { useEffect, useId, useRef, useState } from 'react';
import { PlusOutlined, DeleteOutlined, ArrowLeftOutlined, ArrowRightOutlined, SafetyOutlined, CheckCircleOutlined, StopOutlined } from '@ant-design/icons';
import { businessBoundariesApi as api, type BoundaryMaintenanceDraftDto, type BoundaryMaintenanceCommandDto, type ProposedEffectDto } from '../../entities/permission/api/businessBoundaries';
import { ApiError } from '../../shared/api/http';
import { readPending, savePending } from '../../shared/lib/operations';
import { Button } from '../../shared/ui/actions';
import { Choice } from '../../shared/ui/Choice';
import { Heading, Field } from '../../shared/ui/layout';
import { Badge, Notice } from '../../shared/ui/feedback';
import { Tabs } from '../../shared/ui/Tabs';

const id = (prefix: string) => prefix + crypto.randomUUID().replaceAll('-', '').slice(0, 16);
const effectKinds = { STATE_MUTATION: '状态改变', DATA_DISCLOSURE: '读取业务数据', FILE_CONTENT_DELIVERY: '交付文件内容', OBJECT_CREATION: '创建业务对象', EXTERNAL_DISPATCH: '发送外部消息', RESTRICTED_FUNCTION_INVOCATION: '调用受限功能', CREDENTIAL_ACCESS: '取得凭据' } as const;
type Draft = BoundaryMaintenanceCommandDto & { proposal_id?: string; uncertain?: boolean };
type Section = 'actors' | 'actions' | 'permissions';
const newEffect = (): ProposedEffectDto => ({ item_id: id('peff_'), business_label: '', effect_kind: 'STATE_MUTATION', resource_concept: '', description: '' });

export function InitialRules({ projectId, basis, onBack, onProposal, onError }: { projectId: string; basis: BoundaryMaintenanceDraftDto; onBack: () => void; onProposal: (id: string) => Promise<void>; onError: (error: unknown) => void }) {
    const key = 'jiejian.studio.initial-rules:' + projectId;
    const [draft, setDraft] = useState<Draft>(() => readPending<Draft>(key) ?? { expected_boundary_state_fingerprint: basis.boundary_state_fingerprint, actors: basis.actors, actions: basis.actions, permissions: basis.permissions, provenance: '' });
    const [section, setSection] = useState<Section>('actors');
    const [busy, setBusy] = useState(false), [proposals, setProposals] = useState<string[]>([]), lock = useRef(false);
    const prefix = useId(), panelId = prefix + '-panel';
    useEffect(() => { savePending(key, draft); }, [key, draft]);
    // 草稿可以继续保留，但不能把旧依据下的编辑自动覆盖到已经变化的正式规则上。
    const changed = basis.boundary_state_fingerprint !== draft.expected_boundary_state_fingerprint;
    const disabled = busy || Boolean(draft.uncertain) || changed;
    const edit = (value: Partial<Draft>) => setDraft(current => ({ ...current, ...value }));
    const run = async (callback: () => Promise<void>) => { if (lock.current) return; lock.current = true; setBusy(true); try { await callback(); } catch (error) { onError(error); } finally { lock.current = false; setBusy(false); } };
    const rolesReady = draft.actors.length > 0 && draft.actors.every(item => item.display_name.trim() && item.description.trim());
    const actionsReady = draft.actions.length > 0 && draft.actions.every(item => item.display_name.trim() && item.description.trim() && item.primary_resource_concept.trim() && item.effects.length && item.effects.every(effect => effect.business_label.trim() && effect.description.trim() && effect.resource_concept.trim() && (effect.effect_kind !== 'DATA_DISCLOSURE' || effect.protected_projection?.length)));
    const rulesReady = draft.permissions.length > 0 && draft.permissions.every(item => item.subject_actor_item_id && item.business_action_item_id && item.resource_owner_actor_item_id && item.protected_effect_item_ids.length);
    const valid = rolesReady && actionsReady && rulesReady && Boolean(draft.provenance.trim());
    const missing: Array<{ section: Section; label: string }> = [
        ...(!rolesReady ? [{ section: 'actors' as const, label: '角色名称与职责' }] : []),
        ...(!actionsReady ? [{ section: 'actions' as const, label: '业务操作与结果依据' }] : []),
        ...(!rulesReady ? [{ section: 'permissions' as const, label: '访问规则与受保护结果' }] : []),
        ...(!draft.provenance.trim() ? [{ section: 'permissions' as const, label: '权限要求的依据' }] : []),
    ];
    const addRole = () => edit({ actors: [...draft.actors, { item_id: id('pactr_'), display_name: '', description: '', effective_state: 'ACTIVE', source_candidate_ids: [] }] });
    const addAction = () => edit({ actions: [...draft.actions, { item_id: id('pactn_'), display_name: '', description: '', primary_resource_concept: '', operation_kind: 'CHANGE', state_changing: true, effects: [newEffect()], effective_state: 'ACTIVE', source_candidate_ids: [] }] });
    const addRule = () => edit({ permissions: [...draft.permissions, { item_id: id('pperm_'), effective_state: 'ACTIVE', subject_actor_item_id: draft.actors[0]?.item_id ?? '', resource_owner_actor_item_id: draft.actors[0]?.item_id ?? '', business_action_item_id: draft.actions[0]?.item_id ?? '', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: [] }] });
    const submit = () => void run(async () => {
        // 发出写请求前标记结果未知；只有收到明确拒绝或提案回执，才允许整理下一次提交。
        edit({ uncertain: true });
        try {
            const { proposal_id: _, uncertain: __, ...command } = draft;
            const result = await api.createMaintenanceProposal(projectId, command);
            edit({ proposal_id: result.proposal.proposal_id, uncertain: false });
            await onProposal(result.proposal.proposal_id);
        } catch (error) {
            if (error instanceof ApiError && ['INPUT_INVALID', 'STATE_PRECONDITION', 'API_VALIDATION_ERROR'].includes(error.code)) edit({ uncertain: false });
            throw error;
        }
    });
    return <>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true" />} onClick={onBack}>全部权限规则</Button></div>
        <Heading title="编写权限要求"><p>定义业务角色和操作，再明确每条访问要求。</p></Heading>
        {changed && <Notice>正式规则已变化，草稿保留。请返回核对当前规则后再整理。</Notice>}
        <div className="jj-rule-authoring">
            <div className="jj-rule-authoring-editor">
                <Tabs label="权限编写分区" value={section} items={[
                    { value: 'actors', label: '业务角色 ' + draft.actors.length },
                    { value: 'actions', label: '操作与结果 ' + draft.actions.length },
                    { value: 'permissions', label: '访问规则 ' + draft.permissions.length },
                ]} onValueChange={value => setSection(value as Section)} idPrefix={prefix} panelId={panelId} />
                <div role="tabpanel" id={panelId} aria-labelledby={prefix + '-' + section} className="jj-rule-authoring-panel" key={section}>
                    <fieldset className="jj-initial-rules" disabled={disabled}>
                        {section === 'actors' && <section className="jj-initial-definitions">
                            <header><h2>定义业务角色</h2><Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={addRole}>添加角色</Button></header>
                            {!draft.actors.length && <p className="jj-initial-empty">添加使用这项业务的角色，例如负责人、成员或访客。</p>}
                            {draft.actors.map((role, index) => <article className="jj-initial-role" key={role.item_id}>
                                <div className="jj-initial-role-fields">
                                    <Field label="角色名称"><input maxLength={128} value={role.display_name} onChange={event => edit({ actors: draft.actors.map((item, i) => i === index ? { ...item, display_name: event.target.value } : item) })} /></Field>
                                    <Field label="对应源码角色"><Choice disabled={disabled} value={role.source_candidate_ids?.[0] ?? ''} onValueChange={value => edit({ actors: draft.actors.map((item, i) => i === index ? { ...item, source_candidate_ids: value ? [value] : [] } : item) })}><option value="">暂未对应</option>{basis.candidate_options.filter(item => item.candidate_kind === 'ROLE').map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.display_name}</option>)}</Choice></Field>
                                    <Field label="角色职责"><textarea rows={2} maxLength={1024} value={role.description} onChange={event => edit({ actors: draft.actors.map((item, i) => i === index ? { ...item, description: event.target.value } : item) })} /></Field>
                                </div>
                                <Button kind="quiet" aria-label={'移除角色 ' + (role.display_name || index + 1)} disabled={draft.permissions.some(item => item.subject_actor_item_id === role.item_id || item.resource_owner_actor_item_id === role.item_id)} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => edit({ actors: draft.actors.filter(item => item.item_id !== role.item_id) })} />
                            </article>)}
                        </section>}
                        {section === 'actions' && <section className="jj-initial-definitions">
                            <header><h2>定义操作与结果</h2><Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={addAction}>添加操作</Button></header>
                            {!draft.actions.length && <p className="jj-initial-empty">添加需要检查权限的业务操作，并说明怎样确认实际结果。</p>}
                            {draft.actions.map((action, index) => {
                                const update = (value: Partial<typeof action>) => edit({ actions: draft.actions.map((item, i) => i === index ? { ...item, ...value } : item) });
                                return <article className="jj-initial-action" key={action.item_id}>
                                    <div className="jj-initial-action-fields">
                                        <Field label="操作名称"><input maxLength={256} value={action.display_name} onChange={event => update({ display_name: event.target.value })} /></Field>
                                        <Field label="操作的资源"><input maxLength={128} value={action.primary_resource_concept} onChange={event => update({ primary_resource_concept: event.target.value })} /></Field>
                                        <Field label="操作类型"><Choice disabled={disabled} value={action.operation_kind} onValueChange={value => update({ operation_kind: value as typeof action.operation_kind })}>{Object.entries({ READ: '读取', CHANGE: '修改', DELETE: '删除', EXPORT: '导出', ADMIN: '管理', CUSTOM: '其他' }).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Choice></Field>
                                        <Field label="对应源码操作"><Choice disabled={disabled} value={action.source_candidate_ids?.[0] ?? ''} onValueChange={value => update({ source_candidate_ids: value ? [value] : [] })}><option value="">暂未对应</option>{basis.candidate_options.filter(item => item.candidate_kind === 'ACTION').map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.display_name}</option>)}</Choice></Field>
                                        <Field label="操作说明"><textarea rows={2} maxLength={1024} value={action.description} onChange={event => update({ description: event.target.value })} /></Field>
                                        <label className="jj-checkbox"><input type="checkbox" checked={action.state_changing} onChange={event => update({ state_changing: event.target.checked })} /><span>此操作会改变业务数据</span></label>
                                    </div>
                                    <div className="jj-initial-effects">
                                        <header><h3>业务结果</h3><Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={() => update({ effects: [...action.effects, newEffect()] })}>添加结果</Button></header>
                                        {action.effects.map((effect, effectIndex) => {
                                            const updateEffect = (value: Partial<ProposedEffectDto>) => update({ effects: action.effects.map((item, i) => i === effectIndex ? { ...item, ...value } : item) });
                                            return <section key={effect.item_id}>
                                                <div className="jj-initial-effect-fields">
                                                    <Field label="结果名称"><input maxLength={256} value={effect.business_label} onChange={event => updateEffect({ business_label: event.target.value })} /></Field>
                                                    <Field label="结果类型"><Choice disabled={disabled} value={effect.effect_kind} onValueChange={value => updateEffect({ effect_kind: value as ProposedEffectDto['effect_kind'], protected_projection: [] })}>{Object.entries(effectKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Choice></Field>
                                                    <Field label="结果涉及的资源"><input maxLength={128} value={effect.resource_concept} onChange={event => updateEffect({ resource_concept: event.target.value })} /></Field>
                                                    <Field label="预期业务状态（选填）"><input maxLength={512} value={effect.expected_state ?? ''} onChange={event => updateEffect({ expected_state: event.target.value || null })} /></Field>
                                                    <Field label="判断依据"><textarea rows={2} maxLength={1024} value={effect.description} onChange={event => updateEffect({ description: event.target.value })} /></Field>
                                                    {effect.effect_kind === 'DATA_DISCLOSURE' && <Field label="受保护的业务字段" hint="填写真实字段名，以逗号分隔。"><input value={effect.protected_projection?.join(', ') ?? ''} onChange={event => updateEffect({ protected_projection: event.target.value.split(',').map(value => value.trim()).filter(Boolean) })} /></Field>}
                                                </div>
                                                {action.effects.length > 1 && <Button kind="quiet" disabled={draft.permissions.some(item => item.protected_effect_item_ids.includes(effect.item_id))} onClick={() => update({ effects: action.effects.filter(item => item.item_id !== effect.item_id) })}>移除此结果</Button>}
                                            </section>;
                                        })}
                                    </div>
                                    <div className="jj-initial-entity-actions"><Button kind="quiet" disabled={draft.permissions.some(item => item.business_action_item_id === action.item_id)} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => edit({ actions: draft.actions.filter(item => item.item_id !== action.item_id) })}>移除此操作</Button></div>
                                </article>;
                            })}
                        </section>}
                        {section === 'permissions' && <section className="jj-initial-definitions">
                            <header><h2>编写访问规则</h2><Button kind="quiet" disabled={!draft.actors.length || !draft.actions.length} icon={<PlusOutlined aria-hidden="true" />} onClick={addRule}>添加规则</Button></header>
                            {!draft.permissions.length && <p className="jj-initial-empty">角色和操作填写后，即可添加允许或禁止的访问要求。</p>}
                            {draft.permissions.map((rule, index) => {
                                const update = (value: Partial<typeof rule>) => edit({ permissions: draft.permissions.map((item, i) => i === index ? { ...item, ...value } : item) });
                                const action = draft.actions.find(item => item.item_id === rule.business_action_item_id);
                                return <article className="jj-initial-permission" key={rule.item_id}>
                                    <header><Badge tone={rule.expectation === 'ALLOW' ? 'positive' : 'negative'}>{rule.expectation === 'ALLOW' ? '允许访问' : '禁止访问'}</Badge><Button kind="quiet" aria-label={'移除规则 ' + (index + 1)} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => edit({ permissions: draft.permissions.filter(item => item.item_id !== rule.item_id) })} /></header>
                                    <div className="jj-initial-permission-fields">
                                        <Field label="操作角色"><Choice disabled={disabled} value={rule.subject_actor_item_id} onValueChange={value => update({ subject_actor_item_id: value, resource_owner_actor_item_id: rule.relation === 'OTHER_ROLE' ? rule.resource_owner_actor_item_id : value })}>{draft.actors.map(item => <option key={item.item_id} value={item.item_id}>{item.display_name || '未命名角色'}</option>)}</Choice></Field>
                                        <Field label="访问要求"><Choice disabled={disabled} value={rule.expectation} onValueChange={value => update({ expectation: value as 'ALLOW' | 'DENY' })}><option value="ALLOW">允许</option><option value="DENY">禁止</option></Choice></Field>
                                        <Field label="业务操作"><Choice disabled={disabled} value={rule.business_action_item_id} onValueChange={value => update({ business_action_item_id: value, protected_effect_item_ids: [] })}>{draft.actions.map(item => <option key={item.item_id} value={item.item_id}>{item.display_name || '未命名操作'}</option>)}</Choice></Field>
                                        <Field label="资源范围"><Choice disabled={disabled} value={rule.relation === 'OTHER_ROLE' ? rule.resource_owner_actor_item_id : rule.relation} onValueChange={value => update(value === 'OWNS' || value === 'SAME_ROLE_OTHER_ACCOUNT' ? { relation: value, resource_owner_actor_item_id: rule.subject_actor_item_id } : { relation: 'OTHER_ROLE', resource_owner_actor_item_id: value })}><option value="OWNS">自己的资源</option><option value="SAME_ROLE_OTHER_ACCOUNT">同角色其他账号的资源</option>{draft.actors.filter(item => item.item_id !== rule.subject_actor_item_id).map(item => <option key={item.item_id} value={item.item_id}>{item.display_name || '其他角色'}的资源</option>)}</Choice></Field>
                                    </div>
                                    <fieldset className="jj-initial-protected"><legend>{rule.expectation === 'ALLOW' ? '应当产生的结果' : '不得产生的结果'}</legend>{action?.effects.map(effect => <label className="jj-checkbox" key={effect.item_id}><input type="checkbox" checked={rule.protected_effect_item_ids.includes(effect.item_id)} onChange={event => update({ protected_effect_item_ids: event.target.checked ? [...rule.protected_effect_item_ids, effect.item_id] : rule.protected_effect_item_ids.filter(value => value !== effect.item_id) })} /><span>{effect.business_label || '尚未填写的业务结果'}</span></label>)}</fieldset>
                                </article>;
                            })}
                        </section>}
                    </fieldset>
                    {section !== 'permissions' && <footer className="jj-initial-next"><Button onClick={() => setSection(section === 'actors' ? 'actions' : 'permissions')}>{section === 'actors' ? '继续定义操作与结果' : '继续编写访问规则'}<ArrowRightOutlined aria-hidden="true" /></Button></footer>}
                </div>
            </div>
            <aside className="jj-initial-preview" data-section={section} aria-label="权限草稿预览">
                <header><span className="jj-initial-preview-symbol"><SafetyOutlined aria-hidden="true" /></span><div><h2>权限预览</h2><Badge>尚未生效</Badge></div></header>
                {draft.permissions.length ? <div className="jj-initial-preview-rules">{draft.permissions.map((rule, index) => {
                    const actor = draft.actors.find(item => item.item_id === rule.subject_actor_item_id), owner = draft.actors.find(item => item.item_id === rule.resource_owner_actor_item_id), action = draft.actions.find(item => item.item_id === rule.business_action_item_id);
                    const relation = rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '同角色其他账号的资源' : (owner?.display_name || '指定角色') + '的资源';
                    return <Button kind="quiet" className="jj-initial-preview-rule" data-tone={rule.expectation === 'ALLOW' ? 'positive' : 'negative'} key={rule.item_id} onClick={() => setSection('permissions')} aria-label={'编辑规则 ' + (index + 1)}>
                        {rule.expectation === 'ALLOW' ? <CheckCircleOutlined aria-hidden="true" /> : <StopOutlined aria-hidden="true" />}
                        <span><strong>{actor?.display_name || '未命名角色'}{rule.expectation === 'ALLOW' ? '可以' : '不得'}{action?.display_name || '执行操作'}</strong><small>{relation}</small>{action?.effects.filter(effect => rule.protected_effect_item_ids.includes(effect.item_id)).map(effect => <span className="jj-initial-preview-effect" key={effect.item_id}>{effect.business_label || '未命名结果'}</span>)}</span>
                    </Button>;
                })}</div> : <div className="jj-initial-preview-empty"><p>尚未添加访问规则</p><span>填写角色与操作后，在这里核对完整的权限要求。</span></div>}
                {section === 'permissions' && <div className="jj-initial-provenance"><Field label="权限要求的依据"><textarea disabled={disabled} rows={3} maxLength={512} value={draft.provenance} onChange={event => edit({ provenance: event.target.value })} /></Field></div>}
                <div className="jj-initial-submit">
                    {!!missing.length && <div className="jj-initial-missing"><h3>仍需填写</h3>{missing.map(item => <Button kind="quiet" key={item.label} onClick={() => setSection(item.section)}>{item.label}<ArrowRightOutlined aria-hidden="true" /></Button>)}</div>}
                    <p>生成提案后，审阅并批准才会生效。</p>
                    <Button kind="primary" busy={busy} disabled={!valid || disabled} onClick={submit}>生成完整提案<ArrowRightOutlined aria-hidden="true" /></Button>
                </div>
            </aside>
        </div>
        {draft.uncertain && <Notice>提案结果尚未确认，草稿已保留。<Button busy={busy} onClick={() => void run(async () => { const value = await api.proposals(projectId, true); setProposals(value.proposals.map(item => item.proposal.proposal_id)); })}>查询已接收的提案</Button></Notice>}
        {(draft.proposal_id ? [draft.proposal_id] : proposals).map((value, index) => <Button key={value} onClick={() => void run(() => onProposal(value))}>审阅提案{proposals.length > 1 ? ' ' + (index + 1) : ''}</Button>)}
    </>;
}
