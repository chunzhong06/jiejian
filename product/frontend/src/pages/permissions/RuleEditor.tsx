import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import { InitialRules } from './InitialRules';
import { useRef, useState } from 'react';
import { businessBoundariesApi as api } from '../../entities/permission/api/businessBoundaries';
import { ApiError } from '../../shared/api/http';
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
    const [changes, setChanges] = useState<Record<string, 'ALLOW' | 'DENY'>>({}), [reason, setReason] = useState(''), [busy, setBusy] = useState(false), [uncertain, setUncertain] = useState(Boolean(sessionStorage.getItem('jiejian.studio.maintenance:' + projectId))), [proposals, setProposals] = useState<string[]>([]), lock = useRef(false);
    if (state.loading)
        return <PageSkeleton view="/permissions" title="编辑权限要求"/>;
    if (state.error || !state.data)
        return <ErrorNote error={state.error} onRetry={state.reload}/>;
    const value = state.data;
    if (!value.permissions.length) return <InitialRules projectId={projectId} basis={value} onBack={onBack} onProposal={onProposal} onError={onError}/>;
    const changed = value.permissions.some(item => changes[item.item_id] && changes[item.item_id] !== item.expectation);
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
    return <><div><Button kind="quiet" disabled={busy} onClick={onBack}>全部权限规则</Button></div><Heading title="调整访问要求"/><section className="jj-panel jj-rule-editor"><h2>当前生效的访问规则</h2><div className="jj-rule-editor-list">{value.permissions.filter(item => item.effective_state === 'ACTIVE').map(item => { const actor = value.actors.find(actor => actor.item_id === item.subject_actor_item_id), owner = value.actors.find(actor => actor.item_id === item.resource_owner_actor_item_id), action = value.actions.find(action => action.item_id === item.business_action_item_id); return <article className="jj-rule-editor-row" key={item.item_id}><div><h3>{text(actor?.display_name ?? '当前角色')}{text(action?.display_name ?? '当前业务操作')}</h3><p className="jj-small jj-muted">{item.relation === 'OWNS' ? '自己的资源' : item.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${text(owner?.display_name ?? '同角色')}账号的资源` : `${text(owner?.display_name ?? '其他角色')}的资源`}</p></div><div className="jj-rule-editor-controls"><Badge tone={item.expectation === 'ALLOW' ? 'positive' : 'negative'}>{item.expectation === 'ALLOW' ? '目前允许' : '目前禁止'}</Badge><Choice aria-label={`调整${actor?.display_name}${action?.display_name}的权限`} value={changes[item.item_id] ?? item.expectation} disabled={busy || uncertain} onValueChange={value => setChanges(current => ({ ...current, [item.item_id]: value as 'ALLOW' | 'DENY' }))}><option value="ALLOW">调整后允许</option><option value="DENY">调整后禁止</option></Choice></div></article>; })}</div>{!value.permissions.length && <Empty title="当前没有可调整的访问规则"/>}<label className="jj-field jj-rule-editor-reason"><span>变更理由</span><textarea value={reason} disabled={busy || uncertain} onChange={event => setReason(event.target.value)} placeholder="说明访问要求发生了什么变化"/></label><div className="jj-confirmation-actions jj-form-actions"><Button disabled={busy} onClick={onBack}>返回</Button><Button kind="primary" busy={busy} disabled={!changed || !reason.trim() || uncertain} onClick={() => void act(async () => { const key = 'jiejian.studio.maintenance:' + projectId; sessionStorage.setItem(key, 'pending'); try {
        const proposal = await api.createMaintenanceProposal(projectId, { expected_boundary_state_fingerprint: value.boundary_state_fingerprint, actors: value.actors, actions: value.actions, permissions: value.permissions.map(item => ({ ...item, expectation: changes[item.item_id] ?? item.expectation })), provenance: reason.trim() });
        assertProject(proposal.proposal.project_id, projectId);
        sessionStorage.removeItem(key);
        await onProposal(proposal.proposal.proposal_id);
    }
    catch (error) {
        if (error instanceof ApiError && ['INPUT_INVALID', 'STATE_PRECONDITION', 'API_VALIDATION_ERROR'].includes(error.code))
            sessionStorage.removeItem(key);
        else
            setUncertain(true);
        throw error;
    } })}>生成待审变更</Button></div>{uncertain && <Notice>生成结果尚未确认，请先读取已经保存的提案。<Button busy={busy} onClick={() => void act(async () => { const result = await api.proposals(projectId, true); assertProject(result.project_id, projectId); result.proposals.forEach(item => assertProject(item.proposal.project_id, projectId)); setProposals(result.proposals.map(item => item.proposal.proposal_id)); })}>读取待审提案</Button></Notice>}{proposals.map((id, index) => <Button key={id} onClick={() => void act(() => onProposal(id))}>审阅提案 {index + 1}</Button>)}</section></>;
}
