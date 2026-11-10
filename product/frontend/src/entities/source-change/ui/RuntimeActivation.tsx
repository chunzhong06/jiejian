import {PendingRecovery} from '../../../shared/ui/PendingRecovery'
import { useEffect, useRef, useState } from 'react';
import './styles.css';
import { developmentApi as api, type DeliveryDetails, type RuntimeActivationReceipt } from '../api/development';
import { operationId, readPending, savePending, notAccepted, isOperationId } from '../../../shared/lib/operations';
import { useRead } from '../../../shared/lib/useRead';
import { assertProject } from '../../../shared/model/page';
import {Button,ActionLink} from '../../../shared/ui/actions'
import { Badge, ErrorNote, Notice } from '../../../shared/ui/feedback';
import {readRoute,withReturnDestination,scopedPath} from '../../../shared/lib/navigation'

export function RuntimeActivation({ projectId, details, onError, onChanged, onReady }: { projectId: string; details: DeliveryDetails; onError: (error: unknown) => void; onChanged: () => void; onReady?: (ready:boolean) => void }) {
    const key = 'jiejian.studio.runtime:' + projectId + ':' + details.delivery.delivery_id;
    const [pending, setPending] = useState(() => readPending<{ operation: string; version: number }>(key,(value):value is {operation:string;version:number}=>Boolean(value)&&typeof value==='object'&&isOperationId((value as {operation?:unknown}).operation)&&Number.isInteger((value as {version?:unknown}).version)&&Number((value as {version:number}).version)>0));
    const [receipt, setReceipt] = useState<RuntimeActivationReceipt>(), [busy, setBusy] = useState(false), lock = useRef(false);
    const task = useRead('runtime-task:' + details.delivery.task_id, () => api.show(projectId, details.delivery.task_id));
    const status = useRead(pending ? 'runtime-operation:' + pending.operation : null, () => pending ? api.runtimeReceipt(projectId, pending.operation) : Promise.resolve(null), value => value?.status === 'PENDING' ? 1000 : 0);
    const current = status.data ?? receipt, latest = task.data?.deliveries[0]?.delivery_id === details.delivery.delivery_id;
    useEffect(() => { if (current?.status === 'SUCCEEDED') { savePending(key, undefined); setPending(undefined); task.reload(); onChanged(); } }, [current?.status]);
    const matched = latest && task.data?.runtime_state === 'MATCHED';
    useEffect(() => { onReady?.(Boolean(matched)); }, [matched,onReady]);
    const load = async () => {
        if (lock.current || !task.data) return;
        lock.current = true; setBusy(true);
        try {
            const request = pending ?? { operation: operationId(), version: task.data.task.version };
            savePending(key, request); setPending(request);
            const value = await api.loadRuntime(projectId, details.delivery.delivery_id, { operation_id: request.operation, expected_version: request.version });
            assertProject(value.project_id, projectId); setReceipt(value); status.reload(); task.reload(); onChanged();
        } catch (error) {
            if (notAccepted(error,Boolean(pending))) { savePending(key, undefined); setPending(undefined); }
            onError(error);
        }
        finally { lock.current = false; setBusy(false); }
    };
    return <section className="jj-runtime-activation"><PendingRecovery storageKey={key} projectId={projectId} destination="/changes" label="查看修改与运行记录"/><div className="jj-runtime-activation-body"><div className="jj-runtime-activation-copy"><header><div className="jj-object-line"><h3>运行这批代码</h3><Badge tone={matched ? 'positive' : 'neutral'}>{matched ? '运行版本已对应' : current?.status === 'PENDING' ? '正在载入' : '待核对运行版本'}</Badge></div></header>{!matched&&<p className="jj-small jj-muted">载入后，受影响的账号和材料需要重新核对。</p>}</div>
        <footer className="jj-runtime-activation-actions">{!matched && !onReady && <ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/application',readRoute().path+'?'+readRoute().query))} kind="quiet">查看应用运行配置</ActionLink>}{matched ? (onReady ? <span className="jj-small jj-muted">当前运行已使用这次修改。</span> : <ActionLink navigationScope="page" href={'#'+scopedPath(withReturnDestination('/preparation?change_id=' + encodeURIComponent(details.delivery.change_id),readRoute().path+'?'+readRoute().query))}  kind="default">核对这次修改的材料</ActionLink>) : !latest ? <span className="jj-small jj-muted">仅最新登记可以载入运行。历史检查保留原有代码对应。</span> : pending && current?.status !== 'FAILED' ? <><Button busy={busy} onClick={() => { status.reload(); task.reload(); }}>查询载入结果</Button>{!current && <Button busy={busy} onClick={() => void load()}>恢复原载入请求</Button>}</> : <Button kind="primary" busy={busy} disabled={!task.data} onClick={() => { if (pending) { savePending(key, undefined); setPending(undefined); } else void load(); }}>{pending ? '重新核对后载入' : '载入这批代码'}</Button>}</footer>
        </div>{task.error && <ErrorNote error={task.error}/>}{status.error && <ErrorNote error={status.error}/>}
        {current?.status === 'FAILED' && <Notice tone="caution">这次载入未完成，请核对应用地址及受控运行配置。</Notice>}
    </section>;
}
