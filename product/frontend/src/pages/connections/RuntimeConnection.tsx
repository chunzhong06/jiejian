import { useEffect, useRef, useState } from 'react';
import { projectsApi as api, type RuntimePreview, type RuntimeSettings } from '../../entities/application/api/projects';
import {RuntimeOptions} from './RuntimeOptions';
import { useRead } from '../../shared/lib/useRead';
import { ApiError } from '../../shared/api/http';
import { operationId, readPending, savePending } from '../../shared/lib/operations';
import { Button } from '../../shared/ui/actions';
import { Field } from '../../shared/ui/layout';
import { Badge, ErrorNote, Loading, Notice } from '../../shared/ui/feedback';

type ConnectionMethod = 'existing' | 'managed';
type PendingStart = { preview: RuntimePreview; operation: string };

export function RuntimeConnection({ projectId, revision, confirmedEndpoint, canStart, initialMethod, onChanged, onError }: {
    projectId: string;
    revision: number;
    confirmedEndpoint: string | null;
    canStart: boolean;
    initialMethod?: ConnectionMethod;
    onChanged: () => void;
    onError: (error: unknown) => void;
}) {
    const key = 'jiejian.studio.start-runtime:' + projectId;
    const [pending, setPending] = useState(() => readPending<PendingStart>(key));
    const [method, setMethod] = useState<ConnectionMethod|undefined>(initialMethod);
    const [endpoint, setEndpoint] = useState<string>();
    const [entry, setEntry] = useState<string>();
    const [port, setPort] = useState<string>();
    const [settings,setSettings]=useState<RuntimeSettings>();
    const [preview, setPreview] = useState<RuntimePreview>();
    const [outcome, setOutcome] = useState<string>();
    const [ack, setAck] = useState(false);
    const [busy, setBusy] = useState(false);
    const lock = useRef(false);
    const state = useRead(canStart ? 'controlled-runtime:' + projectId : null, () => api.runtime(projectId),()=>pending?1000:0);
    const capabilities=useRead(canStart?'runtime-capabilities:'+projectId:null,()=>api.runtimeCapabilities(projectId));
    const configuration:RuntimeSettings=settings??{build_script:state.data?.configuration?.package?.build_script??null,allow_install_scripts:state.data?.configuration?.package?.allow_install_scripts??false,sqlite:state.data?.configuration?.sqlite??[]};
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
                build_script:request.preview.package?.build_script??null,allow_install_scripts:request.preview.package?.allow_install_scripts??false,sqlite:request.preview.sqlite??[],
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
        <header><div><h3>让应用可以访问</h3><p className="jj-small jj-muted">连接你已启动的应用，或交给界鉴启动一个测试实例。</p></div></header>
        {canStart && <fieldset className="jj-runtime-methods" aria-label="应用运行方式">
            <legend className="jj-sr-only">应用运行方式</legend>
            <label className="jj-runtime-method"><input type="radio" name={'runtime-method-' + projectId} aria-label="连接已有应用" aria-controls={panelId} checked={currentMethod === 'existing'} disabled={busy || Boolean(pending)} onChange={() => setMethod('existing')}/><span><strong>连接已有应用</strong><small>使用你已启动的应用地址</small></span></label>
            <label className="jj-runtime-method"><input type="radio" name={'runtime-method-' + projectId} aria-label="由界鉴启动" aria-controls={panelId} checked={currentMethod === 'managed'} disabled={busy || Boolean(pending)} onChange={() => setMethod('managed')}/><span><strong>由界鉴启动</strong><small>启动源码，保留对应的运行记录</small></span></label>
        </fieldset>}
        <div className="jj-runtime-panel" id={panelId} key={currentMethod}>
            {currentMethod === 'existing' ? <>
                <div className="jj-endpoint-form"><Field label="应用地址"><input type="url" disabled={busy} value={endpoint ?? confirmedEndpoint ?? ''} placeholder="http://127.0.0.1:端口" onChange={event => setEndpoint(event.target.value)}/></Field><Button busy={busy} disabled={!(endpoint ?? confirmedEndpoint ?? '').trim()} onClick={() => void act(() => confirmAddress(endpoint ?? confirmedEndpoint ?? ''))}>使用此地址</Button></div>
                <p className="jj-small jj-muted">用于登录、录制和检查。</p>
                {state.data?.running && <div className="jj-runtime-retained"><span>界鉴启动的实例仍在运行</span><Button kind="quiet" onClick={() => setMethod('managed')}>管理运行实例</Button></div>}
            </> : <>
                {state.loading ? <Loading>正在读取运行实例</Loading> : state.error ? <ErrorNote error={state.error} onRetry={state.reload}/> : !pending && state.data?.running ? <div className="jj-runtime-instance">
                    <header><strong>界鉴启动的应用</strong><Badge tone={state.data.source_matches ? 'positive' : 'caution'}>{state.data.source_matches ? '正在运行' : '源码已有变化'}</Badge></header>
                    <dl><div><dt>访问地址</dt><dd>{runtimeAddress}</dd></div><div><dt>入口文件</dt><dd>{state.data.configuration?.entry}</dd></div></dl>
                    <footer>{usingRuntime ? <Badge tone="positive">已用于检查</Badge> : <div className="jj-small jj-muted">{confirmedEndpoint ? <>当前检查地址：<span className="jj-path">{confirmedEndpoint}</span></> : '尚未设置检查地址'}</div>}<div className="jj-inline-actions"><Button kind="quiet" busy={busy} onClick={() => void act(async () => { await api.runtimeStop(projectId, state.data!.operation!.instance_id); setMethod('managed'); state.reload(); onChanged(); })}>停止应用</Button>{!usingRuntime && <Button kind="primary" busy={busy} onClick={() => void act(() => confirmAddress(runtimeAddress!))}>使用此应用</Button>}</div></footer>
                </div> : !pending && !preview && <>
                    <div className="jj-runtime-setup"><Field label="启动文件"><input value={entry ?? state.data?.configuration?.entry ?? capabilities.data?.entries[0]??''} placeholder="例如 app.mjs 或 server.cjs" disabled={busy} onChange={event => { setEntry(event.target.value); setPreview(undefined); }}/></Field><Field label="本地端口"><input type="number" min={1024} max={65535} value={port ?? state.data?.configuration?.port ?? 3000} disabled={busy} onChange={event => { setPort(event.target.value); setPreview(undefined); }}/></Field><Button disabled={busy || !(entry ?? state.data?.configuration?.entry??capabilities.data?.entries[0])} onClick={() => void act(async () => { setAck(false); setOutcome(undefined); setPreview(await api.runtimePreview(projectId, { entry: entry ?? state.data?.configuration?.entry??capabilities.data!.entries[0], port: Number(port ?? state.data?.configuration?.port ?? 3000), revision,...configuration })); })}>核对启动设置</Button></div>
                    <RuntimeOptions capabilities={capabilities.data??undefined} value={configuration} disabled={busy} onChange={next=>{setSettings(next);setPreview(undefined)}}/>
                    {!preview && <p className="jj-small jj-muted">选择启动文件和端口，下一步核对运行范围。</p>}
                </>}
                {preview && !pending && !state.data?.running && <section className="jj-runtime-review">
                    <header><Badge tone="accent">等待启动确认</Badge><h3>将启动这份源码的测试实例</h3></header>
                    <dl className="jj-facts"><div><dt>启动文件</dt><dd>{preview.entry}</dd></div><div><dt>访问地址</dt><dd>http://127.0.0.1:{preview.port}</dd></div><div><dt>依赖准备</dt><dd>{preview.package?'按项目锁文件安装依赖':'无需安装 npm 依赖'}</dd></div><div><dt>测试数据库</dt><dd>{preview.sqlite?.length?preview.sqlite.length+' 个数据库使用独立副本':'未设置数据库副本'}</dd></div></dl>
                    <details><summary>查看允许执行的文件（{preview.files.length} 个）</summary><ul>{preview.files.map(file=><li key={file.relative_path}>{file.relative_path}</li>)}</ul></details>
                    <label className="jj-checkbox"><input type="checkbox" checked={ack} onChange={event => setAck(event.target.checked)}/><span>允许按上述设置安装依赖、建立测试副本并启动应用</span></label>
                    <footer><Button disabled={busy} onClick={()=>{setPreview(undefined);setAck(false)}}>返回修改</Button><Button kind="primary" busy={busy} disabled={!ack} onClick={() => void act(start)}>启动测试实例</Button></footer>
                </section>}
                {!preview && terminalState === 'FAILED' && <Notice tone="caution">本次启动未完成，请重新预览启动范围。检查地址未因启动失败而改变。</Notice>}
                {!preview && terminalState === 'CANCELLED' && <Notice>本次启动已取消。</Notice>}
            </>}
        </div>
        {currentMethod === 'existing' && state.error && <ErrorNote error={state.error} onRetry={state.reload}/>}
        {operation.error && <ErrorNote error={operation.error} onRetry={operation.reload}/>}
        {pending && <Notice>{state.data?.preparation?.stage==='INSTALLING'?'正在准备锁定依赖':state.data?.preparation?.stage==='BUILDING'?'正在构建运行文件':'正在启动应用'}。离开页面后仍可查询结果。<Button onClick={operation.reload}>查询启动结果</Button>{operation.data ? <Button busy={busy} onClick={() => void act(() => api.runtimeCancel(projectId, pending.operation).then(operation.reload))}>取消本次启动</Button> : <Button busy={busy} onClick={() => void act(start)}>恢复原启动请求</Button>}</Notice>}
    </section>;
}
