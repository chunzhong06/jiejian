import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import './styles/permissions.css'
import './styles/rules.css'
import './workspace.css'
import { useEffect, useRef, useState } from 'react';
import { CheckOutlined, MinusOutlined, ArrowLeftOutlined, CloseOutlined } from '@ant-design/icons';
import { businessBoundariesApi as api, type BusinessBoundaryViewDto, type BoundaryProposalViewDto, type BoundaryReviewValueDto } from '../../entities/permission/api/businessBoundaries';
import { ruleCandidatesApi, type RuleCandidateView } from '../../entities/permission/api/ruleCandidates';
import { RuleEditor } from './RuleEditor';
import { BusinessIssue } from './BusinessIssue';
import { RuleWorkbench } from './RuleWorkbench';
import { experienceApi } from '../../entities/application/api/experience';
import { assertProject, type PageProps } from '../../shared/model/page';
import { go } from '../../shared/lib/navigation';
import { text } from '../../shared/lib/format';
import { useRead } from '../../shared/lib/useRead';
import { Button } from "../../shared/ui/actions";
import { Heading } from "../../shared/ui/layout";
import { Badge, Loading, ErrorNote, Notice, Empty } from "../../shared/ui/feedback";
type Rule = BusinessBoundaryViewDto['permission_intents'][number];
function owner(rule: Rule, names: Map<string, string>) { return rule.relation === 'OWNS' ? '自己的资源' : rule.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${names.get(rule.resource_owner_actor_id) ?? '同角色'}账号的资源` : `${names.get(rule.resource_owner_actor_id) ?? '其他角色'}的资源`; }
export function Permissions({ projectId, official, refresh, onError, route }: PageProps) {
    const editor = useRead('rules:' + projectId, async () => { const value = await api.editor(projectId); assertProject(value.project_id, projectId); return value; });
    const candidates = useRead('rule-candidates:' + projectId, () => ruleCandidatesApi.context(projectId));
    const [maintenance, setMaintenance] = useState(false), [proposal, setProposal] = useState<BoundaryProposalViewDto>(), [candidate, setCandidate] = useState<RuleCandidateView>(), [selection, setSelection] = useState<Rule>(), [query, setQuery] = useState(''), [filter, setFilter] = useState('ALL'), [choice, setChoice] = useState<boolean>(), [busy, setBusy] = useState(false), [ack, setAck] = useState(false), [uncertain, setUncertain] = useState(false), [notice, setNotice] = useState('');
    const pending = useRef(false), generation = useRef(0);
    useEffect(() => () => { generation.current++; }, []);
    useEffect(() => { setAck(false); setUncertain(Boolean(proposal && sessionStorage.getItem(`jiejian.studio.approval:${projectId}:${proposal.proposal.proposal_id}`))); }, [proposal?.proposal.proposal_id]);
    useEffect(() => { const id = route.query.get('proposal_id'); if (id) {
        let valid = true;
        void api.proposal(projectId, id).then(value => { assertProject(value.proposal.project_id, projectId); if (value.proposal.proposal_id !== id)
            throw new Error('提案与所选记录不一致。'); if (valid)
            setProposal(value); }).catch(onError);
        return () => { valid = false; };
    } }, [projectId, route.query.get('proposal_id')]);
    useEffect(() => { const id = route.query.get('candidate_id'); if (!id)
        return; let valid = true; void ruleCandidatesApi.show(projectId, id, Number(route.query.get('revision')) || undefined).then(value => { assertProject(value.candidate.project_id, projectId); if (valid)
        setCandidate(value); }).catch(onError); return () => { valid = false; }; }, [projectId, route.query.get('candidate_id'), route.query.get('revision')]);
    const act = async (callback: () => Promise<unknown>) => { if (pending.current)
        return; const epoch = generation.current; pending.current = true; setBusy(true); try {
        await callback();
    }
    catch (error) {
        if (epoch === generation.current)
            onError(error);
    }
    finally {
        pending.current = false;
        if (epoch === generation.current)
            setBusy(false);
    } };
    const boundary = editor.data?.boundary, names = new Map(boundary?.actors.map(actor => [actor.actor_id, text(actor.display_name)]));
    const openProposal = async (id: string) => { const value = await api.proposal(projectId, id); assertProject(value.proposal.project_id, projectId); setMaintenance(false); setProposal(value); go('/permissions?proposal_id=' + encodeURIComponent(id)); };
    const approved = async () => { if (!proposal || pending.current)
        return; await act(async () => { try {
        sessionStorage.setItem(`jiejian.studio.approval:${projectId}:${proposal.proposal.proposal_id}`, 'pending');
        await api.approve(projectId, proposal.proposal, '已核对完整提案中的访问要求、业务结果和沿用规则。');
        sessionStorage.removeItem(`jiejian.studio.approval:${projectId}:${proposal.proposal.proposal_id}`);
        setNotice('权限规则已更新。');
        setProposal(undefined);
        setUncertain(false);
        go('/permissions');
        editor.reload();
        refresh();
    }
    catch (error) {
        setUncertain(true);
        throw error;
    } }); };
    const readDecision = () => void act(async () => { if (!proposal)
        return; const value = await api.proposal(projectId, proposal.proposal.proposal_id); assertProject(value.proposal.project_id, projectId); setProposal(value); if (value.decision) {
        sessionStorage.removeItem(`jiejian.studio.approval:${projectId}:${value.proposal.proposal_id}`);
        setUncertain(false);
        editor.reload();
        refresh();
    } });
    if (editor.loading)
        return <PageSkeleton view="/permissions"/>;
    if (editor.error || !boundary)
        return <ErrorNote error={editor.error} onRetry={editor.reload}/>;
    if (proposal) {
        const review = proposal.review, permissions = review?.items.filter(item => item.entity_kind === 'PERMISSION') ?? [], definitions = review?.items.filter(item => item.entity_kind !== 'PERMISSION') ?? [];
        const blocked = Boolean(!review || review.basis_state !== 'COMPLETE' || review.current_state_changed || proposal.proposal.unresolved_questions?.length);
        const ruleGroups = new Map<string, typeof permissions>();
        for (const item of permissions) {
            const name = text(item.after.action ?? item.before?.action ?? '访问规则');
            ruleGroups.set(name, [...(ruleGroups.get(name) ?? []), item]);
        }
        const accepted = proposal.decision?.decision === 'APPROVED';
        return <>
      <div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => { setProposal(undefined); go('/permissions'); }}>全部权限规则</Button></div>
      <Heading eyebrow={proposal.decision ? '权限变更记录' : '权限审阅'} title={proposal.decision ? '查看这次权限变更' : '核对规则将如何改变'} actions={<Badge tone={proposal.decision ? accepted ? 'positive' : 'neutral' : 'accent'}>{proposal.decision ? accepted ? '已批准' : '已放弃' : '尚未生效'}</Badge>}/>
      <div className="jj-review-overview"><span><strong>{permissions.length}</strong> 条访问规则</span><span><strong>{ruleGroups.size}</strong> 项业务操作</span><span>批准覆盖整份提案及沿用定义</span></div>
      <div className="jj-permission-review-layout">
        <div className="jj-review-content">
          {[...ruleGroups].map(([name, items]) => <section className="jj-review-action" key={name}>
            <header><h2>{name}</h2><span>{items.length} 条规则</span></header>
            {items.map(item => <article className="jj-review-rule" key={item.item_id}>
              {item.change_kind !== 'CREATE' && item.change_kind !== 'REFERENCE' ? <div className="jj-rule-compare">
                <section><p className="jj-eyebrow">现在</p>{item.basis_available && item.before ? <RuleMeaning value={item.before}/> : <Notice>原版本不可用，无法核对变化。</Notice>}</section>
                <section><p className="jj-eyebrow">批准后</p><RuleMeaning value={item.after} changeKind={item.change_kind}/></section>
              </div> : <RuleMeaning value={item.after} changeKind={item.change_kind}/>}
            </article>)}
          </section>)}
          {!permissions.length && <section className="jj-review-action"><h2>访问规则</h2><p className="jj-muted">这份提案没有调整访问规则。</p></section>}
          <div className="jj-review-appendix">
            {definitions.length > 0 && <details className="jj-review-definitions"><summary>角色、业务动作与结果定义（{definitions.length} 项）</summary>{definitions.map(item => <article className="jj-review-rule" key={item.item_id}><h3>{text(item.after.display_name)}</h3>{item.before && <><p className="jj-eyebrow">现在</p><RuleMeaning value={item.before}/></>}<p className="jj-eyebrow">{item.change_kind === 'REFERENCE' ? '沿用' : '批准后'}</p><RuleMeaning value={item.after} changeKind={item.change_kind}/></article>)}</details>}
            <details><summary>提案来源</summary><p className="jj-small">{text(proposal.proposal.provenance)}</p></details>
          </div>
        </div>
        <footer className="jj-approval-footer">
          {blocked && !proposal.decision && <Notice>{review?.current_state_changed ? '当前业务已变化，请重新整理提案。' : proposal.proposal.unresolved_questions?.length ? proposal.proposal.unresolved_questions.map(text).join('；') : '原始依据不完整，暂时无法批准。'}</Notice>}
          {proposal.decision ? <div className="jj-approval-decision"><p>{accepted ? '这份规则已生效，检查将使用批准后的访问要求。' : '这份提案未被采用，现有权限保持原样。'}</p><Button kind="primary" onClick={() => go(accepted ? '/preparation' : '/permissions')}>{accepted ? '准备检查材料' : '查看当前规则'}</Button></div> : <>
            <div className="jj-approval-choice"><h3>确认这份权限要求</h3><label className="jj-checkbox"><input type="checkbox" checked={ack} disabled={busy || uncertain} onChange={event => setAck(event.target.checked)}/><span>我已核对整份权限要求</span></label></div>
            <div className="jj-review-buttons jj-confirmation-actions"><Button disabled={busy || uncertain} onClick={() => void act(async () => { await api.reject(projectId, proposal.proposal, '用户放弃本次权限提案'); setProposal(undefined); editor.reload(); go('/permissions'); })}>放弃提案</Button>{uncertain ? <><Notice>批准结果尚未确认。</Notice><Button busy={busy} onClick={readDecision}>查询这次批准</Button></> : <Button kind="primary" busy={busy} disabled={!ack || blocked} onClick={() => void approved()}>批准权限规则</Button>}</div>
          </>}
        </footer>
      </div>
    </>;
    }
    if (maintenance)
        return <RuleEditor projectId={projectId} onBack={() => setMaintenance(false)} onProposal={openProposal} onError={onError}/>;
    if (candidate)
        return <CandidateReview value={candidate} projectId={projectId} busy={busy} onChange={setCandidate} onRun={act} onBack={() => setCandidate(undefined)} onProposal={openProposal}/>;
    const roles = boundary.actors.filter(actor => actor.effective_state === 'ACTIVE'), actions = boundary.actions.filter(action => action.effective_state === 'ACTIVE' && action.display_name.includes(query.trim()));
    if (boundary.permission_intents.length)
        return <RuleWorkbench projectId={projectId} boundary={boundary} official={official} route={route} refresh={refresh} onError={onError} onManage={() => setMaintenance(true)} reviewActions={<>{editor.data?.pending_proposals.length ? <Notice>{editor.data.pending_proposals.length} 份权限变更待审阅。{editor.data.pending_proposals.map(item => <Button kind="quiet" key={item.proposal_id} onClick={() => void act(() => openProposal(item.proposal_id))}>审阅权限变更</Button>)}</Notice> : null}{candidates.data?.candidates.filter(item => !item.decision && !item.visibility?.archived).map(item => <Button key={item.candidate_id} onClick={() => void act(async () => setCandidate(await ruleCandidatesApi.show(projectId, item.candidate_id, item.revision)))}>整理业务要求</Button>)}</>}/>;
    return <><Heading eyebrow={`权限版本 ${boundary.policy_epoch}`} title="权限规则" actions={<>{boundary.actors.length > 0 && <Button onClick={() => setMaintenance(true)}>调整访问规则</Button>}<Button onClick={() => { candidates.reload(); editor.reload(); }}>读取待审变更</Button></>}/>{notice && <Notice tone="positive">{notice}<Button kind="quiet" onClick={() => go('/preparation')}>准备检查</Button></Notice>}
    {editor.data!.pending_proposals.length > 0 && <section className="jj-pending-rules"><div><Badge tone="accent">待审阅</Badge><h3>{editor.data!.pending_proposals.length} 份权限提案</h3></div>{editor.data!.pending_proposals.map((item, index) => <Button key={item.proposal_id} busy={busy} onClick={() => void act(() => openProposal(item.proposal_id))}>审阅{editor.data!.pending_proposals.length > 1 ? `第 ${index + 1} 份` : ''}变更</Button>)}</section>}
    {roles.length > 0 ? <><div className="jj-rule-toolbar"><input aria-label="查找业务操作" placeholder="查找业务操作" value={query} onChange={event => setQuery(event.target.value)}/><div className="jj-toggle-group" aria-label="筛选规则">{[['ALL', '全部'], ['ALLOW', '允许'], ['DENY', '禁止']].map(([id, label]) => <button key={id} aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}</button>)}</div></div><div className="jj-rule-workspace"><div className="jj-scroll-table jj-permission-table"><table><thead><tr><th>业务操作</th>{roles.map(role => <th key={role.actor_id}>{text(role.display_name)}</th>)}</tr></thead><tbody>{actions.map(action => { const rules = boundary.permission_intents.filter(rule => boundary.actors.some(owner => owner.actor_id === rule.resource_owner_actor_id && owner.revision === rule.resource_owner_actor_revision && owner.effective_state === 'ACTIVE') && rule.effective_state === 'ACTIVE' && rule.business_action_id === action.action_id && rule.action_revision === action.revision); if (filter !== 'ALL' && !rules.some(rule => rule.expectation === filter))
        return null; const status = boundary.permission_statuses.find(item => item.action_id === action.action_id && item.action_revision === action.revision); return <tr key={action.action_id}><th scope="row"><strong>{text(action.display_name)}</strong><small>{text(action.primary_resource_concept)}</small>{!status?.permission_semantics_confirmed && <small className="jj-warning-text">需要重新确认权限</small>}{status?.permission_semantics_confirmed && !status.allow_control_available && <small className="jj-warning-text">缺少正常操作对照</small>}</th>{roles.map(role => { const matching = rules.filter(rule => rule.subject_actor_id === role.actor_id && rule.subject_actor_revision === role.revision && (filter === 'ALL' || rule.expectation === filter)); return <td key={role.actor_id}>{matching.length ? matching.map((rule, index) => <button className="jj-permission-cell" key={rule.intent_id ?? index} onClick={() => setSelection(rule)}><span data-allowed={rule.expectation === 'ALLOW'}>{rule.expectation === 'ALLOW' ? <CheckOutlined aria-hidden="true"/> : <MinusOutlined aria-hidden="true"/>}{rule.expectation === 'ALLOW' ? '允许' : '禁止'}</span><small>{owner(rule, names)}</small>{matching.length > 1 && <small>{rule.protected_effect_ids.map(id => action.effect_catalog.find(effect => effect.effect_id === id)?.business_label ?? '未识别的结果').map(text).join('、')}</small>}</button>) : <span className="jj-small jj-muted">未设定</span>}</td>; })}</tr>; })}</tbody></table>{!actions.length && <Empty title="没有找到这项业务操作"/>}</div>{selection && <aside className="jj-rule-inspector jj-panel" key={selection.intent_id + ":" + selection.revision}><header><h3>这条规则保护什么</h3><Button kind="quiet" icon={<CloseOutlined aria-hidden="true"/>} aria-label="关闭规则详情" onClick={() => setSelection(undefined)}/></header><Badge tone={selection.expectation === 'ALLOW' ? 'positive' : 'negative'}>{selection.expectation === 'ALLOW' ? '允许访问' : '禁止访问'}</Badge><p>{names.get(selection.subject_actor_id)}{selection.expectation === 'ALLOW' ? '可以' : '不得'}{text(boundary.actions.find(item => item.action_id === selection.business_action_id)?.display_name ?? '执行该操作')}。</p><dl className="jj-facts"><div><dt>资源范围</dt><dd>{owner(selection, names)}</dd></div><div><dt>业务结果</dt><dd>{selection.protected_effect_ids.map(id => boundary.actions.find(item => item.action_id === selection.business_action_id)?.effect_catalog.find(effect => effect.effect_id === id)?.business_label ?? '未识别的结果').map(text).join('、')}</dd></div><div><dt>规则版本</dt><dd>{selection.revision}</dd></div></dl></aside>}</div></> : official ? <section className="jj-panel jj-official-rules"><p className="jj-eyebrow">数字展馆</p><h2>先确认评审的访问范围</h2><div className="jj-business-agreement"><div><Badge tone="positive">负责人</Badge><p>可以下载自己管理的内部资料与公开展示版。</p></div><div><Badge>评审</Badge><p>可以阅读公开介绍，不得取得内部完整包，也不得在处理过程中被临时授予内部包访问权。</p></div></div><fieldset className="jj-choice-field"><legend>评审可以下载公开展示版吗？</legend><label><input type="radio" name="exhibition" checked={choice === true} onChange={() => setChoice(true)}/><span><strong>可以下载</strong><small>公开内容可离线阅读</small></span></label><label><input type="radio" name="exhibition" checked={choice === false} onChange={() => setChoice(false)}/><span><strong>只在线阅读</strong><small>保留预览，不提供展示版下载</small></span></label></fieldset><Button kind="primary" disabled={typeof choice !== 'boolean' || uncertain} busy={busy} onClick={() => void act(async () => { try {
        const result = await experienceApi.boundaryProposal(choice);
        assertProject(result.proposal.project_id, projectId);
        setProposal(result);
        go('/permissions?proposal_id=' + result.proposal.proposal_id);
    }
    catch (error) {
        setUncertain(true);
        throw error;
    } })}>生成待审权限</Button>{uncertain && <Notice>生成结果未确认。请读取待审变更，找到本次提案后继续。</Notice>}</section> : <Empty title="先写清楚访问要求">将角色、业务操作、资源归属和允许或禁止的结果交给开发 Agent 整理，保存的候选会出现在下方。</Empty>}
    <section className="jj-business-requirements"><div className="jj-section-header jj-near-heading"><h2>待整理的业务要求</h2><Button kind="quiet" onClick={candidates.reload}>刷新</Button></div>{candidates.loading ? <Loading /> : candidates.data?.candidates.filter(item => !item.decision && !item.visibility?.archived).length ? <div className="jj-candidate-list">{candidates.data.candidates.filter(item => !item.decision && !item.visibility?.archived).map(item => <button key={item.candidate_id} onClick={() => void act(async () => setCandidate(await ruleCandidatesApi.show(projectId, item.candidate_id, item.revision)))}><span>{text(item.original_text)}</span><Badge tone="accent">查看要求</Badge></button>)}</div> : <p className="jj-small jj-muted">没有尚未处理的业务要求。</p>}</section>
  </>;
}
function RuleMeaning({ value, changeKind }: {
    value: BoundaryReviewValueDto;
    changeKind?: 'CREATE' | 'UPDATE' | 'RETIRE' | 'REFERENCE';
}) {
    return <div className="jj-rule-meaning">{value.expectation ? <>
    <div className="jj-rule-definition">
      <div className="jj-rule-title"><span className="jj-rule-direction" data-allowed={value.expectation === 'ALLOW'} aria-hidden="true">{value.expectation === 'ALLOW' ? <CheckOutlined /> : <CloseOutlined />}</span><h3>{text(value.subject ?? '操作人')}{value.expectation === 'ALLOW' ? '可以' : '不得'}{text(value.action ?? '执行此操作')}</h3>{changeKind && <span className="jj-rule-change">{({ CREATE: '新增', UPDATE: '调整', RETIRE: '停用', REFERENCE: '沿用' })[changeKind]}</span>}</div>
      <p>{value.relation === 'OWNS' ? '自己的资源' : value.relation === 'SAME_ROLE_OTHER_ACCOUNT' ? `其他${text(value.resource_owner ?? '同角色')}账号的资源` : `${text(value.resource_owner ?? '其他角色')}的资源`}</p>
    </div>
    <div className="jj-rule-effects"><span>{value.expectation === 'ALLOW' ? '允许的业务结果' : '禁止的业务结果'}</span><ul>{value.protected_effects.map((effect, index) => <li key={index}>{text(effect)}</li>)}</ul></div>
  </> : <div className="jj-rule-definition"><p>{text(value.description)}</p>{value.resource_concept && <p className="jj-small jj-muted">资源：{text(value.resource_concept)}</p>}{value.effects.map((effect, index) => <div className="jj-definition-effect" key={index}><strong>{text(effect.business_label)}</strong><p>{text(effect.description)}</p></div>)}</div>}{value.effective_state === 'RETIRED' && <Badge tone="caution">将停用</Badge>}</div>;
}
function CandidateReview({ value, projectId, busy, onChange, onRun, onBack, onProposal }: {
    value: RuleCandidateView;
    projectId: string;
    busy: boolean;
    onChange: (value: RuleCandidateView) => void;
    onRun: (callback: () => Promise<unknown>) => Promise<void>;
    onBack: () => void;
    onProposal: (id: string) => Promise<void>;
}) {
    const candidate = value.candidate;
    return <><div><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>全部权限规则</Button></div><Heading eyebrow="整理业务要求" title="先澄清规则，再确认权限"/><section className="jj-panel"><p>{text(candidate.content.original_text)}</p>{value.issues.length > 0 && <div className="jj-divider"/>}{value.issues.map((issue, index) => <Notice key={index}>{text(issue.message)}</Notice>)}{value.boundary_reviews?.map(issue => <BusinessIssue key={candidate.revision + ':' + issue.issue_id} projectId={projectId} value={value} issue={issue} busy={busy} onChange={onChange} onRun={onRun}/>)}{candidate.content.scenarios?.map(scenario => <fieldset className="jj-choice-field" key={scenario.scenario_id}><legend>{text(scenario.question)}</legend>{scenario.options.map(option => <Button key={option.option_id} disabled={busy} onClick={() => void onRun(async () => onChange(await ruleCandidatesApi.decide(projectId, candidate.candidate_id, candidate.revision, candidate.basis_id, crypto.randomUUID(), { scenario_id: scenario.scenario_id, scenario_fingerprint: scenario.scenario_fingerprint, action: 'SELECT', option_id: option.option_id })))}>{text(option.label)}</Button>)}</fieldset>)}{value.scope_review?.map(item => <article className="jj-review-rule" key={item.source.requirement_id}><h3>{text(item.source.title)}</h3><p>{text(item.source.interpretation)}</p><Badge>{item.status === 'CONFIRMED' ? '已确认' : '待确认范围'}</Badge>{item.status !== 'CONFIRMED' && <div className="jj-inline-actions">{([['IN_SCOPE', '纳入检查'], ['PREPARATION', '准备条件'], ['OUT_OF_SCOPE', '本次不覆盖'], ['DEFER', '稍后决定']] as const).map(([disposition, label]) => <Button key={disposition} disabled={busy} onClick={() => void onRun(async () => onChange(await ruleCandidatesApi.scope(projectId, candidate.candidate_id, candidate.revision, candidate.basis_id, crypto.randomUUID(), { requirement_id: item.source.requirement_id, requirement_fingerprint: item.fingerprint, disposition, requirement: item.source.interpretation, reason: '用户在业务要求审阅中明确选择范围', time_scope: 'CHECK_WINDOW' })))}>{label}</Button>)}</div>}</article>)}<div className="jj-confirmation-actions"><Button busy={busy} onClick={() => void onRun(async () => onChange(await ruleCandidatesApi.show(projectId, candidate.candidate_id)))}>重新读取</Button>{value.proposal_id ? <Button kind="primary" busy={busy} onClick={() => void onRun(() => onProposal(value.proposal_id!))}>审阅权限提案</Button> : <Button kind="primary" busy={busy} disabled={value.assessment !== 'REVIEWABLE'} onClick={() => void onRun(async () => { const key = `jiejian.studio.propose:${projectId}:${candidate.candidate_id}:${candidate.revision}`, saved = sessionStorage.getItem(key); if (saved) {
        const receipt = await ruleCandidatesApi.receipt(projectId, saved);
        if (receipt.candidate)
            onChange(receipt.candidate);
        return;
    } const operation = crypto.randomUUID(); sessionStorage.setItem(key, operation); const next = await ruleCandidatesApi.propose(projectId, candidate.candidate_id, candidate.revision, operation); sessionStorage.removeItem(key); onChange(next); if (next.proposal_id)
        await onProposal(next.proposal_id); })}>生成权限提案</Button>}</div></section></>;
}
