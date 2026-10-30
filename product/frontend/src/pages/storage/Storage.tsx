import './styles.css'
import { useEffect, useRef, useState } from 'react';
import { ArrowLeftOutlined, ReloadOutlined, DeleteOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { ApiError } from '../../shared/api/http';
import { systemApi, type MaintenanceStatus, type MaintenanceOperationResult } from '../../entities/runtime/api/system';
import { ActionLink, Button } from "../../shared/ui/actions";
import { Badge, Empty, ErrorNote, Loading, Notice } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
const categories: Record<string, string> = { builds: '旧前端构建', build_cache: '下载与构建缓存', components: '闲置运行组件', assistant: 'AI 辅助缓存', logs: '历史日志', temporary: '运行临时文件' };
const pendingKey = 'jiejian.maintenance.pending';
type InventoryItem = NonNullable<MaintenanceStatus['inventory']>[number];
const size = (bytes: number | null) => { if (bytes === null)
    return '未确认'; const units = ['B', 'KiB', 'MiB', 'GiB']; let value = bytes, index = 0; while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index++;
} return `${index ? value.toFixed(1) : value} ${units[index]}`; };
export function Storage() {
    const [status, setStatus] = useState<MaintenanceStatus>(), [reading, setReading] = useState(true), [failed, setFailed] = useState(false), [busy, setBusy] = useState(false), [error, setError] = useState<unknown>();
    const [review, setReview] = useState(false), [plan, setPlan] = useState<MaintenanceOperationResult>(), [selected, setSelected] = useState<string[]>([]), [pending, setPending] = useState<string>(), [result, setResult] = useState<MaintenanceOperationResult>();
    const alive = useRef(true), lock = useRef(false), epoch = useRef(0), scanController = useRef<AbortController | undefined>(undefined);
    const scan = async () => {
        scanController.current?.abort();
        const controller = new AbortController();
        scanController.current = controller;
        const version = ++epoch.current;
        setReading(true);
        setError(undefined);
        try {
            const next = await systemApi.maintenanceStatus(controller.signal);
            if (!alive.current || version !== epoch.current)
                return;
            setStatus(next);
            setFailed(false);
            try {
                const stored = JSON.parse(sessionStorage.getItem(pendingKey) ?? 'null');
                if (stored?.root === next.protected.data && typeof stored.planId === 'string')
                    setPending(stored.planId);
            }
            catch { }
        }
        catch (reason) {
            if (alive.current && version === epoch.current && !controller.signal.aborted) {
                setFailed(true);
                setError(reason);
            }
        }
        finally {
            if (alive.current && version === epoch.current)
                setReading(false);
        }
    };
    useEffect(() => { alive.current = true; void scan(); return () => { alive.current = false; epoch.current++; scanController.current?.abort(); }; }, []);
    const accept = (value: MaintenanceOperationResult, id: string) => {
        if (value.plan_id !== id)
            throw new Error('清理回执与本次计划不一致，请查询原计划。');
        try {
            sessionStorage.removeItem(pendingKey);
        }
        catch { }
        if (!alive.current)
            return;
        setResult(value);
        setStatus(value.status);
        setPending(undefined);
        setPlan(undefined);
        setReview(false);
        setError(undefined);
    };
    const preview = async () => {
        if (lock.current || pending || reading || failed)
            return;
        lock.current = true;
        setBusy(true);
        setReview(true);
        setPlan(undefined);
        setSelected([]);
        setError(undefined);
        try {
            const value = await systemApi.maintenanceOperation('clear-all', { confirmed: false, dry_run: true });
            if (alive.current) {
                setPlan(value);
                setSelected(value.targets.filter(item => ['builds', 'build_cache', 'temporary'].includes(item.category ?? '')).map(item => item.item_id));
            }
        }
        catch (reason) {
            if (alive.current) {
                setError(reason);
                setReview(false);
            }
        }
        finally {
            lock.current = false;
            if (alive.current)
                setBusy(false);
        }
    };
    const execute = async () => {
        if (lock.current || pending || !plan || !selected.length)
            return;
        if (Date.now() * 1000 >= plan.expires_at_us) {
            setError(new Error('这份计划已过期，请重新预览清理项目。'));
            return;
        }
        lock.current = true;
        setBusy(true);
        setError(undefined);
        const id = plan.plan_id;
        let submitted = false;
        try {
            // 删除发出前持久保存定位；离页或断开后只能查询同一计划。
            sessionStorage.setItem(pendingKey, JSON.stringify({ root: status?.protected.data, planId: id }));
            submitted = true;
            setPending(id);
            const value = await systemApi.maintenanceOperation('clear-all', { confirmed: true, dry_run: false, plan_id: id, item_ids: selected });
            accept(value, id);
        }
        catch (reason) {
            if (alive.current) {
                if (reason instanceof ApiError && (reason.executionStarted === false || reason.code === 'INPUT_INVALID')) {
                    sessionStorage.removeItem(pendingKey);
                    setPending(undefined);
                    setError(reason);
                }
                else if (submitted) {
                    setPlan(undefined);
                    setReview(false);
                    setError(new Error('清理结果尚未确认，请查询本次结果。'));
                }
                else
                    setError(new Error('无法保存清理回执定位，本次未提交。请允许会话存储后重试。'));
            }
        }
        finally {
            lock.current = false;
            if (alive.current)
                setBusy(false);
        }
    };
    const recover = async () => {
        if (!pending || lock.current)
            return;
        lock.current = true;
        setBusy(true);
        setError(undefined);
        try {
            const value = await systemApi.maintenanceOutcome(pending);
            if (value.state === 'COMPLETED' && value.result)
                accept(value.result, pending);
            else if (alive.current)
                setError(new Error('尚未取得完成回执，已保留本次计划定位。'));
        }
        catch (reason) {
            if (alive.current)
                setError(reason);
        }
        finally {
            lock.current = false;
            if (alive.current)
                setBusy(false);
        }
    };
    const inventory = status?.inventory ?? [], cleanable = inventory.filter(item => item.state === 'CLEANABLE'), retained = inventory.filter(item => item.state === 'PROTECTED'), unknown = inventory.filter(item => item.state === 'UNKNOWN');
    const targets = plan?.targets ?? [], selectedTargets = targets.filter(item => selected.includes(item.item_id));
    const toggle = (ids: string[], checked: boolean) => setSelected(values => checked ? [...new Set([...values, ...ids])] : values.filter(id => !ids.includes(id)));
    return <>
    <div className="jj-back-link">{review ? <Button kind="quiet" disabled={busy || Boolean(pending)} icon={<ArrowLeftOutlined aria-hidden="true"/>} onClick={() => { setReview(false); setPlan(undefined); setError(undefined); }}>本地存储</Button> : <ActionLink href="#/workspace"><ArrowLeftOutlined aria-hidden="true"/>应用概览</ActionLink>}</div>
    <Heading title={review ? '核对清理项目' : '本地存储'} actions={!review && <Button busy={reading} disabled={busy || Boolean(pending)} icon={<ReloadOutlined aria-hidden="true"/>} onClick={() => void scan()}>重新扫描</Button>}/>
    {error && <ErrorNote error={error}/>}
    {pending && <Notice>已提交清理，正在核对执行结果。<Button busy={busy} onClick={() => void recover()}>查询本次结果</Button></Notice>}
    {reading && !status ? <Loading page>正在扫描已登记的运行文件</Loading> : status && <>
      {review ? <section className="jj-storage-review" aria-label="确认清理范围">
        {!plan ? <Loading page>正在生成清理计划</Loading> : <>
          <header><div><span className="jj-eyebrow">本次选择</span><h2>{selected.length} 项，{size(selectedTargets.reduce((total, item) => total + item.estimated_bytes, 0))}</h2></div><span className="jj-small jj-muted">只处理本计划中的所选文件</span></header>
          {Object.entries(categories).map(([category, name]) => {
                        const items = targets.filter(item => item.category === category);
                        if (!items.length)
                            return null;
                        const ids = items.map(item => item.item_id);
                        return <fieldset className="jj-storage-category" key={category}>
            <legend className="jj-sr-only">{name}</legend><div className="jj-storage-category-heading"><GroupChoice label={name} count={ids.filter(id => selected.includes(id)).length} total={ids.length} disabled={busy || Boolean(pending)} onChange={checked => toggle(ids, checked)}/><span className="jj-small jj-muted">{items.length} 项</span><strong>{size(items.reduce((total, item) => total + item.estimated_bytes, 0))}</strong></div>
            <details><summary>查看项目</summary><div className="jj-storage-selection">{items.map(item => <label key={item.item_id}><input type="checkbox" checked={selected.includes(item.item_id)} disabled={busy || Boolean(pending)} onChange={event => toggle([item.item_id], event.target.checked)}/><span><strong>{item.label}</strong><small>{item.relative_path}</small></span><span>{size(item.estimated_bytes)}</span></label>)}</div></details>
          </fieldset>;
                    })}
          {!targets.length && <Empty title="没有可以清理的闲置文件"/>}
          <footer><p>应用、权限、材料和报告保留。重新被使用或发生变化的文件会跳过。</p><div className="jj-inline-actions"><Button disabled={busy || Boolean(pending)} onClick={() => void preview()}>重新预览</Button><Button kind="primary" busy={busy} disabled={!selected.length || Boolean(pending)} icon={<DeleteOutlined aria-hidden="true"/>} onClick={() => void execute()}>清理所选</Button></div></footer>
        </>}
      </section> : <>
        <div className="jj-storage-layout"><section className="jj-storage-workspace">
          <header><div><p className="jj-eyebrow">可清理的闲置文件</p><h2>{size(cleanable.reduce((total, item) => total + (item.bytes ?? 0), 0))}</h2></div><Badge>{cleanable.length} 项</Badge></header>
          {Object.entries(categories).map(([category, name]) => { const items = cleanable.filter(item => item.category === category); if (!items.length)
                return null; return <div className="jj-storage-summary-row" key={category}><strong>{name}</strong><span>{items.length} 项</span><span>{size(items.reduce((total, item) => total + (item.bytes ?? 0), 0))}</span></div>; })}
          {!cleanable.length && <Empty title="暂未发现可确认清理的文件"/>}
          <footer><p>文件大小仅供参考，实际释放空间可能不同。</p><Button kind="primary" disabled={!cleanable.length || reading || failed || Boolean(pending)} busy={busy} onClick={() => void preview()}>预览清理</Button></footer>
        </section><aside className="jj-storage-kept"><h2>保留与排除</h2><p>应用、权限、材料和报告不参与清理。正在使用或归属未明的文件保留。</p><details><summary>当前保留，{retained.length} 项</summary><p className="jj-small jj-muted">当前依赖、在用文件、应用资料、正式证据、报告、凭据和界面偏好均保留。</p><Inventory items={retained}/></details>{unknown.length > 0 && <details><summary>暂无法确认，{unknown.length} 项</summary><Inventory items={unknown}/></details>}</aside></div>
        {failed && <Notice>当前为上次扫描结果，请重新扫描后再清理。</Notice>}
        {result && <section className="jj-storage-result"><header><CheckCircleOutlined aria-hidden="true"/><h2>本次清理已完成</h2></header><p>已清理 {result.counts.DELETED} 项，跳过 {result.counts.ALREADY_MISSING + result.counts.SKIPPED_CHANGED + result.counts.SKIPPED_IN_USE} 项，失败 {result.counts.FAILED} 项。</p>{result.requires_restart && <Notice>运行环境调整将在重新启动界鉴后生效。</Notice>}<details><summary>查看处理明细</summary>{result.results.map(item => <div className="jj-storage-file" key={item.item_id}><strong>{item.label}</strong><span>{({ DELETED: '已清理', ALREADY_MISSING: '文件已不存在', SKIPPED_CHANGED: '文件已变化，已保留', SKIPPED_IN_USE: '正在使用，已保留', FAILED: '未能清理' } as const)[item.status]}</span><small>{item.relative_path}</small><small>{item.reason}</small></div>)}</details></section>}

      </>}
    </>}
  </>;
}
function GroupChoice({ label, count, total, disabled, onChange }: {
    label: string;
    count: number;
    total: number;
    disabled: boolean;
    onChange: (checked: boolean) => void;
}) {
    const ref = useRef<HTMLInputElement>(null);
    useEffect(() => { if (ref.current)
        ref.current.indeterminate = count > 0 && count < total; }, [count, total]);
    return <label className="jj-checkbox"><input ref={ref} type="checkbox" checked={count === total} disabled={disabled} onChange={event => onChange(event.target.checked)}/><strong>{label}</strong></label>;
}
function Inventory({ items }: {
    items: InventoryItem[];
}) { return <div>{items.map(item => <div className="jj-storage-file" key={item.relative_path}><strong>{item.label}</strong><span>{size(item.bytes)}</span><small>{item.relative_path}</small><small>{item.reason}</small></div>)}</div>; }
