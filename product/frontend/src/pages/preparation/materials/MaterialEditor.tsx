import { useEffect, useRef, useState } from 'react';
import { ArrowLeftOutlined, PlusOutlined, VideoCameraOutlined } from '@ant-design/icons';
import { preparationApi as api, type MaterialChange, type MaterialReference, type MaterialPreview } from '../../../entities/preparation/api/preparation';
import { recordingsApi, type RecordingViewDto, type RecordingCreateInput } from '../../../entities/preparation/api/recordings';
import { ApiError } from '../../../shared/api/http';
import { assertProject } from '../../../shared/model/page';
import { date, text } from '../../../shared/lib/format';
import { useRead } from '../../../shared/lib/useRead';
import { operationId, readPending, savePending } from '../../../shared/lib/operations';
import { Badge, ErrorNote, Loading, Notice } from "../../../shared/ui/feedback";
import { Button } from "../../../shared/ui/actions";
import { Heading } from "../../../shared/ui/layout";
import { requiredVariables, sourceChoice } from './draft';
const recordingLabels: Record<string, string> = { STARTING: '正在打开浏览器', RECORDING: '浏览器已打开', PROCESSING: '正在整理操作', PENDING_REVIEW: '等待核对', COMPLETED: '已保存', FAILED: '录制未完成', CANCELLED: '已放弃' };
type MaterialEditorProps = {
    projectId: string;
    reference: MaterialReference;
    label: string;
    actionName?: string;
    resumeRecordingId?: string;
    onBack: () => void;
    onError: (error: unknown) => void;
};
export function MaterialEditor(props: MaterialEditorProps) {
    const ref = props.reference;
    const identity = JSON.stringify([props.projectId, ref.action_id, ref.action_revision, ref.kind, ref.member_id]);
    // 材料身份变化时重建本地会话，防止把上一动作的选择、影响预览或未知回执带入新材料。
    return <MaterialEditorSession key={identity} {...props} pendingKey={'jiejian.studio.material:' + identity}/>;
}
function MaterialEditorSession({ projectId, reference, label, actionName, resumeRecordingId, onBack, onError, pendingKey }: MaterialEditorProps & {pendingKey: string}) {
    const key = `material:${projectId}:${JSON.stringify(reference)}`;
    const state = useRead(key, () => api.material(projectId, reference));
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
            throw new Error('采用回执与本次操作不匹配，请查询原操作。');
        sessionStorage.removeItem(pendingKey);
        if (mounted.current) { setUncertain(undefined); onBack(); }
    };
    const [mode, setMode] = useState<'existing' | 'new'>('existing');
    const recordingId = recording?.recording?.recording_id ?? resumeRecordingId;
    const lock = useRef(false), active = useRead(recordingId ? 'recording:' + recordingId : null, async () => {
        if (!recordingId)
            return null;
        const value = await recordingsApi.recording(recordingId);
        assertProject(value.recording?.project_id ?? '', projectId);
        if (value.recording?.business_action_id !== reference.action_id || value.recording.action_revision !== reference.action_revision)
            throw new Error('录制属于另一项操作或原版本，请返回当前材料核对。');
        return value;
    }, value => value?.recording && !['COMPLETED', 'FAILED', 'CANCELLED', 'PENDING_REVIEW'].includes(value.recording.state) ? 1000 : 0);
    const current = active.data ?? recording, details = state.data;
    const setup = useRead(details?.recording_context?.can_execute ? 'recording-accounts:' + projectId : null, () => recordingsApi.setup(projectId));
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
            if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(value.recording.state)) rememberCapture();
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
    const canSave = current?.recording?.state === 'PENDING_REVIEW' && Boolean(draft) && (supplement ? choices.length === 1 || choices.some(item => item.step_id === draft?.target_step_id) : Boolean(draft?.target_step_id && draft.resource_candidate_id) && variables.every(item => item.status === 'CONFIRMED'));
    const phase = current?.capture_phase ?? current?.recording?.capture_phase;
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
    return <><div><Button kind="quiet" icon={<ArrowLeftOutlined aria-hidden="true"/>} disabled={busy} onClick={onBack}>检查准备</Button></div><Heading eyebrow={actionName ? text(actionName) : undefined} title={label}/>
    {state.loading ? <Loading page/> : state.error ? <ErrorNote error={state.error} onRetry={state.reload}/> : details && !current?.recording && <section className="jj-recording-workspace" aria-label="操作录制">
      <header className="jj-recording-toolbar"><h2>{creating ? '录制新操作' : '选择已有录制'}</h2>{details.candidates.length > 0 && <Button kind="quiet" disabled={busy || Boolean(uncertain) || captureUnknown} icon={creating ? <ArrowLeftOutlined aria-hidden="true"/> : <PlusOutlined aria-hidden="true"/>} onClick={() => { setMode(creating ? 'existing' : 'new'); setPreview(undefined); }}>{creating ? '已有录制' : '新建录制'}</Button>}</header>
      {creating ? <div className="jj-recording-setup"><div className="jj-recording-instruction"><VideoCameraOutlined aria-hidden="true"/><p>在独立浏览器中完成一次业务操作，结束后核对步骤与资源。</p></div>{details.recording_context?.can_execute ? <><dl className="jj-recording-participants"><div><dt>操作账号</dt><dd>{text(setup.data?.test_identity_options.find(item => item.test_identity_id === details.recording_context!.subject_test_identity_id)?.label ?? '正在核对账号')}</dd></div><div><dt>资源所有者</dt><dd>{text(setup.data?.test_identity_options.find(item => item.test_identity_id === details.recording_context!.resource_owner_test_identity_id)?.label ?? '正在核对账号')}</dd></div></dl>{setup.error && <ErrorNote error={setup.error} onRetry={setup.reload}/>}<label className="jj-checkbox"><input type="checkbox" checked={confirmOwner} onChange={event => setConfirmOwner(event.target.checked)}/><span>我已核对本次操作账号与资源所有者</span></label><div className="jj-recording-actions"><Button kind="primary" disabled={!confirmOwner || busy || captureUnknown || Boolean(capturePending) || !setup.data || Boolean(setup.error)} busy={busy} onClick={() => void act(async () => { const c = details.recording_context!; try {
                const operation = operationId();
                const input: RecordingCreateInput = { material_candidate: true, business_action_id: c.business_action_id, action_revision: c.action_revision, subject_test_identity_id: c.subject_test_identity_id, resource_owner_test_identity_id: c.resource_owner_test_identity_id, subject_slot_id: c.subject_slot_id, resource_owner_slot_id: c.resource_owner_slot_id, resource_owner_confirmed: true, duration_seconds: 120, purpose: c.recording_purpose, parent_recording_id: c.parent_recording_id, effect_id: c.effect_id };
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
            } })}>建立本次录制</Button></div></> : <Notice>当前还不能录制，请先核对账号、权限与资源条件。</Notice>}</div> : <>
        <fieldset className="jj-recording-list" aria-label="已有操作录制">{details.candidates.map((item, index) => <label key={item.recording_id}><input type="radio" name="material-recording" value={item.recording_id} checked={selected === item.recording_id} disabled={busy || Boolean(uncertain)} onChange={() => { setSelected(item.recording_id); setPreview(undefined); }}/><strong>{item.recording_id === details.source_recording_id ? '已采用的录制' : `操作记录 ${index + 1}`}</strong>{item.captured_at_us && <time dateTime={new Date(item.captured_at_us / 1000).toISOString()}>{date(item.captured_at_us)}</time>}<Badge tone={item.current ? 'positive' : 'neutral'}>{item.current ? '当前版本' : '需重新核对'}</Badge></label>)}</fieldset>
        {preview && <div className="jj-material-impact"><h3>采用后需要更新的材料</h3><ul>{preview.impact.updates.map((item, index) => <li key={index}>{({ execution: '操作录制', resource: '测试资源', evidence: '业务结果证明', recovery: '操作恢复' })[item.kind]}</li>)}</ul>{preview.impact.recheck.length > 0 && <p>{preview.impact.recheck.length} 项相关材料将重新核对。</p>}</div>}
        <footer className="jj-recording-actions">{uncertain ? <Notice>采用结果尚未确认。<Button busy={busy} onClick={() => void act(async () => { complete(await api.materialReceipt(projectId, uncertain), uncertain); })}>查询本次采用</Button></Notice> : <>{preview && <Button disabled={busy} onClick={() => setPreview(undefined)}>返回选择</Button>}<Button kind="primary" busy={busy} disabled={!selected} onClick={preview ? () => void act(async () => {
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
            } }) : choose}>{preview ? '采用这份记录' : '核对采用影响'}</Button></>}</footer>
      </>}
    </section>}
    {(captureUnknown || capturePending && !current) && <Notice>录制操作尚未确认。<Button busy={busy} onClick={() => void act(() => recoverCapture(true))}>查询并恢复本次录制</Button></Notice>}
    {current?.recording && <section className="jj-panel jj-recording-live"><div className="jj-panel-heading"><h2>本次操作录制</h2><Badge>{recordingLabels[current.recording.state] ?? '状态待确认'}</Badge></div>{active.error && <ErrorNote error={active.error} onRetry={active.reload}/>}
      {!draft ? <div className="jj-inline-actions">{phase === 'AWAITING_CAPTURE' && <Button busy={busy} disabled={captureUnknown} onClick={() => capture('start')}>开始记录这个操作</Button>}{phase === 'CAPTURING' && <Button busy={busy} disabled={captureUnknown} onClick={() => capture('stop')}>我已完成这个操作</Button>}{!['AWAITING_CAPTURE', 'CAPTURING'].includes(phase ?? '') && <p className="jj-small jj-muted">正在等待浏览器或整理录制结果。</p>}{current.job && !['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(current.job.state) && <Button busy={busy} onClick={() => void act(async () => { await recordingsApi.cancel(current.job!.job_id); active.reload(); })}>取消本次录制</Button>}</div> : <>
        {(supplement ? choices.length > 1 : !draft.target_step_id) && <fieldset className="jj-choice-field"><legend>哪一步完成了这项业务？</legend>{(supplement ? choices : draft.steps.map(step => ({ step_id: step.id, label: step.name }))).map(step => <label key={step.step_id}><input type="radio" checked={draft.target_step_id === step.step_id} disabled={busy} onChange={() => review({ operation: 'CONFIRM_TARGET_STEP', step_id: step.step_id })}/><span>{text(step.label)}</span></label>)}</fieldset>}
        {!supplement && target && <fieldset className="jj-choice-field"><legend>操作对应哪个资源？</legend>{target.resource_candidates.map(item => <label key={item.candidate_id}><input type="radio" checked={draft.resource_candidate_id === item.candidate_id} disabled={busy} onChange={() => review({ operation: 'CONFIRM_RESOURCE_SLOT', candidate_id: item.candidate_id, expected_revision: draft.revision })}/><span>{text(item.label)}</span></label>)}{!target.resource_candidates.length && <Notice>未找到可确认的业务对象。请核对已有录制中的完整响应。</Notice>}<Button disabled={busy} onClick={() => review({ operation: 'REFRESH_RESOURCE_CANDIDATES', expected_revision: draft.revision })}>重新识别已有录制</Button></fieldset>}
        {!supplement && variables.filter(item => item.status !== 'CONFIRMED').map(variable => <fieldset className="jj-choice-field" key={variable.name}><legend>“{text(variable.name)}”来自哪一步？</legend>{variable.candidate_sources.map((source, index) => <Button key={index} disabled={busy} onClick={() => void act(async () => { setRecording(await recordingsApi.reviewRecording(current.recording!.recording_id, { operation: 'CONFIRM_VARIABLE_CHOICE', variable_name: variable.name, choice_id: await sourceChoice(source) })); active.reload(); })}>{text(draft.steps.find(step => step.id === source.source_step_id)?.name ?? `前序步骤 ${index + 1}`)}</Button>)}{!variable.candidate_sources.length && <Notice>现有录制缺少这个值的来源。</Notice>}</fieldset>)}
        {supplement && !choices.length && <Notice>这份补录没有可采用的业务步骤。</Notice>}
        <div className="jj-confirmation-actions"><Button busy={busy} disabled={current.recording.state !== 'PENDING_REVIEW'} onClick={() => void act(async () => { await recordingsApi.discard(current.recording!.recording_id); rememberCapture(); setRecording(undefined); state.reload(); })}>放弃未采用的录制</Button><Button kind="primary" busy={busy} disabled={!canSave || captureUnknown} onClick={() => void act(async () => { await recordingsApi.finalizeRecording(current.recording!.recording_id); state.reload(); rememberCapture(); setRecording(undefined); })}>保存这次操作</Button></div>
      </>}
    </section>}
  </>;
}
