import {RuleConditionFields, conditionLabels} from '../../entities/permission/ui/RuleConditions';
import type {PermissionConditions} from '../../entities/permission/api/businessBoundaries';
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { InitialRules } from './InitialRules';
import { Fragment, useEffect, useRef, useState } from 'react';
import { businessBoundariesApi as api } from '../../entities/permission/api/businessBoundaries';
import {notAccepted} from '../../shared/lib/operations';
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection} from '../../entities/runtime/model/handoff';
import { assertProject } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { useRead } from '../../shared/lib/useRead';
import { Choice } from "../../shared/ui/Choice";
import { Badge, Empty, ErrorNote, Notice } from "../../shared/ui/feedback";
import { Button } from "../../shared/ui/actions";
import { Heading } from "../../shared/ui/layout";
export function RuleEditor({ projectId, onBack, onProposal, onError }: {
    projectId: string;
    onBack: () => void;
    onProposal: (id: string) => Promise<void>;
    onError: (error: unknown) => void;
}) {
    const state = useRead('rule-maintenance:' + projectId, async () => { const value = await api.maintenanceDraft(projectId); assertProject(value.project_id, projectId); return value; });
    const draftKey='rule-editor:'+projectId;
    const saved=useRef(editorDraft<{changes:Record<string,'ALLOW'|'DENY'>;reason:string;conditions:Record<string,PermissionConditions|null>;expanded:string|null;basis?:string}>(draftKey,projectId)).current;
    const basis=useRef(saved?.basis);
    const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
    const [changes, setChanges] = useState<Record<string, 'ALLOW' | 'DENY'>>(saved?.changes??{}), [reason, setReason] = useState(saved?.reason??''), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(Boolean(sessionStorage.getItem('jiejian.studio.maintenance:' + projectId))), [proposals, setProposals] = useState<string[]>([]), lock = useRef(false);
    const [conditionChanges, setConditionChanges] = useState<Record<string,PermissionConditions | null>>(saved?.conditions??{});
    const [expandedRule, setExpandedRule] = useState<string | null>(saved?.expanded??null);
    const dirty=!proposals.length&&Boolean(reason||Object.keys(changes).length||Object.keys(conditionChanges).length);
    useDraftProtection(dirty);
    useEffect(()=>{if(state.data&&!basis.current)basis.current=state.data.boundary_state_fingerprint;if(dirty)rememberEditorDraft(draftKey,{changes,reason,conditions:conditionChanges,expanded:expandedRule,basis:basis.current},projectId)},[changes,reason,conditionChanges,expandedRule,state.data?.boundary_state_fingerprint]);
    if (state.loading)
        return <PageSkeleton view="/permissions" title="编辑权限要求"/>;
    if (!state.data)
        return <ErrorNote error={state.error}/>;
    const value = state.data;
    if (!value.permissions.length) return <InitialRules projectId={projectId} basis={value} onBack={onBack} onProposal={onProposal} onError={onError}/>;
    const conflict=Boolean(basis.current&&basis.current!==value.boundary_state_fingerprint);
    const changedRules = value.permissions.filter(item => (changes[item.item_id] && changes[item.item_id] !== item.expectation) || (item.item_id in conditionChanges && JSON.stringify(conditionChanges[item.item_id]) !== JSON.stringify(item.conditions ?? null)));
    const changed = changedRules.length > 0;
    const act = async (callback: () => Promise<unknown>) => { if (lock.current)
        return; lock.current = true; setBusy(true); try {
        await callback();
    }
    catch (error) {
        onError(error);
    }
    finally {
        lock.current = false;
        setBusy(false);
    } };
    return <><div className="jj-back-link"><Button kind="quiet" disabled={busy} onClick={onBack}>全部权限规则</Button></div>
    <Heading title="调整访问要求"/>
    <section className="jj-panel jj-rule-editor">
      {state.error&&<Notice tone="caution">权限要求更新失败，编辑内容继续保留。请使用右上角刷新后再生成提案。</Notice>}
      {conflict&&<Notice tone="caution">正式规则已变化。编辑内容已保留，请对照当前要求与调整值重新核对。<Button kind="quiet" disabled={busy||uncertain||Object.keys(changes).some(id=>!value.permissions.some(item=>item.item_id===id))||Object.keys(conditionChanges).some(id=>!value.permissions.some(item=>item.item_id===id))} onClick={()=>{basis.current=value.boundary_state_fingerprint;setChanges(current=>({...current}))}}>已核对当前规则，继续编辑</Button></Notice>}
      <header className="jj-rule-editor-heading"><h2>当前生效的访问规则</h2><span className="jj-small jj-muted">{value.permissions.filter(item => item.effective_state === 'ACTIVE').length} 条</span></header>
      <div className="jj-scroll-table"><table data-density="compact" className="jj-content-table jj-rule-editor-table">
        <colgroup><col className="jj-rule-object-column"/><col className="jj-rule-condition-column"/><col className="jj-rule-current-column"/><col className="jj-rule-edit-column"/></colgroup>
        <thead><tr><th scope="col">访问规则</th><th scope="col">适用条件</th><th scope="col" className="jj-table-state">当前要求</th><th scope="col" className="jj-table-state">调整后的要求</th></tr></thead>
        <tbody>{value.permissions.filter(item => item.effective_state === 'ACTIVE').map(item => {
          const actor = value.actors.find(actor => actor.item_id === item.subject_actor_item_id);
          const owner = value.actors.find(actor => actor.item_id === item.resource_owner_actor_item_id);
          const action = value.actions.find(action => action.item_id === item.business_action_item_id);
          const scope = item.relation === 'OWNS' ? '自己的资源' : item.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${text(owner?.display_name ?? '同角色')}账号的资源` : `${text(owner?.display_name ?? '其他角色')}的资源`;
          const title = text(actor?.display_name ?? '当前角色') + text(action?.display_name ?? '当前业务操作');
          const conditions = item.item_id in conditionChanges ? conditionChanges[item.item_id] : item.conditions;
          const expanded = expandedRule === item.item_id;
          const editorId = 'rule-conditions-' + item.item_id;
          return <Fragment key={item.item_id}><tr>
            <td><h3>{title}</h3><p className="jj-small jj-muted">{scope}</p></td>
            <td><div className="jj-rule-condition-summary"><span className="jj-small jj-muted">{conditionLabels(conditions).join('，') || '已登录账号'}</span><Button kind="quiet" aria-expanded={expanded} aria-controls={editorId} aria-label={`${expanded ? '收起' : '编辑'}${title}对${scope}的适用条件`} onClick={() => setExpandedRule(expanded ? null : item.item_id)}>{expanded ? '收起条件' : '编辑条件'}</Button></div></td>
            <td className="jj-table-state"><Badge>{item.expectation === 'ALLOW' ? '允许' : '禁止'}</Badge></td>
            <td className="jj-table-state"><Choice align="center" className="jj-table-choice" aria-label={`调整${actor?.display_name}${action?.display_name}对${scope}的权限`} value={changes[item.item_id] ?? item.expectation} disabled={busy || uncertain} onValueChange={value => setChanges(current => ({ ...current, [item.item_id]: value as 'ALLOW' | 'DENY' }))}><option value="ALLOW">允许</option><option value="DENY">禁止</option></Choice></td>
          </tr>{expanded && <tr className="jj-rule-condition-row"><td colSpan={4}>
            <section id={editorId} className="jj-rule-condition-editor" aria-label={`${title}对${scope}的适用条件`}>
              <h3>适用条件</h3>
              <RuleConditionFields value={conditions} relation={item.relation} disabled={busy || uncertain} onChange={conditions => setConditionChanges(current => ({...current, [item.item_id]:conditions}))}/>
            </section>
          </td></tr>}</Fragment>;
        })}</tbody>
      </table></div>{!value.permissions.length && <Empty title="当前没有可调整的访问规则"/>}{changed&&<p className="jj-small jj-muted">本次将调整 {changedRules.length} 条规则的要求或适用条件；保存后仍需审阅批准。</p>}<label className="jj-field jj-rule-editor-reason"><span>变更理由</span><textarea value={reason} disabled={busy || uncertain} onChange={event => setReason(event.target.value)} placeholder="说明访问要求发生了什么变化"/></label><div className="jj-task-actions jj-form-actions">{dirty&&<Button kind="quiet" disabled={busy||uncertain} onClick={()=>{rememberEditorDraft(draftKey,undefined);basis.current=value.boundary_state_fingerprint;setChanges({});setConditionChanges({});setReason('');setExpandedRule(null)}}>放弃本页编辑</Button>}<Button disabled={busy} onClick={onBack}>返回</Button><Button kind="primary" busy={busy} disabled={!changed || !reason.trim() || uncertain || conflict || proposals.length>0 || Boolean(state.error)} onClick={() => void act(async () => { const key = 'jiejian.studio.maintenance:' + projectId; sessionStorage.setItem(key, 'pending'); const submitted=editorDraftGeneration(draftKey,projectId); let confirmed=false; try {
        const proposal = await api.createMaintenanceProposal(projectId, { expected_boundary_state_fingerprint: value.boundary_state_fingerprint, actors: value.actors, actions: value.actions, permissions: value.permissions.map(item => ({ ...item, expectation: changes[item.item_id] ?? item.expectation, ...(item.item_id in conditionChanges ? {conditions:conditionChanges[item.item_id]} : {}) })), provenance: reason.trim() });
        assertProject(proposal.proposal.project_id, projectId);
        sessionStorage.removeItem(key);confirmed=true;setProposals([proposal.proposal.proposal_id]);
        clearSubmittedDraft(draftKey,projectId,submitted);
        if(alive.current)await onProposal(proposal.proposal.proposal_id);
    }
    catch (error) {
        if(confirmed)throw new Error('权限提案已保存，详情尚未读取。请从下方重新打开已保存的提案。');
        if (notAccepted(error,uncertain))
            sessionStorage.removeItem(key);
        else
            setUncertain(true);
        throw error;
    } })}>生成待审变更</Button></div>{uncertain && <Notice tone="caution">生成结果尚未确认，请先读取已经保存的提案。<Button busy={busy} onClick={() => void act(async () => { const result = await api.proposals(projectId, true); assertProject(result.project_id, projectId); result.proposals.forEach(item => assertProject(item.proposal.project_id, projectId)); setProposals(result.proposals.map(item => item.proposal.proposal_id)); })}>读取待审提案</Button></Notice>}{proposals.map((id, index) => <Button key={id} onClick={() => void act(() => onProposal(id))}>审阅提案 {index + 1}</Button>)}</section></>;
}
