import {useWorkflow} from '../../../shared/lib/workflow';
import { useEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import PlusOutlined from '@ant-design/icons/PlusOutlined';
import VideoCameraOutlined from '@ant-design/icons/VideoCameraOutlined';
import { preparationApi as api, type MaterialChange, type MaterialReference, type MaterialPreview } from '../../../entities/preparation/api/preparation';
import { recordingsApi, type RecordingViewDto, type RecordingCreateInput } from '../../../entities/preparation/api/recordings';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { date, text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { operationId, readPending, savePending } from '../../../shared/lib/operations';
import { Badge, ErrorNote, Loading, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import {Field,FormColumns,Heading,ObjectIdentity,TaskActions,TaskFrame,TaskStage} from "../../../shared/ui/layout"
import {Choice} from '../../../shared/ui/Choice';
import {OperationFlowEditor} from '../../../entities/preparation/ui/OperationFlowEditor';
import {useTaskSurfaceFocus} from '../../../shared/ui/TaskSurface';
import {OperationFlowSummary} from '../../../entities/preparation/ui/OperationFlowSummary';
import {RecordingProgress} from '../../../entities/preparation/ui/RecordingProgress';
import {RecordingSteps} from '../../../entities/preparation/ui/RecordingSteps';
import {recordingEnded,recordingNeedsPolling} from '../../../entities/preparation/model/recordingState';
import {operationFlowsApi,type OperationFlow} from '../../../entities/preparation/api/operationFlows';
import {testIdentitiesApi} from '../../../entities/preparation/api/testIdentities';
import { requiredVariables, sourceChoice } from './draft';
import {materialReasons} from './reasons';
type MaterialEditorProps = {
    projectId: string;
    reference: MaterialReference;
    label: string;
    actionName?: string;
    resumeRecordingId?: string;
    backLabel?: string;
    onBack: () => void;
    onError: (error: unknown) => void;
};
export function MaterialEditor(props: MaterialEditorProps) {
    const ref = props.reference;
    const identity = JSON.stringify([props.projectId, ref.action_id, ref.action_revision, ref.kind, ref.member_id]);
    // 材料身份变化时重建本地会话，防止把上一动作的选择、影响预览或未知回执带入新材料。
    return <MaterialEditorSession key={identity} {...props} pendingKey={'jiejian.studio.material:' + identity}/>;
}
function MaterialEditorSession({ projectId, reference, label, actionName, resumeRecordingId, backLabel='检查准备', onBack, onError, pendingKey }: MaterialEditorProps & {pendingKey: string}) {
    const workflow=useWorkflow();
    const [flowEditor,setFlowEditor]=useState(workflow?.route?.query.get('resume_draft')==='1'&&reference.kind==='execution');
    const [flowVisited,setFlowVisited]=useState(flowEditor),flowTitle=useRef<HTMLHeadingElement>(null);
    useTaskSurfaceFocus(flowEditor,flowTitle);
    const [editingFlow,setEditingFlow]=useState<OperationFlow>(),[recordingTools,setRecordingTools]=useState(false);
    const key = `material:${projectId}:${JSON.stringify(reference)}`;
    const state = useRead(key, () => api.material(projectId, reference));
    const flows=useRead(reference.kind==='evidence'?null:'material-flows:'+projectId,async(signal)=>{
        const [context,accounts]=await Promise.all([operationFlowsApi.context(projectId,signal),testIdentitiesApi.list(projectId,signal)]);
        return {context,accounts};
    });
    // 只认服务标记的在用修订及准确动作版本；不按名称、最新修订或相似资源推测绑定。
    const currentFlow=state.data&&!state.error?flows.data?.context.flows.find(item=>item.in_use&&item.document.business_action_id===reference.action_id&&item.document.action_revision===reference.action_revision&&(reference.kind!=='resource'||item.document.resource_owner_test_identity_id===reference.member_id))?.document:undefined;
    const currentAction=flows.data?.context.actions.find(item=>item.action_id===reference.action_id&&item.revision===reference.action_revision);
    const [selected, setSelected] = useState(''), [preview, setPreview] = useState<{
        change: MaterialChange;
        impact: MaterialPreview;
    }>(), [recording, setRecording] = useState<RecordingViewDto>(), [busy, setBusy] = useState(false), [confirmOwner, setConfirmOwner] = useState(false), [uncertain, setUncertain] = useState<string | undefined>(() => {
        const value = sessionStorage.getItem(pendingKey);
        return value && /^[0-9a-f]{32}$/.test(value) ? value : undefined;
    }), [captureUnknown, setCaptureUnknown] = useState(false);
    const captureKey = pendingKey + ':recording';
    type CaptureRequest = { operation: string; recordingId?: string; input?: RecordingCreateInput };
    const [capturePending, setCapturePending] = useState(() => readPending<CaptureRequest>(captureKey));
    const rememberCapture = (value?: CaptureRequest) => { savePending(captureKey, value); setCapturePending(value); };
    const mounted = useRef(true);
    useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
    const complete = (receipt: Awaited<ReturnType<typeof api.materialReceipt>>, operation: string) => {
        if (receipt.operation_id !== operation || !['SAVED', 'RECHECKED'].includes(receipt.result))
            throw new Error('返回的确认结果与这次操作不一致，请查看本次操作结果。');
        sessionStorage.removeItem(pendingKey);
        if (mounted.current) { setUncertain(undefined); onBack(); }
    };
    const [mode, setMode] = useState<'existing' | 'new'>('existing');
    const [duration,setDuration]=useState(120);
    const recordingId = recording?.recording?.recording_id ?? resumeRecordingId;
    const lock = useRef(false), active = useRead(recordingId ? 'recording:' + recordingId : null, async () => {
        if (!recordingId)
            return null;
        const value = await recordingsApi.recording(recordingId);
        assertProject(value.recording?.project_id ?? '', projectId);
        if (value.recording?.business_action_id !== reference.action_id || value.recording.action_revision !== reference.action_revision)
            throw new Error('录制属于另一项操作或原版本，请返回当前材料核对。');
        return value;
    }, value => recordingNeedsPolling(value?.recording?.state) ? 1000 : 0);
    const current = active.data ?? recording, details = state.data;
    const setup = useRead(details?.recording_context?.can_execute || recordingId ? 'recording-accounts:' + projectId : null, () => recordingsApi.setup(projectId));
    const act = async (callback: () => Promise<unknown>) => { if (lock.current)
        return; lock.current = true; setBusy(true); try {
        await callback();
    }
    catch (error) {
        if (mounted.current) onError(error);
    }
    finally {
        lock.current = false;
        if (mounted.current) setBusy(false);
    } };
    const recoverCapture = async (retry = false) => {
        // 已知 recordingId 就查原录制，否则查创建回执；只有显式恢复才重发原标识的请求。
        const saved = readPending<CaptureRequest>(captureKey);
        const value = saved?.recordingId ? await recordingsApi.recording(saved.recordingId) : saved ? await recordingsApi.receipt(projectId, saved.operation) : null;
        if (!value && retry && saved?.input) {
            const created = await recordingsApi.createRecording(projectId, saved.input, saved.operation);
            assertProject(created.recording?.project_id ?? '', projectId);
            setRecording(created); setCaptureUnknown(false); rememberCapture({ ...saved, recordingId: created.recording!.recording_id });
        }
        if (value?.recording) {
            assertProject(value.recording.project_id, projectId);
            setRecording(value); setCaptureUnknown(false);
            if (recordingEnded(value.recording.state)) rememberCapture();
            else if (saved) rememberCapture({ ...saved, recordingId: value.recording.recording_id });
            active.reload(); state.reload();
        }
    };
    useEffect(() => { if (readPending(captureKey)) void act(() => recoverCapture()); }, [captureKey]);
    // 预览保留同一份变更命令，确认时提交其原指纹；后端负责拒绝预览之后发生的材料漂移。
    const choose = () => void act(async () => { if (!details)
        return; const change: MaterialChange = { schema_version: '1', operation_id: crypto.randomUUID().replaceAll('-', ''), material: reference, expected_fingerprint: details.expected_fingerprint, candidate_recording_id: selected }; setPreview({ change, impact: await api.previewMaterial(projectId, change) }); });
    const draft = current?.draft ?? current?.recording?.draft, target = draft?.steps.find(step => step.id === draft.target_step_id), variables = requiredVariables(draft);
    const supplement = Boolean(current?.recording?.purpose && current.recording.purpose !== 'TARGET'), choices = current?.supplement_choices ?? current?.recording?.supplement_choices ?? [];
    const review = (command: Record<string, unknown>) => void act(async () => { if (!current?.recording)
        return; setRecording(await recordingsApi.reviewRecording(current.recording.recording_id, command)); active.reload(); });
    const reviewLocked=busy||Boolean(active.error);
    const canSave = !active.error && current?.recording?.state === 'PENDING_REVIEW' && Boolean(draft) && (supplement ? choices.length === 1 || choices.some(item => item.step_id === draft?.target_step_id) : Boolean(draft?.target_step_id && draft.resource_candidate_id) && variables.every(item => item.status === 'CONFIRMED'));
    const capture = (kind: 'start' | 'stop') => void act(async () => { if (!current?.recording)
        return; try {
        const value = await (kind === 'start' ? recordingsApi.startCapture : recordingsApi.stopCapture)(current.recording.recording_id);
        setRecording(value);
        active.reload();
    }
    catch (error) {
        if (!(error instanceof ApiError))
            setCaptureUnknown(true);
        active.reload();
        throw error;
    } });
    const creating = mode === 'new' || !details?.candidates.length;
    const openFlow=()=>{if(!flowVisited)setEditingFlow(currentFlow);setFlowVisited(true);setFlowEditor(true)};
    return <><TaskFrame className="jj-material-page" hidden={flowEditor}><div className="jj-back-link"><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} disabled={busy} onClick={onBack}>{workflow?.finishLabel??backLabel}</Button></div><Heading eyebrow={actionName ? text(actionName) : undefined} title={label}/>
    {details&&!state.error&&!current?.recording&&<div className="jj-material-status"><p className="jj-small jj-muted">{details.status==='SATISFIED'?(details.reuse_basis==='VERIFIED_SOURCE_CONTRACT'?'运行代码已更新，所依赖的来源合同与实现绑定仍一致，这份材料可以继续使用。':'这份材料已按当前来源和绑定核对，可以继续使用；需要更换时再选择或录制。'):materialReasons(details.reason_codes).join('；')+'。'}</p>{details.retained&&<Badge>原记录已保留</Badge>}</div>}
    {flows.error&&<ErrorNote error={flows.error} onRetry={flows.reload} retryLabel="重新读取操作流程与材料"/>}
    {currentFlow&&flows.data&&!current?.recording&&!recordingTools&&<section className="jj-material-current" aria-label="当前使用的流程材料"><header><ObjectIdentity name={<h2>当前使用的材料</h2>} status={<Badge>第 {currentFlow.revision} 修订</Badge>}/><p className="jj-small jj-muted">{reference.kind==='resource'?'下列数据与所有者已随流程保存。需要更换时，在流程中一起核对账号与执行安排。':reference.kind==='recovery'?'恢复安排随流程保存，用于检查结束后的处理。实际恢复反馈在试运行和正式检查中分别查看。':'先核对已采用的账号、执行顺序和恢复安排，再决定是否修改。'}</p></header><OperationFlowSummary flow={currentFlow} accounts={flows.data.accounts} focus={reference.kind==='evidence'?undefined:reference.kind} actionLabel={currentAction?.label??actionName??"原业务操作（请核对当前资料）"} effects={currentAction?.effects} stateChanging={currentAction?.state_changing}/><TaskActions separated><Button kind="quiet" disabled={busy||Boolean(uncertain)} onClick={()=>setRecordingTools(true)}>改用操作录制</Button><Button onClick={openFlow}>{reference.kind==='resource'?'核对或更换测试数据':reference.kind==='recovery'?'编辑恢复安排':'核对或编辑流程'}</Button></TaskActions></section>}
    {state.loading||flows.loading ? <Loading page/> : state.error ? <ErrorNote error={state.error} onRetry={state.reload} retryLabel="重新读取操作流程与材料"/> : details && !current?.recording && (!currentFlow||recordingTools||Boolean(uncertain)) && <section className="jj-recording-workspace" aria-label="操作录制">
      <header className="jj-recording-toolbar"><h2>{preview?'确认这份录制的用途':creating ? reference.kind==='resource'?'准备本次测试数据':'录制新操作' : '选择已有录制'}</h2>{!preview&&details.candidates.length > 0 && <Button kind="quiet" disabled={busy || Boolean(uncertain) || captureUnknown} icon={creating ? <ArrowLeftOutlined aria-hidden="true"/> : <PlusOutlined aria-hidden="true"/>} onClick={() => { setMode(creating ? 'existing' : 'new'); setPreview(undefined); }}>{creating ? '已有录制' : '新建录制'}</Button>}</header>
      {creating ? <div className="jj-recording-setup"><div className="jj-recording-instruction"><VideoCameraOutlined aria-hidden="true"/><p>{reference.kind==='resource'?'在独立浏览器中准备本次操作要使用的测试数据，结束后核对数据标识与归属。':'在独立浏览器中完成一次业务操作，结束后核对步骤与资源。'}</p></div>{details.recording_context?.can_execute ? <><dl className="jj-facts jj-recording-participants" data-layout="columns"><div><dt>操作账号</dt><dd>{text(setup.data?.test_identity_options.find(item => item.test_identity_id === details.recording_context!.subject_test_identity_id)?.label ?? '正在核对账号')}</dd></div><div><dt>资源所有者</dt><dd>{text(setup.data?.test_identity_options.find(item => item.test_identity_id === details.recording_context!.resource_owner_test_identity_id)?.label ?? '正在核对账号')}</dd></div></dl><Field label="录制时间上限" measure="compact"><Choice value={String(duration)} measure="compact" disabled={busy||Boolean(capturePending)} onValueChange={value=>setDuration(Number(value))}><option value="120">2 分钟</option><option value="300">5 分钟</option><option value="600">10 分钟</option></Choice></Field>{setup.error && <ErrorNote error={setup.error} onRetry={setup.reload} retryLabel="重新读取操作流程与材料"/>}<label className="jj-checkbox"><input type="checkbox" checked={confirmOwner} onChange={event => setConfirmOwner(event.target.checked)}/><span>我已核对本次操作账号与资源所有者</span></label><div className="jj-recording-actions"><Button kind="primary" disabled={!confirmOwner || busy || captureUnknown || Boolean(capturePending) || !setup.data || Boolean(setup.error)} busy={busy} onClick={() => void act(async () => { const c = details.recording_context!; try {
                const operation = operationId();
                const input: RecordingCreateInput = { material_candidate: true, business_action_id: c.business_action_id, action_revision: c.action_revision, subject_test_identity_id: c.subject_test_identity_id, resource_owner_test_identity_id: c.resource_owner_test_identity_id, subject_slot_id: c.subject_slot_id, resource_owner_slot_id: c.resource_owner_slot_id, resource_owner_confirmed: true, duration_seconds: duration, purpose: c.recording_purpose, parent_recording_id: c.parent_recording_id, effect_id: c.effect_id };
                rememberCapture({ operation, input });
                const value = await recordingsApi.createRecording(projectId, input, operation);
                assertProject(value.recording?.project_id ?? '', projectId);
                rememberCapture({ operation, recordingId: value.recording!.recording_id });
                setRecording(value);
            }
            catch (error) {
                if (!(error instanceof ApiError))
                    setCaptureUnknown(true);
                else rememberCapture();
                throw error;
            } })}>建立本次录制</Button></div></> : <Notice tone="caution">当前还不能录制，请先核对账号、权限与资源条件。<Button kind="quiet" onClick={onBack}>返回核对准备条件</Button></Notice>}</div> : <>
        {!preview&&<fieldset className="jj-recording-list" aria-label="已有操作录制">{details.candidates.map((item, index) => <label key={item.recording_id}><input type="radio" name="material-recording" value={item.recording_id} checked={selected === item.recording_id} disabled={busy || Boolean(uncertain)} onChange={() => { setSelected(item.recording_id); setPreview(undefined); }}/><ObjectIdentity name={<strong>{item.recording_id === details.source_recording_id ? '已用于检查的录制' : `操作记录 ${index + 1}`}</strong>} status={<Badge tone={item.current ? 'positive' : 'neutral'}>{item.current ? '当前版本' : '需重新核对'}</Badge>}/>{item.captured_at_us && <time dateTime={new Date(item.captured_at_us / 1000).toISOString()}>{date(item.captured_at_us)}</time>}</label>)}</fieldset>}
        {preview && <div className="jj-material-impact"><FormColumns><section><h3>使用后将更新的材料</h3><ul>{preview.impact.updates.map((item, index) => <li key={index}>{({ execution: '操作录制', resource: '测试资源', evidence: '业务结果证明', recovery: '操作恢复' })[item.kind]}</li>)}</ul></section><section><h3>保留与后续核对</h3>{preview.impact.retained.length>0&&<p>保留 {preview.impact.retained.length} 项其他材料。</p>}{preview.impact.recheck.length > 0 && <p>{preview.impact.recheck.length} 项相关材料将重新核对。</p>}<p>已有检查与报告继续保留。采用后，检查前仍会核对当前来源与账号。</p></section></FormColumns></div>}
        <footer className="jj-recording-actions">{uncertain ? <Notice tone="caution">还未确认这份录制是否已用于检查。<Button busy={busy} onClick={() => void act(async () => { complete(await api.materialReceipt(projectId, uncertain), uncertain); })} busyLabel="正在查询">查看本次使用结果</Button></Notice> : <>{preview && <Button disabled={busy} onClick={() => setPreview(undefined)}>返回选择</Button>}<Button kind="primary" busy={busy} disabled={!selected} onClick={preview ? () => void act(async () => {
                const operation = preview.change.operation_id;
                sessionStorage.setItem(pendingKey, operation);
                setUncertain(operation);
                try {
                complete(await api.saveMaterial(projectId, preview.change), operation);
            }
            catch (error) {
                if (error instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID', 'RECORD_NOT_FOUND'].includes(error.code)) {
                    sessionStorage.removeItem(pendingKey);
                    if (mounted.current) setUncertain(undefined);
                }
                throw error;
            } }) : choose}>{preview ? '确认使用这份录制' : '核对后用于检查'}</Button></>}</footer>
      </>}
    </section>}
    {!preview&&!current?.recording&&reference.kind!=='evidence'&&(!currentFlow||recordingTools)&&<TaskActions separated note="接口流程可以复用已保存的账号、执行请求和恢复安排。">{currentFlow&&<Button kind="quiet" disabled={busy||Boolean(uncertain)} onClick={()=>setRecordingTools(false)}>返回当前材料</Button>}<Button disabled={busy||Boolean(uncertain)||captureUnknown} onClick={openFlow}>接口方式设置</Button></TaskActions>}
    {(captureUnknown || capturePending && !current) && <Notice tone="caution">录制操作尚未确认。<Button busy={busy} onClick={() => void act(() => recoverCapture(true))} busyLabel="正在查询">查询并恢复本次录制</Button></Notice>}
    {current?.recording && <RecordingProgress view={current} action={actionName??current.action?.display_name??'当前业务操作'} accounts={setup.data?.test_identity_options??[]} busy={busy} uncertain={captureUnknown} error={active.error} onRefresh={active.reload} onBack={onBack} onStart={()=>capture('start')} onStop={()=>capture('stop')} onCancel={()=>void act(async()=>{const job=current.job??current.recording!.job;if(job)await recordingsApi.cancel(job.job_id);active.reload()})}>
      {draft&&current.recording.state==='PENDING_REVIEW'?<div className="jj-recording-review">
        <TaskStage context={<RecordingSteps draft={draft} action={actionName??current.action?.display_name??'当前业务操作'}/>}><div className="jj-recording-decisions">
        {(supplement ? choices.length > 1 : !draft.target_step_id) && <fieldset className="jj-choice-field"><legend>哪一步完成了这项业务？</legend>{(supplement ? choices : draft.steps.map(step => ({ step_id: step.id, label: step.name }))).map(step => <label key={step.step_id}><input type="radio" checked={draft.target_step_id === step.step_id} disabled={reviewLocked} onChange={() => review({ operation: 'CONFIRM_TARGET_STEP', step_id: step.step_id })}/><span>{text(step.label)}</span></label>)}</fieldset>}
        {!supplement && target && <fieldset className="jj-choice-field"><legend>操作对应哪个资源？</legend>{target.resource_candidates.map(item => <label key={item.candidate_id}><input type="radio" checked={draft.resource_candidate_id === item.candidate_id} disabled={reviewLocked} onChange={() => review({ operation: 'CONFIRM_RESOURCE_SLOT', candidate_id: item.candidate_id, expected_revision: draft.revision })}/><span>{text(item.label)}</span></label>)}{!target.resource_candidates.length && <p className="jj-field-guidance" role="status">未找到可确认的业务对象。请核对已有录制中的完整响应。</p>}<Button disabled={reviewLocked} onClick={() => review({ operation: 'REFRESH_RESOURCE_CANDIDATES', expected_revision: draft.revision })}>重新识别已有录制</Button></fieldset>}
        {!supplement && variables.filter(item => item.status !== 'CONFIRMED').map(variable => <fieldset className="jj-choice-field" key={variable.name}><legend>“{text(variable.name)}”来自哪一步？</legend>{variable.candidate_sources.map((source, index) => <Button key={index} disabled={reviewLocked} onClick={() => void act(async () => { setRecording(await recordingsApi.reviewRecording(current.recording!.recording_id, { operation: 'CONFIRM_VARIABLE_CHOICE', variable_name: variable.name, choice_id: await sourceChoice(source) })); active.reload(); })}>{text(draft.steps.find(step => step.id === source.source_step_id)?.name ?? `前序步骤 ${index + 1}`)}</Button>)}{!variable.candidate_sources.length && <p className="jj-field-guidance" role="status">现有录制缺少这个值的来源。</p>}</fieldset>)}
        {supplement && !choices.length && <Notice tone="caution">这份补充录制中没有可用于检查的业务步骤。</Notice>}
        {canSave&&<p className="jj-recording-ready-note">{supplement?'已对应可用的补充步骤。':'业务操作、资源和必要的前序来源已齐备。'}保存后回到原材料，再核对是否用于检查。</p>}
        </div>
        <TaskActions><Button kind="quiet" busy={busy} disabled={Boolean(active.error)||current.recording.state !== 'PENDING_REVIEW'} onClick={() => void act(async () => { await recordingsApi.discard(current.recording!.recording_id); rememberCapture(); setRecording(undefined); state.reload(); })}>放弃这份录制</Button><Button kind="primary" busy={busy} disabled={!canSave || captureUnknown} onClick={() => void act(async () => { await recordingsApi.finalizeRecording(current.recording!.recording_id); state.reload(); rememberCapture(); setRecording(undefined); })}>保存这次操作</Button></TaskActions></TaskStage>
      </div>:undefined}
    </RecordingProgress>}
    </TaskFrame>{flowVisited&&<div hidden={!flowEditor}><OperationFlowEditor projectId={projectId} actionId={reference.action_id} initialFlow={editingFlow} titleRef={flowTitle} backLabel="返回当前材料" onBack={()=>{setFlowEditor(false);state.reload();flows.reload()}}/></div>}
  </>;
}
