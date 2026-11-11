import {ProposalQueue,RequirementQueue} from '../../entities/permission/ui/ProposalQueue'
import {markMilestone,useMilestone} from '../../shared/lib/milestone'
import {LegacyRepairRedirect} from '../../entities/check/ui/LegacyRepairRedirect'
import {usePageRefresh} from '../../shared/lib/pageRefresh'
import {PageSkeleton} from '../../shared/ui/PageSkeleton'
import './styles/permissions.css'
import './styles/rules.css'
import './workspace.css'
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import { businessBoundariesApi as api, type BoundaryProposalViewDto } from '../../entities/permission/api/businessBoundaries';
import { ruleCandidatesApi, type RuleCandidateView } from '../../entities/permission/api/ruleCandidates';
import { RuleEditor } from './RuleEditor';
import {ProposalReview} from './ProposalReview';
import {OfficialRules,OfficialRulesReady,matchesOfficialDraft} from './OfficialRules';
import { BusinessIssue } from './BusinessIssue';
import { RuleWorkbench } from './RuleWorkbench';
import { experienceApi,type OfficialBoundaryDraftDto } from '../../entities/application/api/experience';
import { assertProject, type PageProps } from '../../shared/model/page';
import {go,returnDestination,returnDestinationLabel,withReturnDestination,scopedPath} from '../../shared/lib/navigation'
import { text } from '../../shared/lib/format';
import {notAccepted} from '../../shared/lib/operations'
import { useRead } from '../../shared/lib/useRead';
import {Button,ActionLink} from '../../shared/ui/actions'
import { Heading } from "../../shared/ui/layout";
import {PageError,  Badge, InlineFeedback, Notice, Empty } from "../../shared/ui/feedback";
// 未知批准由原提案的持续恢复区说明，不重复弹出同一请求的全局错误。
class ApprovalResultUnknown extends Error {}
export function Permissions({ projectId, name, official, refresh, onError, route }: PageProps) {
    const origin=returnDestination(route.query.get('return_to'))
    const destination=(path:string)=>origin?withReturnDestination(path,origin):path
    const back=()=>go(origin??'/permissions')
    const backLabel=origin?returnDestinationLabel(origin):'全部权限规则'
    const editor = useRead('rules:' + projectId, async () => { const value = await api.editor(projectId); assertProject(value.project_id, projectId); return value; });
    const candidates = useRead('rule-candidates:' + projectId, () => ruleCandidatesApi.context(projectId));
    const [maintenance, setMaintenance] = useState(false), [proposal, setProposal] = useState<BoundaryProposalViewDto>(), [candidate, setCandidate] = useState<RuleCandidateView>(), [busy, setBusy] = useState(false), [ack, setAck] = useState(false), [uncertain, setUncertain] = useState(false), [notice, setNotice] = useState('');
    const pending = useRef(false), generation = useRef(0);
    const [approvedReceipt,setApprovedReceipt]=useState<string>();
    const approvalCompletion=useMilestone<HTMLDivElement>('rules:'+projectId,Boolean(approvedReceipt)&&!official,'rules');
    const acceptProposal=(value:BoundaryProposalViewDto)=>{
        assertProject(value.proposal.project_id,projectId);setProposal(value);
        const key=`jiejian.studio.approval:${projectId}:${value.proposal.proposal_id}`;
        if(value.decision){sessionStorage.removeItem(key);setUncertain(false);}
        else setUncertain(Boolean(sessionStorage.getItem(key)));
    };
    useEffect(() => () => { generation.current++; }, []);
    // 对象切换在可交互前清除旧确认，避免迟到的初始化覆盖用户刚完成的勾选。
    useLayoutEffect(() => { setAck(false); setUncertain(Boolean(proposal && sessionStorage.getItem(`jiejian.studio.approval:${projectId}:${proposal.proposal.proposal_id}`))); }, [proposal?.proposal.proposal_id]);
    useEffect(() => { const id = route.query.get('proposal_id'); if (id) {
        let valid = true;
        void api.proposal(projectId, id).then(value => { assertProject(value.proposal.project_id, projectId); if (value.proposal.proposal_id !== id)
            throw new Error('提案与所选记录不一致。'); if (valid)
            acceptProposal(value); }).catch(onError);
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
        if (epoch === generation.current && !(error instanceof ApprovalResultUnknown))
            onError(error);
    }
    finally {
        pending.current = false;
        if (epoch === generation.current)
            setBusy(false);
    } };
    const boundary = editor.data?.boundary;
    const openProposal = async (id: string) => { const value = await api.proposal(projectId, id); assertProject(value.proposal.project_id, projectId); setMaintenance(false); setProposal(value); go(destination('/permissions?proposal_id=' + encodeURIComponent(id))); };
    const approveProposal = async (target:BoundaryProposalViewDto) => { let submitted=false; try {
        sessionStorage.setItem(`jiejian.studio.approval:${projectId}:${target.proposal.proposal_id}`, 'pending');
        submitted=true;
        const value=await api.approve(projectId, target.proposal, '已核对完整提案中的访问要求、业务结果和沿用规则。');
        assertProject(value.project_id,projectId);
        sessionStorage.removeItem(`jiejian.studio.approval:${projectId}:${target.proposal.proposal_id}`);
        setNotice('权限规则已批准。后续检查将按这份提案核对，受影响的材料会重新检查。');
        markMilestone('rules:'+projectId);
        setApprovedReceipt(target.proposal.proposal_id);
        setUncertain(false);
        editor.reload();
        refresh();
        try{acceptProposal(await api.proposal(projectId,target.proposal.proposal_id));}
        catch{setNotice('权限规则已批准，确认回执已保留。提案详情暂未更新，可以继续原检查。');}
    }
    catch (error) {
        if(!submitted||notAccepted(error)){
            sessionStorage.removeItem(`jiejian.studio.approval:${projectId}:${target.proposal.proposal_id}`);
            setUncertain(false);setAck(false);
        }else {setUncertain(true);throw new ApprovalResultUnknown();}
        throw error;
    } };
    const approved = async () => {if(proposal&&!pending.current)await act(()=>approveProposal(proposal));};
    const approveOfficial=async(draft:OfficialBoundaryDraftDto,choice:boolean)=>{
        if(pending.current)return;
        sessionStorage.setItem('jiejian.studio.official-review:'+projectId,'pending');
        await act(async()=>{
            let value:BoundaryProposalViewDto;
            try{value=await experienceApi.boundaryProposal(choice);assertProject(value.proposal.project_id,projectId);}
            catch(error){setUncertain(true);throw error;}
            sessionStorage.removeItem('jiejian.studio.official-review:'+projectId);
            setProposal(value);go(destination('/permissions?proposal_id='+encodeURIComponent(value.proposal.proposal_id)));
            // 只批准刚才完整展示的命令；依据或内容发生变化时留在原提案重新核对。
            if(!matchesOfficialDraft(draft,value.proposal)||value.review?.basis_state!=='COMPLETE'||value.review.current_state_changed||value.proposal.unresolved_questions?.length){
                onError(new Error('预置规则或其依据已变化，请核对当前提案后再批准。'));return;
            }
            if(value.decision){if(value.decision.decision==='APPROVED'){setApprovedReceipt(value.proposal.proposal_id);editor.reload();refresh();}return;}
            await approveProposal(value);
            sessionStorage.removeItem('jiejian.studio.official-choice:'+projectId);
        });
    };
    const readDecision = () => void act(async () => { if (!proposal)
        return; const value = await api.proposal(projectId, proposal.proposal.proposal_id, true); assertProject(value.proposal.project_id, projectId);
        if(value.proposal.proposal_id!==proposal.proposal.proposal_id)throw new Error('查询结果与当前提案不一致。');
        // 先查询原提案；无决定时只恢复人工确认，不自动重放批准或改用另一份提案。
        sessionStorage.removeItem(`jiejian.studio.approval:${projectId}:${value.proposal.proposal_id}`);
        acceptProposal(value);setUncertain(false);setAck(false);
        if(!value.decision)setNotice('尚未形成批准决定。请重新核对这份提案，再确认是否批准。');
        if (value.decision) {
        setNotice('');
        if(value.decision.decision==='APPROVED'){markMilestone('rules:'+projectId);setApprovedReceipt(value.proposal.proposal_id);}
        editor.reload();
        refresh();
    } });
    if(route.query.has('repair_reference')||route.query.get('view')==='repair')return <LegacyRepairRedirect projectId={projectId} route={route}/>;
    if (proposal) {
        const review = proposal.review;
        const blocked = Boolean(!review || review.basis_state !== 'COMPLETE' || review.current_state_changed || proposal.proposal.unresolved_questions?.length);
        const accepted = proposal.decision?.decision === 'APPROVED'||approvedReceipt===proposal.proposal.proposal_id;
        const decided=Boolean(proposal.decision)||accepted;
        if(official&&accepted)return <OfficialRulesReady projectId={projectId} origin={origin} onRules={()=>{setProposal(undefined);go(destination('/permissions'));}}/>;
        return <ProposalReview key={proposal.proposal.proposal_id} value={proposal} backLabel={backLabel} onBack={() => { setProposal(undefined); back(); }}>
        <footer className="jj-approval-footer">
          {blocked && !decided && <Notice tone="caution">{review?.current_state_changed ? '当前业务已变化，请重新整理提案。' : proposal.proposal.unresolved_questions?.length ? proposal.proposal.unresolved_questions.map(text).join('；') : '原始依据不完整，暂时无法批准。'}</Notice>}
          {decided ? <div ref={approvalCompletion} className="jj-approval-decision"><p data-milestone-part="facts">{accepted ? notice||'这些规则已用于后续检查。返回原检查后，会重新核对所需材料。' : '这份提案未被采用，现有权限保持原样。'}</p><div data-milestone-part="actions"><ActionLink navigationScope="page" href={'#'+scopedPath(origin??(accepted?'/preparation':'/permissions'),projectId)} kind="primary">{origin?returnDestinationLabel(origin):accepted?'准备检查材料':'查看当前规则'}</ActionLink></div></div> : <>
            {uncertain?<Notice tone="caution" title="批准结果待确认" actions={<Button kind="quiet" busy={busy} busyLabel="正在查询" onClick={readDecision}>查询这次批准</Button>}>先查询这份提案的批准决定。查询会保留原提案，不会再次批准。</Notice>:<>
            <div className="jj-approval-choice"><h3>确认整份提案</h3><p>批准后，界鉴会按这些规则检查应用，不会修改应用自身的权限配置。</p>{notice&&<p role="status">{notice}</p>}<label className="jj-checkbox"><input type="checkbox" checked={ack} disabled={busy} onChange={event => setAck(event.target.checked)}/><span>我已核对全部访问规则及业务定义</span></label></div>
            <div className="jj-review-buttons jj-task-actions"><Button disabled={busy} onClick={() => void act(async () => { const value=await api.reject(projectId, proposal.proposal, '用户放弃本次权限提案'); acceptProposal(value); editor.reload(); refresh(); })}>放弃提案</Button><Button kind="primary" busy={busy} disabled={!ack || blocked} onClick={() => void approved()}>批准权限规则</Button></div>
            </>}
          </>}
        </footer>
    </ProposalReview>;
    }
    if (editor.loading)
        return <PageSkeleton view="/permissions"/>;
    if (editor.error || !boundary)
        return <PageError title="权限与覆盖" error={editor.error}/>;
    if (maintenance)
        return <RuleEditor projectId={projectId} onBack={() => setMaintenance(false)} onProposal={openProposal} onError={onError}/>;
    if (candidate)
        return <CandidateReview value={candidate} projectId={projectId} busy={busy} onChange={setCandidate} onRun={act} backLabel={backLabel} onBack={() => {setCandidate(undefined);back()}} onProposal={openProposal}/>;
    const roles = boundary.actors.filter(actor => actor.effective_state === 'ACTIVE');
    const requirementQueue=<RequirementQueue items={candidates.data?.candidates??[]} busy={busy} onReview={(id,revision)=>void act(async()=>setCandidate(await ruleCandidatesApi.show(projectId,id,revision)))}/>;
    if(official&&!boundary.permission_intents.length&&!roles.length)return <OfficialRules projectId={projectId} name={name} busy={busy} uncertain={uncertain||Boolean(sessionStorage.getItem('jiejian.studio.official-review:'+projectId))} pending={editor.data?.pending_proposals??[]} onApprove={approveOfficial} onReview={id=>void act(()=>openProposal(id))} onRecover={editor.reload}/>;
    if (boundary.permission_intents.length)
        return <RuleWorkbench projectId={projectId} boundary={boundary} official={official} route={route} refresh={refresh} onError={onError} onManage={() => setMaintenance(true)} reviewActions={<>{editor.data?.pending_proposals.length ? <ProposalQueue items={editor.data.pending_proposals} busy={busy} onReview={id=>void act(()=>openProposal(id))}/> : null}{requirementQueue}</>}/>;
    return <><Heading eyebrow={`权限版本 ${boundary.policy_epoch}`} title="权限规则"/>{notice && <InlineFeedback tone="positive">{notice}<ActionLink navigationScope="page" href={'#'+scopedPath('/preparation')} kind="quiet">准备检查</ActionLink></InlineFeedback>}
    <ProposalQueue items={editor.data!.pending_proposals} busy={busy} onReview={id=>void act(()=>openProposal(id))}/>
    <Empty title="先写清楚访问要求" action={<Button kind="primary" onClick={()=>setMaintenance(true)}>编写权限要求</Button>}>已有业务名称会在编写时沿用。确认谁可以对哪些数据做什么后，再开始准备检查。</Empty>
    {requirementQueue}
  </>;
}
function CandidateReview({ value, projectId, busy, onChange, onRun, onBack, onProposal,backLabel }: {
    value: RuleCandidateView;
    projectId: string;
    busy: boolean;
    onChange: (value: RuleCandidateView) => void;
    onRun: (callback: () => Promise<unknown>) => Promise<void>;
    onBack: () => void;
    backLabel?:string;
    onProposal: (id: string) => Promise<void>;
}) {
    const candidate = value.candidate;
    usePageRefresh(()=>onRun(async()=>onChange(await ruleCandidatesApi.show(projectId,candidate.candidate_id))),!busy);
    return <><div><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={onBack}>{backLabel??'全部权限规则'}</Button></div><Heading eyebrow="整理业务要求" title="先澄清规则，再确认权限"/><section className="jj-panel"><p>{text(candidate.content.original_text)}</p>{value.issues.length>0&&<Notice tone="caution" title="仍需澄清的内容"><ul>{value.issues.map((issue,index)=><li key={index}>{text(issue.message)}</li>)}</ul></Notice>}{value.boundary_reviews?.map(issue => <BusinessIssue key={candidate.revision + ':' + issue.issue_id} projectId={projectId} value={value} issue={issue} busy={busy} onChange={onChange} onRun={onRun}/>)}{candidate.content.scenarios?.map(scenario => <fieldset className="jj-choice-field" key={scenario.scenario_id}><legend>{text(scenario.question)}</legend>{scenario.options.map(option => <Button key={option.option_id} disabled={busy} onClick={() => void onRun(async () => onChange(await ruleCandidatesApi.decide(projectId, candidate.candidate_id, candidate.revision, candidate.basis_id, crypto.randomUUID(), { scenario_id: scenario.scenario_id, scenario_fingerprint: scenario.scenario_fingerprint, action: 'SELECT', option_id: option.option_id })))}>{text(option.label)}</Button>)}</fieldset>)}{value.scope_review?.map(item => <article className="jj-review-rule jj-scope-review" key={item.source.requirement_id}><header><div className="jj-object-line"><h3>{text(item.source.title)}</h3><Badge>{item.status === 'CONFIRMED' ? '已确认' : '待确认范围'}</Badge></div></header><p>{text(item.source.interpretation)}</p>{item.status !== 'CONFIRMED' && <div className="jj-inline-actions">{([['IN_SCOPE', '纳入检查'], ['PREPARATION', '准备条件'], ['OUT_OF_SCOPE', '本次不覆盖'], ['DEFER', '稍后决定']] as const).map(([disposition, label]) => <Button key={disposition} disabled={busy} onClick={() => void onRun(async () => onChange(await ruleCandidatesApi.scope(projectId, candidate.candidate_id, candidate.revision, candidate.basis_id, crypto.randomUUID(), { requirement_id: item.source.requirement_id, requirement_fingerprint: item.fingerprint, disposition, requirement: item.source.interpretation, reason: '用户在业务要求审阅中明确选择范围', time_scope: 'CHECK_WINDOW' })))}>{label}</Button>)}</div>}</article>)}<div className="jj-task-actions">{value.proposal_id ? <Button kind="primary" busy={busy} onClick={() => void onRun(() => onProposal(value.proposal_id!))}>审阅权限提案</Button> : <Button kind="primary" busy={busy} disabled={value.assessment !== 'REVIEWABLE'} onClick={() => void onRun(async () => { const key = `jiejian.studio.propose:${projectId}:${candidate.candidate_id}:${candidate.revision}`, saved = sessionStorage.getItem(key); if (saved) {
        const receipt = await ruleCandidatesApi.receipt(projectId, saved);
        if (receipt.candidate)
            onChange(receipt.candidate);
        return;
    } const operation = crypto.randomUUID(); sessionStorage.setItem(key, operation); const next = await ruleCandidatesApi.propose(projectId, candidate.candidate_id, candidate.revision, operation); sessionStorage.removeItem(key); onChange(next); if (next.proposal_id)
        await onProposal(next.proposal_id); })}>生成权限提案</Button>}</div></section></>;
}
