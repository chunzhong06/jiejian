import { useEffect, useRef, useState } from 'react';
import { projectsApi as api, type RuntimePreview } from '../../entities/application/api/projects';
import { useRead } from '../../shared/lib/useRead';
import { ApiError } from '../../shared/api/http';
import { operationId, readPending, savePending } from '../../shared/lib/operations';
import { Button } from '../../shared/ui/actions';
import { Field } from '../../shared/ui/layout';
import { Badge, ErrorNote, Loading, Notice } from '../../shared/ui/feedback';

type ConnectionMethod = 'existing' | 'managed';
type PendingStart = { preview: RuntimePreview; operation: string };

export function RuntimeConnection({ projectId, revision, confirmedEndpoint, canStart, onChanged, onError }: {
    projectId: string;
    revision: number;
    confirmedEndpoint: string | null;
    canStart: boolean;
    onChanged: () => void;
    onError: (error: unknown) => void;
}) {
    const key = 'jiejian.studio.start-runtime:' + projectId;
    const [pending, setPending] = useState(() => readPending<PendingStart>(key));
    const [method, setMethod] = useState<ConnectionMethod>();
    const [endpoint, setEndpoint] = useState<string>();
    const [entry, setEntry] = useState<string>();
    const [port, setPort] = useState<string>();
    const [preview, setPreview] = useState<RuntimePreview>();
    const [outcome, setOutcome] = useState<string>();
    const [ack, setAck] = useState(false);
    const [busy, setBusy] = useState(false);
    const lock = useRef(false);
    const state = useRead(canStart ? 'controlled-runtime:' + projectId : null, () => api.runtime(projectId));
    const operation = useRead(pending ? 'start-runtime:' + pending.operation : null,
        () => pending ? api.runtimeOperation(projectId, pending.operation) : Promise.resolve(null),
        value => value && ['PENDING', 'RUNNING', 'RETRY_WAIT'].includes(value.state) ? 1000 : 0);

    useEffect(() => {
        if (operation.data && ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(operation.data.state)) {
            savePending(key, undefined);
            setPending(undefined);
            setMethod('managed');
            setOutcome(operation.data.state);
            setPreview(undefined);
            setAck(false);
            state.reload();
            onChanged();
        }
    }, [operation.data?.state]);

    // 方式选择只切换编辑区域；检查对象和进程归属仍由服务端事实决定。
    const currentMethod = pending ? 'managed' : method ?? (state.data?.running ? 'managed' : 'existing');
    const runtimeAddress = state.data?.configuration ? 'http://127.0.0.1:' + state.data.configuration.port : null;
    const usingRuntime = Boolean(runtimeAddress && confirmedEndpoint === runtimeAddress);
    const panelId = 'runtime-configuration-' + projectId;
    const terminalState = !pending && (outcome ?? state.data?.operation?.state);
    const act = async (callback: () => Promise<unknown>) => {
        if (lock.current) return;
        lock.current = true;
        setBusy(true);
        try { await callback(); }
        catch (error) { onError(error); }
        finally { lock.current = false; setBusy(false); }
    };
    const confirmAddress = async (address: string) => {
        await api.confirmEndpoint(projectId, address, revision);
        setEndpoint(undefined);
        onChanged();
    };
    const start = async () => {
        const request = pending ?? (preview ? { preview, operation: operationId() } : undefined);
        if (!request) return;
        savePending(key, request);
        setPending(request);
        setOutcome(undefined);
        try {
            await api.runtimeStart(projectId, {
                entry: request.preview.entry, port: request.preview.port, revision: request.preview.revision,
                preview_fingerprint: request.preview.preview_fingerprint, operation_id: request.operation, consent_execute: true,
            });
        } catch (error) {
            if (error instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID'].includes(error.code)) {
                savePending(key, undefined); setPending(undefined); setPreview(undefined);
            }
            throw error;
        }
        operation.reload();
    };

    return <section className="jj-application-runtime" aria-label="应用运行">
        <header><h3>应用运行</h3></header>
        {canStart && <fieldset className="jj-runtime-methods" aria-label="应用运行方式">
            <legend className="jj-sr-only">应用运行方式</legend>
            <label className="jj-runtime-method"><input type="radio" name={'runtime-method-' + projectId} aria-label="连接已有应用" aria-controls={panelId} checked={currentMethod === 'existing'} disabled={busy || Boolean(pending)} onChange={() => setMethod('existing')}/><span><strong>连接已有应用</strong><small>使用你已启动的应用地址</small></span></label>
            <label className="jj-runtime-method"><input type="radio" name={'runtime-method-' + projectId} aria-label="由界鉴启动" aria-controls={panelId} checked={currentMethod === 'managed'} disabled={busy || Boolean(pending)} onChange={() => setMethod('managed')}/><span><strong>由界鉴启动</strong><small>运行此目录中的 Node ESM 源码</small></span></label>
        </fieldset>}
        <div className="jj-runtime-panel" id={panelId} key={currentMethod}>
            {currentMethod === 'existing' ? <>
                <div className="jj-endpoint-form"><Field label="应用地址"><input type="url" disabled={busy} value={endpoint ?? confirmedEndpoint ?? ''} placeholder="http://127.0.0.1:端口" onChange={event => setEndpoint(event.target.value)}/></Field><Button kind="primary" busy={busy} disabled={!(endpoint ?? confirmedEndpoint ?? '').trim()} onClick={() => void act(() => confirmAddress(endpoint ?? confirmedEndpoint ?? ''))}>使用此地址</Button></div>
                <p className="jj-small jj-muted">用于登录、录制和检查。</p>
                {state.data?.running && <div className="jj-runtime-retained"><span>界鉴启动的实例仍在运行</span><Button kind="quiet" onClick={() => setMethod('managed')}>管理运行实例</Button></div>}
            </> : <>
                {state.loading ? <Loading>正在读取运行实例</Loading> : state.error ? <ErrorNote error={state.error} onRetry={state.reload}/> : !pending && state.data?.running ? <div className="jj-runtime-instance">
                    <header><strong>界鉴启动的应用</strong><Badge tone={state.data.source_matches ? 'positive' : 'caution'}>{state.data.source_matches ? '正在运行' : '源码已有变化'}</Badge></header>
                    <dl><div><dt>访问地址</dt><dd>{runtimeAddress}</dd></div><div><dt>入口文件</dt><dd>{state.data.configuration?.entry}</dd></div></dl>
                    <footer>{usingRuntime ? <Badge tone="positive">已用于检查</Badge> : <div className="jj-small jj-muted">{confirmedEndpoint ? <>当前检查地址：<span className="jj-path">{confirmedEndpoint}</span></> : '尚未设置检查地址'}</div>}<div className="jj-inline-actions"><Button kind="quiet" busy={busy} onClick={() => void act(async () => { await api.runtimeStop(projectId, state.data!.operation!.instance_id); state.reload(); onChanged(); })}>停止应用</Button>{!usingRuntime && <Button kind="primary" busy={busy} onClick={() => void act(() => confirmAddress(runtimeAddress!))}>使用此应用</Button>}</div></footer>
                </div> : !pending && <>
                    <div className="jj-runtime-setup"><Field label="Node 入口文件"><input value={entry ?? state.data?.configuration?.entry ?? ''} placeholder="例如 source/app.mjs" disabled={busy} onChange={event => { setEntry(event.target.value); setPreview(undefined); }}/></Field><Field label="本地端口"><input type="number" min={1024} max={65535} value={port ?? state.data?.configuration?.port ?? 3000} disabled={busy} onChange={event => { setPort(event.target.value); setPreview(undefined); }}/></Field><Button disabled={busy || !(entry ?? state.data?.configuration?.entry)} onClick={() => void act(async () => { setAck(false); setOutcome(undefined); setPreview(await api.runtimePreview(projectId, { entry: entry ?? state.data!.configuration!.entry, port: Number(port ?? state.data?.configuration?.port ?? 3000), revision })); })}>预览启动</Button></div>
                    {!preview && <p className="jj-small jj-muted">先核对执行范围，再授权启动。界鉴会记录实际运行的源码。</p>}
                </>}
                {preview && !pending && !state.data?.running && <div className="jj-runtime-review"><div><strong>{preview.entry}</strong><p className="jj-small jj-muted">{preview.files.length} 个授权文件，将使用 http://127.0.0.1:{preview.port}</p></div><label className="jj-checkbox"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)}/><span>允许执行这份源码并使用上述端口</span></label><Button kind="primary" busy={busy} disabled={!ack} onClick={() => void act(start)}>启动应用</Button></div>}
                {!preview && terminalState === 'FAILED' && <Notice tone="caution">本次启动未完成，请重新预览启动范围。检查地址未因启动失败而改变。</Notice>}
                {!preview && terminalState === 'CANCELLED' && <Notice>本次启动已取消。</Notice>}
            </>}
        </div>
        {currentMethod === 'existing' && state.error && <ErrorNote error={state.error} onRetry={state.reload}/>}
        {operation.error && <ErrorNote error={operation.error} onRetry={operation.reload}/>}
        {pending && <Notice>正在核对本次启动。离开页面后仍可查询结果。<Button onClick={operation.reload}>查询启动结果</Button>{operation.data ? <Button busy={busy} onClick={() => void act(() => api.runtimeCancel(projectId, pending.operation).then(operation.reload))}>取消本次启动</Button> : <Button busy={busy} onClick={() => void act(start)}>恢复原启动请求</Button>}</Notice>}
    </section>;
}
