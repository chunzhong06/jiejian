import { useEffect, useRef, useState } from 'react';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { Button } from '../../../shared/ui/actions';
import { Notice, Badge } from '../../../shared/ui/feedback';
import { Field, TaskActions } from '../../../shared/ui/layout';
import { text } from '../../../shared/lib/format';
import type { RuleItem } from '../../permission/api/ruleWorkspace';
import { repairReference } from '../../check/api/repairs';
import { developmentApi, type DevelopmentReceipt } from '../api/development';
import { sourceChangesApi, type RegistrationPreview, type RuleChangeTarget } from '../api/sourceChanges';
import { ChangePreview } from './ChangePreview';
import './styles.css';

type Submission = Parameters<typeof sourceChangesApi.register>[1];
type Option = { key: string; title: string; scope: string; problem: boolean; target: RuleChangeTarget };
const targetKey = (target: RuleChangeTarget) => JSON.stringify([target.permission, target.repair]);
export function changeTargetOptions(rules: RuleItem[], original?:string): Option[] {
    return rules.flatMap(rule => {
        const issues = rule.issues.filter(issue => issue.status!=='STALE'&&(issue.status!=='VERIFIED'||issue.contract.repair_fingerprint===original));
        const targets = issues.length ? issues.map(issue => ({ permission: rule.permission, repair: repairReference(issue.contract) })) : [{ permission: rule.permission, repair: null }];
        return targets.map(target => ({ key: targetKey(target), title: rule.title, scope: rule.resource_scope, problem: Boolean(target.repair), target }));
    });
}

export function ChangeRegistration({ projectId, options, initialTargets = [], draftScope, closeLabel = '收起', embedded=false, onClose, onSaved, onError, onBusyChange }: {
    projectId: string; options: Option[]; initialTargets?: RuleChangeTarget[];
    closeLabel?: string; embedded?: boolean; draftScope?:string;
    onBusyChange?: (busy:boolean)=>void; onClose: () => void; onSaved: (id: string) => void; onError: (error: unknown) => void;
}) {
    const key = 'jiejian.change-registration:' + projectId;
    // 未提交说明按原题隔离；未知写入继续由项目级原请求持有，跨入口只能查询或恢复它。
    const draftKey=key+':draft'+(draftScope?':'+encodeURIComponent(draftScope):'');
    const [pending, setPending] = useState<Submission | null>(() => {
        const saved = sessionStorage.getItem(key);
        return saved ? JSON.parse(saved) as Submission : null;
    });
    const [reason, setReason] = useState(pending?.reason ?? sessionStorage.getItem(draftKey) ?? '');
    const [targets, setTargets] = useState<RuleChangeTarget[]>(pending?.rule_targets ?? initialTargets);
    const [preview, setPreview] = useState<RegistrationPreview>();
    const [busy, setBusy] = useState(false), [retry, setRetry] = useState(false);
    const lock = useRef(false);
    useEffect(()=>{onBusyChange?.(busy)},[busy,onBusyChange]);
    useEffect(()=>()=>onBusyChange?.(false),[onBusyChange]);
    const accept = (receipt: DevelopmentReceipt) => {
        assertProject(receipt.project_id, projectId);
        if (!receipt.change_id) throw new Error('登记尚未返回修改记录，请查询原回执。');
        sessionStorage.removeItem(key);
        const owner=sessionStorage.getItem(key+':draft-owner');
        if(owner===key+':draft'||owner?.startsWith(key+':draft:'))sessionStorage.removeItem(owner);
        else sessionStorage.removeItem(key+':draft');
        sessionStorage.removeItem(key+':draft-owner');
        onSaved(receipt.change_id);
    };
    const act = async (resubmit = false) => {
        if (lock.current) return;
        lock.current = true; setBusy(true);
        try {
            if (pending) {
                const receipt = resubmit ? await sourceChangesApi.register(projectId, pending) : await developmentApi.receipt(projectId, 'DELIVER', pending.operation_id);
                if (receipt) accept(receipt);
                else setRetry(true);
                return;
            }
            if (!preview) {
                const value = await sourceChangesApi.registrationPreview(projectId);
                assertProject(value.project_id, projectId); setPreview(value); return;
            }
            const submission: Submission = { operation_id: crypto.randomUUID().replaceAll('-', ''),
                expected_registration_fingerprint: preview.fingerprint, expected_source_fingerprint: preview.source_fingerprint,
                reason: reason.trim(), claimed_paths: [], repair_reference: null, rule_targets: targets };
            // 丢失响应后保留原参数和操作键，跨入口查询或重试同一笔登记。
            sessionStorage.setItem(key+':draft-owner',draftKey);
            sessionStorage.setItem(key, JSON.stringify(submission)); setPending(submission);
            accept(await sourceChangesApi.register(projectId, submission));
        } catch (error) {
            if (error instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID'].includes(error.code)) {
                sessionStorage.removeItem(key); setPending(null); setPreview(undefined); setRetry(false);
            }
            onError(error);
        } finally { lock.current = false; setBusy(false); }
    };
    const selected = new Set(targets.map(targetKey)), disabled = busy || Boolean(pending);
    return <section className={embedded?"jj-change-registration is-embedded":"jj-change-registration"} aria-label="登记本地修改">
        <header hidden={embedded}><div><h2>登记本地修改</h2><p>选择这次修改涉及的权限，再核对实际文件变化。</p></div><Button disabled={busy} onClick={onClose}>{closeLabel}</Button></header>
        <div className="jj-registration-fields"><Field measure="long" label="修改说明"><textarea rows={4} maxLength={512} disabled={disabled} value={reason} placeholder="说明修复了什么，以及正常功能如何保留" onChange={event => { setReason(event.target.value); sessionStorage.setItem(draftKey, event.target.value); }}/></Field>
            <fieldset><legend>涉及的权限与问题 <span>{targets.length} 项</span></legend><div className="jj-registration-targets">{options.map(option => <label key={option.key} data-selected={selected.has(option.key)}><input type="checkbox" disabled={disabled} checked={selected.has(option.key)} onChange={event => { setTargets(values => event.target.checked ? [...values, option.target] : values.filter(target => targetKey(target) !== option.key)); }}/><span><span className="jj-object-line"><strong>{text(option.title)}</strong>{option.problem && <Badge tone="negative">原问题</Badge>}</span><small>{text(option.scope)}</small></span></label>)}</div></fieldset>
        </div>
        {preview && <ChangePreview value={preview}/>}
        <TaskActions separated note={pending ? '登记结果待确认，保留原请求查询。' : '登记后继续核对运行版本与原问题复验。'}>{pending && retry && <Button disabled={busy} onClick={() => void act(true)}>使用原请求重试</Button>}<Button kind="primary" busy={busy} disabled={!pending && (!reason.trim() || (options.length > 0 && targets.length === 0))} onClick={() => void act()}>{pending ? '查询登记结果' : preview ? '确认登记修改' : '预览文件变化'}</Button></TaskActions>
        {retry && <Notice tone="caution">尚未找到回执。可稍后查询，或使用相同请求继续登记。</Notice>}
    </section>;
}
