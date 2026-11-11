import {editorDraft,rememberEditorDraft,useDraftProtection} from '../../entities/runtime/model/handoff'
import {prefixedId as id} from '../../shared/lib/id'
import {RuleConditionsEditor, conditionLabels} from '../../entities/permission/ui/RuleConditions';
import { useEffect, useId, useRef, useState } from 'react';
import PlusOutlined from '@ant-design/icons/PlusOutlined';
import DeleteOutlined from '@ant-design/icons/DeleteOutlined';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import SafetyOutlined from '@ant-design/icons/SafetyOutlined';
import CheckCircleOutlined from '@ant-design/icons/CheckCircleOutlined';
import StopOutlined from '@ant-design/icons/StopOutlined';
import { businessBoundariesApi as api, type BoundaryMaintenanceDraftDto, type BoundaryMaintenanceCommandDto, type ProposedEffectDto } from '../../entities/permission/api/businessBoundaries';
import { readPending, savePending, useCommand, notAccepted, isRecord } from '../../shared/lib/operations';
import { Button } from '../../shared/ui/actions';
import { Choice } from '../../shared/ui/Choice';
import { Heading, Field, SectionHeading, FormColumns } from '../../shared/ui/layout';
import { Badge, Notice } from '../../shared/ui/feedback';
import { Tabs } from '../../shared/ui/Tabs';
import {FieldMutationEditor,validFieldMutation} from '../../entities/permission/ui/FieldMutation';

const effectKinds = { STATE_MUTATION: '状态改变', DATA_DISCLOSURE: '读取业务数据', FILE_CONTENT_DELIVERY: '交付文件内容', OBJECT_CREATION: '创建业务对象', EXTERNAL_DISPATCH: '发送外部消息', RESTRICTED_FUNCTION_INVOCATION: '调用受限功能', CREDENTIAL_ACCESS: '取得凭据' } as const;
type Draft = BoundaryMaintenanceCommandDto & { provenance: string; proposal_id?: string; uncertain?: boolean };
type Section = 'actors' | 'actions' | 'permissions';
const newEffect = (): ProposedEffectDto => ({ item_id: id('peff_'), business_label: '', effect_kind: 'STATE_MUTATION', resource_concept: '', description: '' });

export function InitialRules({ projectId, basis, onBack, onProposal, onError }: { projectId: string; basis: BoundaryMaintenanceDraftDto; onBack: () => void; onProposal: (id: string) => Promise<void>; onError: (error: unknown) => void }) {
    const key = 'jiejian.studio.initial-rules:' + projectId;
    // 旧版本的表单记录只迁入本次文档内存，后续会话缓存仅保留公开提案身份。
    const recovery=readPending<Partial<Draft>>(key,(value):value is Partial<Draft>=>isRecord(value));
    const [draft, setDraft] = useState<Draft>(() => editorDraft<Draft>(key,projectId) ?? (recovery&&Array.isArray(recovery.actors)&&Array.isArray(recovery.actions)&&Array.isArray(recovery.permissions)&&typeof recovery.expected_boundary_state_fingerprint==='string'?recovery as Draft:{ expected_boundary_state_fingerprint: basis.boundary_state_fingerprint, actors: basis.actors, actions: basis.actions, permissions: basis.permissions, provenance: '', uncertain:recovery?.uncertain===true, proposal_id:typeof recovery?.proposal_id==='string'?recovery.proposal_id:undefined }));
    const original=useRef(JSON.stringify(draft)).current;
    const [section, setSection] = useState<Section>('actors');
    const [proposals, setProposals] = useState<string[]>([]);
    const {busy,run}=useCommand(key,onError,error=>notAccepted(error,Boolean(draft.uncertain)));
    const prefix = useId(), panelId = prefix + '-panel';
    useEffect(() => { rememberEditorDraft(key,draft,projectId); savePending(key,{uncertain:Boolean(draft.uncertain),proposal_id:draft.proposal_id}); }, [key, draft]);
    useDraftProtection(!draft.proposal_id&&JSON.stringify(draft)!==original);
    // 草稿可以继续保留，但不能把旧依据下的编辑自动覆盖到已经变化的正式规则上。
    const changed = basis.boundary_state_fingerprint !== draft.expected_boundary_state_fingerprint;
    const disabled = busy || Boolean(draft.uncertain) || changed;
    const edit = (value: Partial<Draft>) => setDraft(current => ({ ...current, ...value }));
    const rolesReady = draft.actors.length > 0 && draft.actors.every(item => item.display_name.trim());
    const actionsReady = draft.actions.length > 0 && draft.actions.every(item => item.display_name.trim() && item.primary_resource_concept.trim() && item.effects.length && item.effects.every(effect => effect.business_label.trim() && effect.resource_concept.trim() && validFieldMutation(effect.field_mutation) && (effect.effect_kind !== 'DATA_DISCLOSURE' || effect.protected_projection?.length)));
    const rulesReady = draft.permissions.length > 0 && draft.permissions.every(item => item.subject_actor_item_id && item.business_action_item_id && item.resource_owner_actor_item_id && item.protected_effect_item_ids.length);
    const valid = rolesReady && actionsReady && rulesReady;
    const missing: Array<{ section: Section; label: string }> = [
        ...(!rolesReady ? [{ section: 'actors' as const, label: '业务角色名称' }] : []),
        ...(!actionsReady ? [{ section: 'actions' as const, label: '业务操作与结果依据' }] : []),
        ...(!rulesReady ? [{ section: 'permissions' as const, label: '访问规则与受保护结果' }] : []),
    ];
    const addRole = (candidate?: string) => edit({ actors: [...draft.actors, { item_id: id('pactr_'), display_name: basis.candidate_options.find(item => item.candidate_id === candidate)?.display_name ?? '', description: '', effective_state: 'ACTIVE', source_candidate_ids: candidate ? [candidate] : [] }] });
    const addAction = (candidate?: string) => edit({ actions: [...draft.actions, { item_id: id('pactn_'), display_name: basis.candidate_options.find(item => item.candidate_id === candidate)?.display_name ?? '', description: '', primary_resource_concept: '', operation_kind: 'CHANGE', state_changing: true, effects: [newEffect()], effective_state: 'ACTIVE', source_candidate_ids: candidate ? [candidate] : [] }] });
    const addRule = () => edit({ permissions: [...draft.permissions, { item_id: id('pperm_'), effective_state: 'ACTIVE', subject_actor_item_id: draft.actors[0]?.item_id ?? '', resource_owner_actor_item_id: draft.actors[0]?.item_id ?? '', business_action_item_id: draft.actions[0]?.item_id ?? '', relation: 'OWNS', expectation: 'ALLOW', protected_effect_item_ids: [] }] });
    const submit = () => void run(async () => {
        // 发出写请求前标记结果未知；只有收到明确拒绝或提案回执，才允许整理下一次提交。
        edit({ uncertain: true });
        try {
            const { proposal_id: _, uncertain: __, provenance, ...command } = draft;
            const result = await api.createMaintenanceProposal(projectId, {...command,...(provenance.trim() ? {provenance:provenance.trim()} : {})});
            edit({ proposal_id: result.proposal.proposal_id, uncertain: false });
            await onProposal(result.proposal.proposal_id);
        } catch (error) {
            if (notAccepted(error,Boolean(draft.uncertain))) edit({ uncertain: false });
            throw error;
        }
    },'write');
    return <>
        <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true" />} onClick={onBack}>全部权限规则</Button></div>
        <Heading title="编写权限要求"><p>先确认谁在操作，再定义操作会产生的业务结果，最后约定谁可以对哪些数据完成这些操作。各部分可以随时返回修改，整理完成后统一审阅批准。</p></Heading>
        {changed && <Notice tone="caution">正式规则已变化，草稿保留。请返回核对当前规则后再整理。</Notice>}
        <div className="jj-rule-authoring" data-preview={draft.permissions.length>0}>
            <div className="jj-rule-authoring-editor">
                <Tabs label="权限编写分区" value={section} items={[
                    { value: 'actors', label: '业务角色 ' + draft.actors.length },
                    { value: 'actions', label: '操作与结果 ' + draft.actions.length },
                    { value: 'permissions', label: '访问规则 ' + draft.permissions.length },
                ]} onValueChange={value => setSection(value as Section)} idPrefix={prefix} panelId={panelId} />
                <div role="tabpanel" id={panelId} aria-labelledby={prefix + '-' + section} className="jj-rule-authoring-panel" key={section}>
                    <fieldset className="jj-initial-rules" disabled={disabled}>
                        {section === 'actors' && <section className="jj-initial-definitions">
                            <SectionHeading title="业务角色" actions={<Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={() => addRole()}>添加角色</Button>}/>
                            {basis.candidate_options.some(item => item.candidate_kind === 'ROLE') && <div className="jj-initial-candidates"><Field label="从已识别角色添加"><Choice value="" placeholder="选择源码中的角色" onValueChange={value => addRole(value)}>{basis.candidate_options.filter(item => item.candidate_kind === 'ROLE' && !draft.actors.some(actor => actor.source_candidate_ids?.includes(item.candidate_id))).map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.display_name}</option>)}</Choice></Field></div>}
                            {!draft.actors.length && <p className="jj-initial-empty">添加使用这项业务的角色，例如负责人、成员或访客。</p>}
                            {draft.actors.map((role, index) => <article className="jj-initial-role" key={role.item_id}>
                                <div className="jj-initial-role-fields">
                                    <Field label="角色名称"><input maxLength={128} value={role.display_name} onChange={event => edit({ actors: draft.actors.map((item, i) => i === index ? { ...item, display_name: event.target.value } : item) })} /></Field>
                                    <details className="jj-initial-extra"><summary>说明与源码对应（选填）</summary><div><Field label="对应源码角色"><Choice disabled={disabled} value={role.source_candidate_ids?.[0] ?? ''} onValueChange={value => edit({ actors: draft.actors.map((item, i) => i === index ? { ...item, source_candidate_ids: value ? [value] : [] } : item) })}><option value="">暂未对应</option>{basis.candidate_options.filter(item => item.candidate_kind === 'ROLE').map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.display_name}</option>)}</Choice></Field>
                                    <Field label="角色职责（选填）"><textarea rows={2} maxLength={1024} value={role.description} onChange={event => edit({ actors: draft.actors.map((item, i) => i === index ? { ...item, description: event.target.value } : item) })} /></Field></div></details>
                                </div>
                                <Button kind="quiet" aria-label={'移除角色 ' + (role.display_name || index + 1)} disabled={draft.permissions.some(item => item.subject_actor_item_id === role.item_id || item.resource_owner_actor_item_id === role.item_id)} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => edit({ actors: draft.actors.filter(item => item.item_id !== role.item_id) })} />
                            </article>)}
                        </section>}
                        {section === 'actions' && <section className="jj-initial-definitions" aria-label="业务操作">
                            {!draft.actions.length&&<SectionHeading title="业务操作" actions={<Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={() => addAction()}>添加操作</Button>}/>}
                            {basis.candidate_options.some(item => item.candidate_kind === 'ACTION') && <div className="jj-initial-candidates"><Field label="从已识别操作添加"><Choice value="" placeholder="选择源码中的操作" onValueChange={value => addAction(value)}>{basis.candidate_options.filter(item => item.candidate_kind === 'ACTION' && !draft.actions.some(action => action.source_candidate_ids?.includes(item.candidate_id))).map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.display_name}</option>)}</Choice></Field></div>}
                            {!draft.actions.length && <p className="jj-initial-empty">添加需要检查权限的业务操作，并说明怎样确认实际结果。</p>}
                            {draft.actions.map((action, index) => {
                                const update = (value: Partial<typeof action>) => edit({ actions: draft.actions.map((item, i) => i === index ? { ...item, ...value } : item) });
                                return <article className="jj-initial-action" key={action.item_id} aria-label={'业务操作 '+(index+1)}>
                                    <FormColumns><section className="jj-initial-operation">
                                        <SectionHeading title={index===0?'业务操作':'业务操作 '+(index+1)} level={index===0?2:3} actions={index===0?<Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={() => addAction()}>添加操作</Button>:undefined}/>
                                    <div className="jj-field-stack">
                                        <Field label="操作名称"><input maxLength={256} value={action.display_name} onChange={event => update({ display_name: event.target.value })} /></Field>
                                        <Field label="操作的资源"><input maxLength={128} value={action.primary_resource_concept} onChange={event => update({ primary_resource_concept: event.target.value, effects: action.effects.map(effect => !effect.resource_concept || effect.resource_concept === action.primary_resource_concept ? { ...effect, resource_concept: event.target.value } : effect) })} /></Field>
                                        <Field label="操作类型"><Choice disabled={disabled} value={action.operation_kind} onValueChange={value => update({ operation_kind: value as typeof action.operation_kind })}>{Object.entries({ READ: '读取', CHANGE: '修改', DELETE: '删除', EXPORT: '导出', ADMIN: '管理', CUSTOM: '其他' }).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Choice></Field>
                                        {basis.candidate_options.some(item=>item.candidate_kind==='ACTION')&&<Field label="对应源码操作"><Choice disabled={disabled} value={action.source_candidate_ids?.[0] ?? ''} onValueChange={value => update({ source_candidate_ids: value ? [value] : [] })}><option value="">暂未对应</option>{basis.candidate_options.filter(item => item.candidate_kind === 'ACTION').map(item => <option key={item.candidate_id} value={item.candidate_id}>{item.display_name}</option>)}</Choice></Field>}
                                        <Field label="操作说明（选填）"><textarea rows={2} maxLength={1024} value={action.description} onChange={event => update({ description: event.target.value })} /></Field>
                                        <label className="jj-checkbox"><input type="checkbox" checked={action.state_changing} onChange={event => update({ state_changing: event.target.checked })} /><span>此操作会改变业务数据</span></label>
                                    </div></section>
                                    <section className="jj-initial-effects" aria-label={'业务操作 '+(index+1)+'的业务结果'}>
                                        <SectionHeading title="业务结果" level={3} actions={<Button kind="quiet" icon={<PlusOutlined aria-hidden="true" />} onClick={() => update({ effects: [...action.effects, {...newEffect(),resource_concept:action.primary_resource_concept}] })}>添加结果</Button>}/>
                                        {action.effects.map((effect, effectIndex) => {
                                            const updateEffect = (value: Partial<ProposedEffectDto>) => update({ effects: action.effects.map((item, i) => i === effectIndex ? { ...item, ...value } : item) });
                                            return <section key={effect.item_id}>
                                                <div className="jj-field-stack">
                                                    <Field label="结果名称"><input maxLength={256} value={effect.business_label} onChange={event => updateEffect({ business_label: event.target.value })} /></Field>
                                                    <Field label="结果类型"><Choice disabled={disabled} value={effect.effect_kind} onValueChange={value => {
                                                        const kind=value as ProposedEffectDto['effect_kind'];
                                                        const classification=action.effects.length===1 ? ({STATE_MUTATION:{operation_kind:'CHANGE',state_changing:true},OBJECT_CREATION:{operation_kind:'CHANGE',state_changing:true},DATA_DISCLOSURE:{operation_kind:'READ',state_changing:false},FILE_CONTENT_DELIVERY:{operation_kind:'EXPORT',state_changing:false}} as const)[kind as 'STATE_MUTATION'|'OBJECT_CREATION'|'DATA_DISCLOSURE'|'FILE_CONTENT_DELIVERY'] : undefined;
                                                        update({...classification,effects:action.effects.map((item,i)=>i===effectIndex?{...item,effect_kind:kind,protected_projection:[],field_mutation:null}:item)});
                                                    }}>{Object.entries(effectKinds).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Choice></Field>
                                                    <Field label="结果涉及的资源"><input maxLength={128} value={effect.resource_concept} onChange={event => updateEffect({ resource_concept: event.target.value })} /></Field>
                                                    {!effect.field_mutation&&<Field label="预期业务状态（选填）"><input maxLength={512} value={effect.expected_state ?? ''} onChange={event => updateEffect({ expected_state: event.target.value || null })} /></Field>}
                                                    <details className="jj-initial-extra"><summary>补充结果说明（选填）</summary><div><Field label="结果说明（选填）"><textarea rows={2} maxLength={1024} value={effect.description} onChange={event => updateEffect({ description: event.target.value })} /></Field></div></details>
                                                    {effect.effect_kind === 'DATA_DISCLOSURE' && <Field label="受保护的业务字段" hint="填写真实字段名，以逗号分隔。"><input value={effect.protected_projection?.join(', ') ?? ''} onChange={event => updateEffect({ protected_projection: event.target.value.split(',').map(value => value.trim()).filter(Boolean) })} /></Field>}
                                                    {effect.effect_kind==='STATE_MUTATION'&&<FieldMutationEditor value={effect.field_mutation} disabled={disabled} onChange={field_mutation=>updateEffect({field_mutation,expected_state:null})}/>}
                                                </div>
                                                {action.effects.length > 1 && <Button kind="quiet" disabled={draft.permissions.some(item => item.protected_effect_item_ids.includes(effect.item_id))} onClick={() => update({ effects: action.effects.filter(item => item.item_id !== effect.item_id) })}>移除此结果</Button>}
                                            </section>;
                                        })}
                                    </section></FormColumns>
                                    <div className="jj-initial-entity-actions"><Button kind="quiet" disabled={draft.permissions.some(item => item.business_action_item_id === action.item_id)} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => edit({ actions: draft.actions.filter(item => item.item_id !== action.item_id) })}>移除此操作</Button></div>
                                </article>;
                            })}
                        </section>}
                        {section === 'permissions' && <section className="jj-initial-definitions">
                            <SectionHeading title="访问规则" actions={<Button kind="quiet" disabled={!draft.actors.length || !draft.actions.length} icon={<PlusOutlined aria-hidden="true" />} onClick={addRule}>添加规则</Button>}/>
                            {!draft.permissions.length && <p className="jj-initial-empty">角色和操作填写后，即可添加允许或禁止的访问要求。</p>}
                            {draft.permissions.map((rule, index) => {
                                const update = (value: Partial<typeof rule>) => edit({ permissions: draft.permissions.map((item, i) => i === index ? { ...item, ...value } : item) });
                                const action = draft.actions.find(item => item.item_id === rule.business_action_item_id);
                                return <article className="jj-initial-permission" key={rule.item_id}>
                                    <header><Badge>{rule.expectation === 'ALLOW' ? '允许访问' : '禁止访问'}</Badge><Button kind="quiet" aria-label={'移除规则 ' + (index + 1)} icon={<DeleteOutlined aria-hidden="true" />} onClick={() => edit({ permissions: draft.permissions.filter(item => item.item_id !== rule.item_id) })} /></header>
                                    <div className="jj-initial-permission-fields">
                                        <Field label="操作角色"><Choice disabled={disabled} value={rule.subject_actor_item_id} onValueChange={value => update({ subject_actor_item_id: value, resource_owner_actor_item_id: rule.relation === 'OTHER_ROLE' ? rule.resource_owner_actor_item_id : value })}>{draft.actors.map(item => <option key={item.item_id} value={item.item_id}>{item.display_name || '未命名角色'}</option>)}</Choice></Field>
                                        <Field label="访问要求"><Choice disabled={disabled} value={rule.expectation} onValueChange={value => update({ expectation: value as 'ALLOW' | 'DENY' })}><option value="ALLOW">允许</option><option value="DENY">禁止</option></Choice></Field>
                                        <Field label="业务操作"><Choice disabled={disabled} value={rule.business_action_item_id} onValueChange={value => update({ business_action_item_id: value, protected_effect_item_ids: [] })}>{draft.actions.map(item => <option key={item.item_id} value={item.item_id}>{item.display_name || '未命名操作'}</option>)}</Choice></Field>
                                        <Field label="资源范围"><Choice disabled={disabled} value={rule.relation === 'OTHER_ROLE' ? rule.resource_owner_actor_item_id : rule.relation} onValueChange={value => update(value === 'OWNS' || value === 'SAME_ROLE_OTHER_ACCOUNT' ? { relation: value, resource_owner_actor_item_id: rule.subject_actor_item_id } : { relation: 'OTHER_ROLE', resource_owner_actor_item_id: value })}><option value="OWNS" disabled={rule.conditions?.principal === "ANONYMOUS" || rule.conditions?.tenant === "DIFFERENT"}>自己的资源</option><option value="SAME_ROLE_OTHER_ACCOUNT" disabled={rule.conditions?.principal === "ANONYMOUS"}>同角色其他账号的资源</option>{draft.actors.filter(item => item.item_id !== rule.subject_actor_item_id).map(item => <option key={item.item_id} value={item.item_id}>{item.display_name || '其他角色'}的资源</option>)}</Choice></Field>
                                    </div>
                                    <RuleConditionsEditor value={rule.conditions} relation={rule.relation} disabled={disabled} onChange={conditions => update({conditions})}/><fieldset className="jj-initial-protected"><legend>{rule.expectation === 'ALLOW' ? '应当产生的结果' : '不得产生的结果'}</legend>{action?.effects.map(effect => <label className="jj-checkbox" key={effect.item_id}><input type="checkbox" checked={rule.protected_effect_item_ids.includes(effect.item_id)} onChange={event => update({ protected_effect_item_ids: event.target.checked ? [...rule.protected_effect_item_ids, effect.item_id] : rule.protected_effect_item_ids.filter(value => value !== effect.item_id) })} /><span>{effect.business_label || '尚未填写的业务结果'}</span></label>)}</fieldset>
                                </article>;
                            })}
                        </section>}
                    </fieldset>
                    {section !== 'permissions' && <footer className="jj-initial-next"><Button onClick={() => setSection(section === 'actors' ? 'actions' : 'permissions')}>{section === 'actors' ? '继续定义操作与结果' : '继续编写访问规则'}<ArrowRightOutlined aria-hidden="true" /></Button></footer>}
                </div>
            </div>
            {draft.permissions.length>0&&<aside className="jj-initial-preview" data-section={section} aria-label="权限草稿预览">
                <header><span className="jj-initial-preview-symbol"><SafetyOutlined aria-hidden="true" /></span><div className="jj-object-line"><h2 className="jj-title-group">权限预览</h2><Badge>尚未生效</Badge></div></header>
                <div className="jj-initial-preview-rules">{draft.permissions.map((rule, index) => {
                    const actor = draft.actors.find(item => item.item_id === rule.subject_actor_item_id), owner = draft.actors.find(item => item.item_id === rule.resource_owner_actor_item_id), action = draft.actions.find(item => item.item_id === rule.business_action_item_id);
                    const relation = rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? '同角色其他账号的资源' : (owner?.display_name || '指定角色') + '的资源';
                    return <Button kind="quiet" className="jj-initial-preview-rule" key={rule.item_id} onClick={() => setSection('permissions')} aria-label={'编辑规则 ' + (index + 1)}>
                        {rule.expectation === 'ALLOW' ? <CheckCircleOutlined aria-hidden="true" /> : <StopOutlined aria-hidden="true" />}
                        <span><strong>{rule.conditions?.principal === 'ANONYMOUS' ? '未登录访客' : actor?.display_name || '未命名角色'}{rule.expectation === 'ALLOW' ? '可以' : '不得'}{action?.display_name || '执行操作'}</strong><small>{relation}</small>{conditionLabels(rule.conditions).length > 0 && <small>{conditionLabels(rule.conditions).join("，")}</small>}{action?.effects.filter(effect => rule.protected_effect_item_ids.includes(effect.item_id)).map(effect => <span className="jj-initial-preview-effect" key={effect.item_id}>{effect.business_label || '未命名结果'}</span>)}</span>
                    </Button>;
                })}</div>
                {section === 'permissions' && <details className="jj-initial-provenance"><summary>补充规则依据（选填）</summary><Field label="权限要求的依据"><textarea disabled={disabled} rows={3} maxLength={512} value={draft.provenance} onChange={event => edit({ provenance: event.target.value })} /></Field></details>}
                <div className="jj-initial-submit">
                    {!!missing.length && <details className="jj-initial-missing"><summary>仍需填写 {missing.length} 项</summary><div>{missing.map(item => <Button kind="quiet" key={item.label} onClick={() => setSection(item.section)}>{item.label}<ArrowRightOutlined aria-hidden="true" /></Button>)}</div></details>}
                    <p>生成后需审阅批准，规则才会生效。</p>
                    <Button kind="primary" busy={busy} disabled={!valid || disabled} onClick={submit}>生成完整提案<ArrowRightOutlined aria-hidden="true" /></Button>
                </div>
            </aside>}
        </div>
        {draft.uncertain && <Notice tone="caution">提案结果尚未确认，草稿已保留。<Button busy={busy} onClick={() => void run(async () => { const value = await api.proposals(projectId, true); setProposals(value.proposals.map(item => item.proposal.proposal_id)); })} busyLabel="正在查询">查询已接收的提案</Button></Notice>}
        {(draft.proposal_id ? [draft.proposal_id] : proposals).map((value, index) => <Button key={value} onClick={() => void run(() => onProposal(value))}>审阅提案{proposals.length > 1 ? ' ' + (index + 1) : ''}</Button>)}
    </>;
}
