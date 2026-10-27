import { useState } from 'react';
import { ruleCandidatesApi, type BoundaryChoice, type BoundaryReview, type RuleCandidateView } from '../../entities/permission/api/ruleCandidates';
import { Choice } from "../../shared/ui/Choice";
import { Button } from "../../shared/ui/actions";
import { Field } from "../../shared/ui/layout";
import { text } from '../../shared/lib/format';
const treatments: Array<{
    id: BoundaryChoice['outcome'];
    label: string;
}> = [{ id: 'BUSINESS_RULE', label: '保留为业务要求' }, { id: 'REPRESENTED_BY_RULES', label: '已由指定访问规则覆盖' }, { id: 'PREPARATION_DEPENDENCY', label: '作为检查前的准备条件' }, { id: 'EVIDENCE_GAP', label: '需要补充独立证据' }, { id: 'COVERAGE_GAP', label: '需要补充检查范围' }, { id: 'NOT_SEPARATE_ACTION', label: '不作为独立业务操作' }, { id: 'AGENT_OVERINTERPRETATION', label: '纠正与原要求不符的解释' }, { id: 'DEFER', label: '暂不决定' }];
export function BusinessIssue({ projectId, value, issue, busy, onChange, onRun }: {
    projectId: string;
    value: RuleCandidateView;
    issue: BoundaryReview;
    busy: boolean;
    onChange: (value: RuleCandidateView) => void;
    onRun: (callback: () => Promise<unknown>) => Promise<void>;
}) {
    const [outcome, setOutcome] = useState<BoundaryChoice['outcome'] | ''>(''), [reason, setReason] = useState(''), [retained, setRetained] = useState(issue.text), [permissions, setPermissions] = useState<string[]>([]);
    const candidate = value.candidate, requiresRules = outcome === 'REPRESENTED_BY_RULES';
    return <article className="jj-review-rule jj-business-issue"><h3>{text(issue.text)}</h3>{issue.status === 'RESOLVED' ? <details><summary>查看已确认的处理方式</summary><p>{text(issue.decision?.reason ?? '已确认')}</p><p>{text(issue.decision?.retained_requirement ?? issue.text)}</p></details> : <><Field label="如何处理这条要求"><Choice disabled={busy} value={outcome} onValueChange={value => setOutcome(value as BoundaryChoice['outcome'])}><option value="">选择处理方式</option>{treatments.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}</Choice></Field>{requiresRules && <fieldset className="jj-choice-field"><legend>由哪些访问规则覆盖？</legend>{candidate.content.permissions.map((permission, index) => { const actor = candidate.content.actors.find(item => item.item_id === permission.subject_actor_item_id), action = candidate.content.actions.find(item => item.item_id === permission.business_action_item_id); return <label key={permission.item_id}><input type="checkbox" checked={permissions.includes(permission.item_id)} onChange={event => setPermissions(current => event.target.checked ? [...current, permission.item_id] : current.filter(id => id !== permission.item_id))}/><span>{actor && action ? `${text(actor.display_name)}${permission.expectation === 'ALLOW' ? '可以' : '不得'}${text(action.display_name)}` : `访问规则 ${index + 1}`}</span></label>; })}</fieldset>}<Field label="判断依据"><textarea value={reason} disabled={busy} onChange={event => setReason(event.target.value)}/></Field><Field label="仍需保留的业务要求"><textarea value={retained} disabled={busy} onChange={event => setRetained(event.target.value)}/></Field><div className="jj-confirmation-actions"><Button disabled={busy || !outcome || !reason.trim() || !retained.trim() || requiresRules && !permissions.length} onClick={() => void onRun(async () => { if (!outcome)
        return; const operation = crypto.randomUUID(), key = `jiejian.studio.rule-decision:${projectId}:${candidate.candidate_id}`; const prior = sessionStorage.getItem(key); if (prior) {
        const receipt = await ruleCandidatesApi.receipt(projectId, prior, 'DECIDE');
        if (receipt.candidate) {
            sessionStorage.removeItem(key);
            onChange(receipt.candidate);
        }
        return;
    } sessionStorage.setItem(key, operation); const next = await ruleCandidatesApi.reviewBoundary(projectId, candidate.candidate_id, candidate.revision, candidate.basis_id, operation, { issue_id: issue.issue_id, issue_fingerprint: issue.issue_fingerprint, outcome, reason: reason.trim(), retained_requirement: retained.trim(), permission_item_ids: requiresRules ? permissions : undefined }); sessionStorage.removeItem(key); onChange(next); })}>保存这项决定</Button></div></>}</article>;
}
