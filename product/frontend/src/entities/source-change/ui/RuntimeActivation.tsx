import { useEffect, useRef, useState } from 'react';
import './styles.css';
import { developmentApi as api, type DeliveryDetails, type RuntimeActivationReceipt } from '../api/development';
import { operationId, readPending, savePending } from '../../../shared/lib/operations';
import { useRead } from '../../../shared/lib/useRead';
import { assertProject } from '../../../shared/model/page';
import { ApiError } from '../../../shared/api/http';
import { Button } from '../../../shared/ui/actions';
import { Badge, ErrorNote, Notice } from '../../../shared/ui/feedback';
import { go } from '../../../shared/lib/navigation';

export function RuntimeActivation({ projectId, details, onError, onChanged }: { projectId: string; details: DeliveryDetails; onError: (error: unknown) => void; onChanged: () => void }) {
    const key = 'jiejian.studio.runtime:' + projectId + ':' + details.delivery.delivery_id;
    const [pending, setPending] = useState(() => readPending<{ operation: string; version: number }>(key));
    const [receipt, setReceipt] = useState<RuntimeActivationReceipt>(), [busy, setBusy] = useState(false), lock = useRef(false);
    const task = useRead('runtime-task:' + details.delivery.task_id, () => api.show(projectId, details.delivery.task_id));
    const status = useRead(pending ? 'runtime-operation:' + pending.operation : null, () => pending ? api.runtimeReceipt(projectId, pending.operation) : Promise.resolve(null), value => value?.status === 'PENDING' ? 1000 : 0);
    const current = status.data ?? receipt, latest = task.data?.deliveries[0]?.delivery_id === details.delivery.delivery_id;
    useEffect(() => { if (current?.status === 'SUCCEEDED') { savePending(key, undefined); setPending(undefined); task.reload(); onChanged(); } }, [current?.status]);
    const matched = latest && task.data?.runtime_state === 'MATCHED';
    const load = async () => {
        if (lock.current || !task.data) return;
        lock.current = true; setBusy(true);
        try {
            const request = pending ?? { operation: operationId(), version: task.data.task.version };
            savePending(key, request); setPending(request);
            const value = await api.loadRuntime(projectId, details.delivery.delivery_id, { operation_id: request.operation, expected_version: request.version });
            assertProject(value.project_id, projectId); setReceipt(value); status.reload(); task.reload(); onChanged();
        } catch (error) {
            if (error instanceof ApiError && ['STATE_PRECONDITION', 'INPUT_INVALID'].includes(error.code)) { savePending(key, undefined); setPending(undefined); }
            onError(error);
        }
        finally { lock.current = false; setBusy(false); }
    };
    return <section className="jj-runtime-activation"><header><h3>运行这批代码</h3><Badge tone={matched ? 'positive' : 'neutral'}>{matched ? '运行版本已对应' : current?.status === 'PENDING' ? '正在载入' : '待核对运行版本'}</Badge></header><p className="jj-small jj-muted">载入后重新核对受影响的材料，再按原要求复验。</p>{task.error && <ErrorNote error={task.error} onRetry={task.reload}/>}{status.error && <ErrorNote error={status.error} onRetry={status.reload}/>}
        <div className="jj-inline-actions">{matched ? <Button onClick={() => go('/preparation?change_id=' + encodeURIComponent(details.delivery.change_id))}>核对这次修改的材料</Button> : !latest ? <span className="jj-small jj-muted">仅最新登记可以载入运行。历史检查保留原有代码对应。</span> : pending && current?.status !== 'FAILED' ? <><Button busy={busy} onClick={() => { status.reload(); task.reload(); }}>查询载入结果</Button>{!current && <Button busy={busy} onClick={() => void load()}>恢复原载入请求</Button>}</> : <Button kind="primary" busy={busy} disabled={!task.data} onClick={() => { if (pending) { savePending(key, undefined); setPending(undefined); } else void load(); }}>{pending ? '重新核对后载入' : '载入这批代码'}</Button>}</div>
        {!matched && <Button kind="quiet" onClick={() => go('/application')}>查看应用运行配置</Button>}
        {current?.status === 'FAILED' && <Notice>这次载入未完成，请核对应用地址及受控运行配置。</Notice>}
    </section>;
}
