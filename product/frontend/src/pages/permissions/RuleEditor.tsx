import {DraftValidationPreview} from '../../entities/permission/ui/DraftValidationPreview';
import {RuleConditionFields, conditionLabels} from '../../entities/permission/ui/RuleConditions';
import type {PermissionConditions} from '../../entities/permission/api/businessBoundaries';
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { InitialRules } from './InitialRules';
import {ImplementationMappings,implementationRows,type ImplementationEdits} from './ImplementationMappings';
import { useEffect, useRef, useState } from 'react';
import { businessBoundariesApi as api } from '../../entities/permission/api/businessBoundaries';
import {notAccepted} from '../../shared/lib/operations';
import {editorDraft,rememberEditorDraft,editorDraftGeneration,clearSubmittedDraft,useDraftProtection} from '../../entities/runtime/model/handoff';
import { assertProject } from '../../shared/model/page';
import { text } from '../../shared/lib/format';
import { useRead } from '../../shared/lib/useRead';
import { Choice } from "../../shared/ui/Choice";
import { Badge, Empty, ErrorNote, Notice } from "../../shared/ui/feedback";
import { Button } from "../../shared/ui/actions";
import { TaskActions, SectionHeading, Field, ObjectIdentity } from "../../shared/ui/layout";
import {TaskSurface} from '../../shared/ui/TaskSurface';
import {IndexSelection} from '../../shared/ui/IndexSelection';
import {ObjectTable} from '../../shared/ui/ObjectTable';
import CloseOutlined from '@ant-design/icons/CloseOutlined';
export function RuleEditor({ projectId, onBack, onProposal, onError }: {
    projectId: string;
    onBack: () => void;
    onProposal: (id: string) => Promise<void>;
    onError: (error: unknown) => void;
}) {
    const state = useRead('rule-maintenance:' + projectId, async () => { const value = await api.maintenanceDraft(projectId); assertProject(value.project_id, projectId); return value; });
    const draftKey='rule-editor:'+projectId;
    const saved=useRef(editorDraft<{changes:Record<string,'ALLOW'|'DENY'>;reason:string;conditions:Record<string,PermissionConditions|null>;sources?:ImplementationEdits;expanded:string|null;basis?:string}>(draftKey,projectId)).current;
    const basis=useRef(saved?.basis);
    const alive=useRef(true);useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);
    const [changes, setChanges] = useState<Record<string, 'ALLOW' | 'DENY'>>(saved?.changes??{}), [reason, setReason] = useState(saved?.reason??''), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(Boolean(sessionStorage.getItem('jiejian.studio.maintenance:' + projectId))), [proposals, setProposals] = useState<string[]>([]), lock = useRef(false);
    const [conditionChanges, setConditionChanges] = useState<Record<string,PermissionConditions | null>>(saved?.conditions??{});
    const [expandedRule, setExpandedRule] = useState<string | null>(saved?.expanded??null);
    const editorRoot=useRef<HTMLElement>(null),lastRule=useRef(saved?.expanded??'');
    const [sourceChanges,setSourceChanges]=useState<ImplementationEdits>(saved?.sources??{});
    const dirty=!proposals.length&&Boolean(reason||Object.keys(changes).length||Object.keys(conditionChanges).length||Object.keys(sourceChanges).length);
    useDraftProtection(dirty);
    useEffect(()=>{if(state.data&&!basis.current)basis.current=state.data.boundary_state_fingerprint;if(dirty)rememberEditorDraft(draftKey,{changes,reason,conditions:conditionChanges,sources:sourceChanges,expanded:expandedRule,basis:basis.current},projectId)},[changes,reason,conditionChanges,sourceChanges,expandedRule,state.data?.boundary_state_fingerprint]);
    if (state.loading)
        return <PageSkeleton view="/permissions" title="编辑权限要求"/>;
    if (!state.data)
        return <ErrorNote error={state.error} onRetry={state.reload} retryLabel="重新读取权限要求"/>;
    const value = state.data;
    if (!value.permissions.length) return <InitialRules projectId={projectId} basis={value} onBack={onBack} onProposal={onProposal} onError={onError}/>;
    // 目录只选择编辑对象；每条规则的未提交值仍由整份草稿保存。
    const records=value.permissions.filter(item=>item.effective_state==='ACTIVE').map(item=>{
      const actor=value.actors.find(actor=>actor.item_id===item.subject_actor_item_id),owner=value.actors.find(actor=>actor.item_id===item.resource_owner_actor_item_id),action=value.actions.find(action=>action.item_id===item.business_action_item_id);
      const scope=item.relation==='OWNS'?'自己的资源':item.relation==='SAME_ROLE_OTHER_ACCOUNT'?`其他${text(owner?.display_name??'同角色')}账号的资源`:`${text(owner?.display_name??'其他角色')}的资源`;
      return {item,actor,action,scope,title:text(actor?.display_name??'当前角色')+text(action?.display_name??'当前业务操作'),conditions:item.item_id in conditionChanges?conditionChanges[item.item_id]:item.conditions,conditionChanged:item.item_id in conditionChanges&&JSON.stringify(conditionChanges[item.item_id])!==JSON.stringify(item.conditions??null),effects:action?.effects?.filter(effect=>item.protected_effect_item_ids?.includes(effect.item_id)).map(effect=>effect.business_label)??[]};
    });
    const selected=records.find(row=>row.item.item_id===expandedRule)??records[0],editingDisabled=busy||uncertain||proposals.length>0;
    const closeRule=()=>{lastRule.current=selected.item.item_id;setExpandedRule(null);requestAnimationFrame(()=>Array.from(editorRoot.current?.querySelectorAll<HTMLButtonElement>('[data-rule-id]')??[]).find(node=>node.dataset.ruleId===lastRule.current)?.focus({preventScroll:true}))};
    const conflict=Boolean(basis.current&&basis.current!==value.boundary_state_fingerprint);
    const changedRules = value.permissions.filter(item => (changes[item.item_id] && changes[item.item_id] !== item.expectation) || (item.item_id in conditionChanges && JSON.stringify(conditionChanges[item.item_id]) !== JSON.stringify(item.conditions ?? null)));
    const mappingRows=implementationRows(value);
    const changedMappings=mappingRows.filter(item=>item.item_id in sourceChanges&&(JSON.stringify([...(item.source_candidate_ids??[])].sort())!==JSON.stringify([...sourceChanges[item.item_id]].sort())||Boolean(item.inspection&&item.inspection.status!=='CURRENT')));
    const changed = changedRules.length > 0||changedMappings.length>0;
    const unknownMapping=Object.keys(sourceChanges).some(id=>!mappingRows.some(item=>item.item_id===id));
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
    return <TaskSurface width="wide" title="调整访问要求" description="对照当前规则调整要求或适用条件，生成提案后统一审阅批准。" onBack={onBack} backLabel="全部权限规则" backDisabled={busy}>
    <section ref={editorRoot} className="jj-rule-editor">
      {state.error&&<Notice tone="caution">权限要求更新失败，编辑内容继续保留。请使用右上角刷新后再生成提案。</Notice>}
      {conflict&&<Notice tone="caution">正式规则已变化。编辑内容已保留，请对照当前要求与调整值重新核对。<Button kind="quiet" disabled={busy||uncertain||unknownMapping||Object.keys(changes).some(id=>!value.permissions.some(item=>item.item_id===id))||Object.keys(conditionChanges).some(id=>!value.permissions.some(item=>item.item_id===id))} onClick={()=>{basis.current=value.boundary_state_fingerprint;setChanges(current=>({...current}))}}>已核对当前规则，继续编辑</Button></Notice>}
      <SectionHeading title="当前生效的访问规则" meta={value.permissions.filter(item => item.effective_state === 'ACTIVE').length + ' 条'}/>
      {!expandedRule?<ObjectTable appearance="contained" selection={lastRule.current} className="jj-rule-edit-overview"><thead><tr><th>访问规则</th><th>适用条件</th><th className="jj-table-state">当前要求</th><th className="jj-table-state">调整后的要求</th></tr></thead><tbody>{records.map(row=><tr key={row.item.item_id} data-selected={row.item.item_id===lastRule.current}><th scope="row"><button className="jj-object-select" data-rule-id={row.item.item_id} aria-label={`编辑${row.title}对${row.scope}的访问要求`} onClick={()=>setExpandedRule(row.item.item_id)}><strong>{row.title}</strong><small>{row.scope}</small></button></th><td data-label="适用条件"><span>{conditionLabels(row.conditions).join('，')||'已登录账号'}</span>{row.conditionChanged&&<small className="jj-table-secondary">条件已调整</small>}</td><td className="jj-table-state" data-label="当前要求"><Badge>{row.item.expectation==='ALLOW'?'允许':'禁止'}</Badge></td><td className="jj-table-state" data-label="调整后的要求"><Choice measure="compact" align="center" className="jj-table-choice" aria-label={`调整${row.actor?.display_name}${row.action?.display_name}对${row.scope}的权限`} value={changes[row.item.item_id]??row.item.expectation} disabled={editingDisabled} onValueChange={value=>setChanges(current=>({...current,[row.item.item_id]:value as 'ALLOW'|'DENY'}))}><option value="ALLOW">允许</option><option value="DENY">禁止</option></Choice></td></tr>)}</tbody></ObjectTable>:selected?<div className="jj-rule-edit-workspace">
        <IndexSelection className="jj-rule-edit-index" identity={selected.item.item_id} label="选择要调整的规则">
          {records.map(row=><button key={row.item.item_id} className="jj-index-item" aria-label={`编辑${row.title}对${row.scope}的访问要求`} aria-pressed={row===selected} aria-controls="selected-rule-editor" disabled={editingDisabled} onClick={()=>setExpandedRule(row.item.item_id)}><ObjectIdentity name={<strong>{row.title}</strong>} status={<Badge>{row.item.expectation==='ALLOW'?'允许':'禁止'}{changes[row.item.item_id]&&changes[row.item.item_id]!==row.item.expectation?` → ${changes[row.item.item_id]==='ALLOW'?'允许':'禁止'}`:''}</Badge>}/><small>{row.scope}{row.conditionChanged?' · 条件已调整':''}</small></button>)}
        </IndexSelection>
        <div className="jj-rule-edit-selector"><Field measure="standard" label="选择要调整的规则"><Choice value={selected.item.item_id} disabled={editingDisabled} onValueChange={setExpandedRule}>{records.map(row=><option key={row.item.item_id} value={row.item.item_id}>{row.title} · {row.scope}</option>)}</Choice></Field></div>
        <section id="selected-rule-editor" className="jj-rule-edit-detail" aria-label={selected.title+'的访问要求'}>
          <header className="jj-rule-edit-heading"><div className="jj-rule-edit-title"><h3 className="jj-title-group">{selected.title}</h3><Button kind="quiet" icon={<CloseOutlined aria-hidden="true"/>} aria-label="收起规则编辑" onClick={closeRule}/></div><p className="jj-muted">{selected.scope}</p>{selected.effects.length>0&&<p className="jj-small jj-muted">受保护结果：{selected.effects.join('、')}</p>}</header>
          <div className="jj-rule-expectations"><div><span className="jj-small jj-muted">当前生效要求</span><Badge>{selected.item.expectation==='ALLOW'?'允许':'禁止'}</Badge></div><Field measure="compact" label="调整后的要求"><Choice measure="compact" aria-label={`调整${selected.actor?.display_name}${selected.action?.display_name}对${selected.scope}的权限`} value={changes[selected.item.item_id]??selected.item.expectation} disabled={editingDisabled} onValueChange={value=>setChanges(current=>({...current,[selected.item.item_id]:value as 'ALLOW'|'DENY'}))}><option value="ALLOW">允许</option><option value="DENY">禁止</option></Choice></Field></div>
          <section className="jj-rule-condition-editor" aria-label={`${selected.title}对${selected.scope}的适用条件`}>
            <header className="jj-rule-condition-context"><h4 className="jj-title-caption">{selected.title}的适用条件</h4>{selected.conditionChanged&&<p className="jj-small jj-muted">原条件：{conditionLabels(selected.item.conditions).join('，')||'已登录账号'}</p>}</header>
            <RuleConditionFields key={selected.item.item_id} value={selected.conditions} relation={selected.item.relation} disabled={editingDisabled} onChange={conditions=>setConditionChanges(current=>({...current,[selected.item.item_id]:conditions}))}/>
          </section>
        </section>
      </div>:<Empty title="当前没有可调整的访问规则"/>}
      <ImplementationMappings projectId={projectId} value={value} edits={sourceChanges} disabled={busy||uncertain||proposals.length>0} onChange={setSourceChanges}/>
      {changed&&<p className="jj-rule-edit-summary jj-small jj-muted">{changedRules.length>0&&<>调整 {changedRules.length} 条规则的要求或适用条件。</>}{changedMappings.length>0&&<>核对 {changedMappings.length} 项角色或操作对应。</>}生成提案后仍需审阅批准。</p>}
      {changed&&!conflict&&!unknownMapping&&<DraftValidationPreview projectId={projectId} command={{expected_boundary_state_fingerprint:value.boundary_state_fingerprint,actors:value.actors.map(item=>item.item_id in sourceChanges?{...item,source_candidate_ids:sourceChanges[item.item_id]}:item),actions:value.actions.map(item=>item.item_id in sourceChanges?{...item,source_candidate_ids:sourceChanges[item.item_id]}:item),permissions:value.permissions.map(item=>({...item,expectation:changes[item.item_id]??item.expectation,...(item.item_id in conditionChanges?{conditions:conditionChanges[item.item_id]}:{})}))}}/>}
      <div className="jj-rule-editor-reason"><Field measure="long" label="变更理由"><textarea value={reason} disabled={busy || uncertain || proposals.length > 0} onChange={event => setReason(event.target.value)} placeholder="说明访问要求或对应关系为何需要调整"/></Field></div>
      <TaskActions separated note="本页编辑尚未生效；生成提案不会直接改变正式规则。">{dirty&&<Button kind="quiet" disabled={busy||uncertain} onClick={()=>{rememberEditorDraft(draftKey,undefined);basis.current=value.boundary_state_fingerprint;setChanges({});setConditionChanges({});setSourceChanges({});setReason('');setExpandedRule(null)}}>放弃本页编辑</Button>}<Button kind="primary" busy={busy} disabled={!changed || !reason.trim() || uncertain || conflict || unknownMapping || proposals.length>0 || Boolean(state.error)} onClick={() => void act(async () => { const key = 'jiejian.studio.maintenance:' + projectId; sessionStorage.setItem(key, 'pending'); const submitted=editorDraftGeneration(draftKey,projectId); let confirmed=false; try {
        const proposal = await api.createMaintenanceProposal(projectId, { expected_boundary_state_fingerprint: value.boundary_state_fingerprint,
            actors: value.actors.map(item=>item.item_id in sourceChanges?{...item,source_candidate_ids:sourceChanges[item.item_id]}:item),
            actions: value.actions.map(item=>item.item_id in sourceChanges?{...item,source_candidate_ids:sourceChanges[item.item_id]}:item),
            permissions: value.permissions.map(item => ({ ...item, expectation: changes[item.item_id] ?? item.expectation, ...(item.item_id in conditionChanges ? {conditions:conditionChanges[item.item_id]} : {}) })), provenance: reason.trim() });
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
    } })}>生成待审变更</Button></TaskActions>{uncertain && <Notice tone="caution">生成结果尚未确认，请先读取已经保存的提案。<Button busy={busy} onClick={() => void act(async () => { const result = await api.proposals(projectId, true); assertProject(result.project_id, projectId); result.proposals.forEach(item => assertProject(item.proposal.project_id, projectId)); setProposals(result.proposals.map(item => item.proposal.proposal_id)); })} busyLabel="正在查询">读取待审提案</Button></Notice>}{proposals.map((id, index) => <Button key={id} onClick={() => void act(() => onProposal(id))}>审阅提案 {index + 1}</Button>)}</section></TaskSurface>;
}
