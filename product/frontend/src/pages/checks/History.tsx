import { useEffect, useRef, useState } from 'react';
import { ArrowRightOutlined } from '@ant-design/icons';
import { currentChecksApi as api, type CheckHistoryCursor, type CheckVerdict } from '../../entities/check/api/currentChecks';
import { Choice } from "../../shared/ui/Choice";
import { Button } from "../../shared/ui/actions";
import { Badge, Empty, ErrorNote, Loading } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import { go } from '../../shared/lib/navigation';
import { useRead } from '../../shared/lib/useRead';
import type { ReportsProps } from './types';
export type HistoryMemory = {
    query: string;
    search: string;
    filter: CheckVerdict | 'ALL';
    cursor?: CheckHistoryCursor;
    stack: Array<CheckHistoryCursor | undefined>;
    scroll: number;
};
export function restoreHistory(key: string): HistoryMemory {
    const initial: HistoryMemory = { query: '', search: '', filter: 'ALL', stack: [], scroll: 0 };
    try {
        const saved = JSON.parse(sessionStorage.getItem(key) ?? 'null');
        if (saved && typeof saved.query === 'string' && typeof saved.search === 'string' && ['ALL', 'PASS', 'BLOCK', 'INCONCLUSIVE'].includes(saved.filter) && Array.isArray(saved.stack))
            return { ...initial, ...saved, stack: saved.stack.map((item: CheckHistoryCursor | null) => item ?? undefined) };
    }
    catch { }
    return initial;
}
export function History({ projectId, route, archive = false }: ReportsProps) {
    const key = 'jiejian.studio.history:' + projectId + ':' + (route.query.get('intent_id') ?? 'all');
    const [saved] = useState(() => restoreHistory(key));
    const [query, setQuery] = useState(route.query.get('query') ?? saved.query), [search, setSearch] = useState(route.query.get('query') ?? saved.search), [filter, setFilter] = useState<CheckVerdict | 'ALL'>(saved.filter), [cursor, setCursor] = useState<CheckHistoryCursor | undefined>(saved.cursor), [stack, setStack] = useState<Array<CheckHistoryCursor | undefined>>(saved.stack);
    const restored = useRef(false), scroll = useRef(saved.scroll);
    useEffect(() => { sessionStorage.setItem(key, JSON.stringify({ query, search, filter, cursor, stack, scroll: scroll.current })); if (!archive)
        sessionStorage.setItem('jiejian.studio.history-location:' + projectId, route.path + (route.query.size ? '?' + route.query : '')); }, [key, query, search, filter, cursor, stack, route.path, route.query.toString()]);
    const rule = route.query.get('intent_id') && route.query.get('revision') && route.query.get('intent_hash') ? { intent_id: route.query.get('intent_id')!, revision: Number(route.query.get('revision')), intent_hash: route.query.get('intent_hash')! } : undefined;
    const state = useRead(`reports:${projectId}:${search}:${filter}:${JSON.stringify(cursor)}:${JSON.stringify(rule)}`, async (signal) => { const value = await api.history(projectId, { rule, query: search, verdict: filter === 'ALL' ? undefined : filter, cursor }, signal); assertProject(value.project_id, projectId); value.items.forEach(item => assertProject(item.status.run.project_id, projectId)); return value; });
    useEffect(() => { if (!state.data || restored.current)
        return; restored.current = true; const frame = requestAnimationFrame(() => window.scrollTo({ top: saved.scroll, behavior: 'instant' })); return () => cancelAnimationFrame(frame); }, [Boolean(state.data)]);
    const openRun = (runId: string) => { scroll.current = window.scrollY; sessionStorage.setItem(key, JSON.stringify({ query, search, filter, cursor, stack, scroll: scroll.current })); go((archive ? '/archive?project_id=' + encodeURIComponent(projectId) + '&' : '/reports?') + 'run_id=' + encodeURIComponent(runId)); };
    return <>
    <Heading title="检查记录" actions={!archive && <Button kind="primary" onClick={() => go('/reports?view=plan')}>发起新检查 <ArrowRightOutlined aria-hidden="true"/></Button>}/>
    <section className="jj-history-workspace">
      <div className="jj-history-toolbar"><form onSubmit={event => { event.preventDefault(); setCursor(undefined); setStack([]); setSearch(query); }}><label className="jj-sr-only" htmlFor="jj-history-search">查找检查记录</label><input id="jj-history-search" placeholder="查找业务操作或检查编号" value={query} onChange={event => setQuery(event.target.value)}/><Button type="submit">查找</Button></form><Choice aria-label="筛选检查结果" value={filter} onValueChange={value => { setFilter(value as CheckVerdict | 'ALL'); setCursor(undefined); setStack([]); }}><option value="ALL">全部结果</option><option value="PASS">符合规则</option><option value="BLOCK">存在问题</option><option value="INCONCLUSIVE">证据不足</option></Choice></div>
      {state.error && <ErrorNote error={state.error} onRetry={state.reload}/>}
      {state.loading ? <Loading page>正在读取检查记录</Loading> : state.data?.items.length ? <>
        <div className="jj-history-table-wrap"><table className="jj-history-table"><thead><tr><th>检查时间</th><th>业务操作</th><th>结果</th><th>关联</th><th><span className="jj-sr-only">打开报告</span></th></tr></thead><tbody>{state.data.items.map(item => {
                const run = item.status.run;
                return <tr key={run.run_id}>
          <td><time>{date(run.created_at_us)}</time><small>权限版本 {run.policy_epoch}</small></td>
          <td><strong>{item.action_labels.map(text).join('、') || '权限检查'}</strong></td>
          <td><Badge tone={run.verdict === 'PASS' ? 'positive' : run.verdict === 'BLOCK' ? 'negative' : run.verdict === 'INCONCLUSIVE' ? 'caution' : 'neutral'}>{run.verdict === 'PASS' ? '符合规则' : run.verdict === 'BLOCK' ? '存在问题' : run.verdict === 'INCONCLUSIVE' ? '证据不足' : ['QUEUED', 'RUNNING'].includes(run.lifecycle) ? '正在检查' : '未形成结论'}</Badge></td>
          <td className="jj-history-context">{item.change_id ? '源码修改' : '常规检查'}</td>
          <td><Button kind="quiet" onClick={() => openRun(run.run_id)}>{['QUEUED', 'RUNNING'].includes(run.lifecycle) ? '查看进度' : '阅读报告'}<ArrowRightOutlined aria-hidden="true"/></Button></td>
        </tr>;
            })}</tbody></table></div>
        <div className="jj-pagination jj-history-pagination"><Button disabled={!stack.length} onClick={() => { setCursor(stack.at(-1)); setStack(value => value.slice(0, -1)); }}>上一页</Button><span>第 {stack.length + 1} 页</span><Button disabled={!state.data.next_cursor} onClick={() => { setStack(value => [...value, cursor]); setCursor(state.data!.next_cursor ?? undefined); }}>下一页</Button></div>
      </> : <Empty title={search || filter !== 'ALL' ? '没有符合筛选条件的检查' : archive ? '这份示例没有检查记录' : '这里将保存你的检查报告'} action={search || filter !== 'ALL' ? <Button onClick={() => { setQuery(''); setSearch(''); setFilter('ALL'); setCursor(undefined); setStack([]); }}>清除筛选</Button> : !archive && <Button onClick={() => go('/reports?view=plan')}>预览首次检查</Button>}/>}
    </section>
  </>;
}
