import {SearchField} from '../../shared/ui/SearchField'
import { useEffect, useRef, useState } from 'react';
import ArrowLeftOutlined from '@ant-design/icons/ArrowLeftOutlined';
import ArrowRightOutlined from '@ant-design/icons/ArrowRightOutlined';
import { currentChecksApi as api, type CheckHistoryCursor, type CheckVerdict } from '../../entities/check/api/currentChecks';
import { Choice } from "../../shared/ui/Choice";
import {ActionLink,Button} from '../../shared/ui/actions'
import { Badge, Empty, ErrorNote, Loading } from "../../shared/ui/feedback";
import { Heading } from "../../shared/ui/layout";
import { assertProject } from '../../shared/model/page';
import { date, text } from '../../shared/lib/format';
import {go,returnDestination,returnDestinationLabel,withReturnDestination,scopedPath} from '../../shared/lib/navigation'
import { useRead } from '../../shared/lib/useRead';
import type { ReportsProps } from './types';
import './comparison.css';
import {TestingSections} from '../../shared/ui/SectionNavigation';
type ComparisonSelection={run_id:string;created_at_us:number};
export type HistoryMemory = {
    query: string;
    search: string;
    filter: CheckVerdict | 'ALL';
    cursor?: CheckHistoryCursor;
    stack: Array<CheckHistoryCursor | undefined>;
    scroll: number;
    comparison?:ComparisonSelection[];
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
export function History({ projectId, name, route, archive = false }: ReportsProps) {
    const origin=archive?null:returnDestination(route.query.get('return_to'))
    const here=route.path+'?'+route.query
    const key = 'jiejian.studio.history:' + projectId + ':' + (route.query.get('intent_id') ?? 'all');
    const [saved] = useState(() => restoreHistory(key));
    const [comparison,setComparison]=useState<ComparisonSelection[]>(()=>Array.isArray(saved.comparison)?saved.comparison.filter(item=>item&&typeof item.run_id==='string'&&/^run_[0-9a-f]{32}$/.test(item.run_id)&&Number.isSafeInteger(item.created_at_us)).slice(0,2):[]);
    const [query, setQuery] = useState(route.query.get('query') ?? saved.query), [search, setSearch] = useState(route.query.get('query') ?? saved.search), [filter, setFilter] = useState<CheckVerdict | 'ALL'>(saved.filter), [cursor, setCursor] = useState<CheckHistoryCursor | undefined>(saved.cursor), [stack, setStack] = useState<Array<CheckHistoryCursor | undefined>>(saved.stack);
    const restored = useRef(false), scroll = useRef(saved.scroll);
    useEffect(() => { sessionStorage.setItem(key, JSON.stringify({ query, search, filter, cursor, stack, scroll: scroll.current, comparison })); if (!archive)
        sessionStorage.setItem('jiejian.studio.history-location:' + projectId, route.path + (route.query.size ? '?' + route.query : '')); }, [key, query, search, filter, cursor, stack, comparison, route.path, route.query.toString()]);
    const rule = route.query.get('intent_id') && route.query.get('revision') && route.query.get('intent_hash') ? { intent_id: route.query.get('intent_id')!, revision: Number(route.query.get('revision')), intent_hash: route.query.get('intent_hash')! } : undefined;
    const state = useRead(`reports:${projectId}:${search}:${filter}:${JSON.stringify(cursor)}:${JSON.stringify(rule)}`, async (signal) => { const value = await api.history(projectId, { rule, query: search, verdict: filter === 'ALL' ? undefined : filter, cursor }, signal); assertProject(value.project_id, projectId); value.items.forEach(item => assertProject(item.status.run.project_id, projectId)); return value; });
    useEffect(() => { if (!state.data || restored.current)
        return; restored.current = true; const frame = requestAnimationFrame(() => window.scrollTo({ top: saved.scroll, behavior: 'instant' })); return () => cancelAnimationFrame(frame); }, [Boolean(state.data)]);
    const openRun = (runId: string) => { scroll.current = window.scrollY; sessionStorage.setItem(key, JSON.stringify({ query, search, filter, cursor, stack, scroll: scroll.current, comparison })); go(archive?'/archive?project_id='+encodeURIComponent(projectId)+'&run_id='+encodeURIComponent(runId):withReturnDestination('/reports?run_id='+encodeURIComponent(runId),here)); };
    const hasHistoryContext=Boolean(state.data?.items.length||query||search||filter!=='ALL'||stack.length);
    return <>
    {origin&&<div className="jj-back-link"><ActionLink navigationScope="page" href={'#'+scopedPath(origin)} kind="quiet">{returnDestinationLabel(origin)}</ActionLink></div>}
    <Heading eyebrow={archive?'已归档：'+name:undefined} title="检查记录" actions={archive?<ActionLink href="#/environment"><ArrowLeftOutlined aria-hidden="true"/>返回官方示例</ActionLink>: (Boolean(state.data?.items.length) || Boolean(search) || filter!=='ALL') && <ActionLink navigationScope="page" href={'#'+scopedPath('/reports?view=plan')} kind="primary">发起新检查 <ArrowRightOutlined aria-hidden="true"/></ActionLink>}>{archive?'已归档示例的检查报告':undefined}</Heading>
    {!archive&&!rule&&<TestingSections value="history" projectId={projectId}/>}
    <section className="jj-history-workspace" data-empty={!state.loading&&Boolean(state.data)&&!state.data?.items.length||undefined}>
      {hasHistoryContext&&<div className="jj-history-toolbar"><form onSubmit={event => { event.preventDefault(); setCursor(undefined); setStack([]); setSearch(query); }}><SearchField id="jj-history-search" label="查找检查记录" placeholder="查找业务操作或检查编号" value={query} onValueChange={setQuery}/><Button type="submit">查找</Button></form><Choice aria-label="筛选检查结果" value={filter} onValueChange={value => { setFilter(value as CheckVerdict | 'ALL'); setCursor(undefined); setStack([]); }}><option value="ALL">全部结果</option><option value="PASS">符合规则</option><option value="BLOCK">不符合规则</option><option value="INCONCLUSIVE">证据不足</option></Choice></div>}
      {state.error && <ErrorNote error={state.error}/>}
      {state.loading ? <Loading page>正在读取检查记录</Loading> : state.data?.items.length ? <>
        <div className="jj-history-table-wrap"><table className="jj-content-table jj-history-table"><thead><tr>{!archive&&<th scope="col" className="jj-history-select"><span className="jj-sr-only">选择比较记录</span></th>}<th scope="col" className="jj-history-time">检查时间</th><th scope="col" className="jj-history-action">业务操作</th><th scope="col" className="jj-table-state">结果</th><th scope="col" className="jj-table-state jj-history-context">检查用途</th><th scope="col" className="jj-table-actions"><span className="jj-sr-only">打开报告</span></th></tr></thead><tbody>{state.data.items.map(item => {
                const run = item.status.run;
                return <tr key={run.run_id}>
          {!archive&&<td><label className="jj-checkbox"><input type="checkbox" aria-label={'选择比较记录 '+run.run_id.slice(-8)} checked={comparison.some(item=>item.run_id===run.run_id)} disabled={!comparison.some(item=>item.run_id===run.run_id)&&comparison.length>=2} onChange={event=>setComparison(current=>event.target.checked?[...current,{run_id:run.run_id,created_at_us:run.created_at_us}]:current.filter(item=>item.run_id!==run.run_id))}/></label></td>}
          <td className="jj-history-time"><time>{date(run.created_at_us)}</time><small>权限版本 {run.policy_epoch}</small></td>
          <td className="jj-history-action"><strong>{item.action_labels.map(text).join('、') || '权限检查'}</strong></td>
          <td className="jj-table-state"><Badge tone={run.verdict === 'PASS' ? 'positive' : run.verdict === 'BLOCK' ? 'negative' : run.verdict === 'INCONCLUSIVE' ? 'caution' : 'neutral'}>{run.verdict === 'PASS' ? '符合规则' : run.verdict === 'BLOCK' ? '不符合规则' : run.verdict === 'INCONCLUSIVE' ? '证据不足' : ['QUEUED', 'RUNNING'].includes(run.lifecycle) ? '正在检查' : '未形成结论'}</Badge></td>
          <td className="jj-history-context jj-table-state"><strong>{item.source_run_id?'原问题复验':item.change_id?'修改后检查':item.status.routine?'方案检查':'常规检查'}</strong>{(item.status.routine||item.status.environment)&&<small>{[item.status.routine?`方案第 ${item.status.routine.revision} 修订`:null,item.status.environment?.name].filter(Boolean).join(' · ')}</small>}</td>
          <td className="jj-table-actions"><Button kind="quiet" onClick={() => openRun(run.run_id)}>{['QUEUED', 'RUNNING'].includes(run.lifecycle) ? '查看进度' : '阅读报告'}<ArrowRightOutlined aria-hidden="true"/></Button></td>
        </tr>;
            })}</tbody></table></div>
        {!archive&&comparison.length>0&&<footer className="jj-history-compare"><span className="jj-small jj-muted">已选 {comparison.length} 条记录，选择两条后比较</span><Button onClick={()=>setComparison([])}>清除选择</Button><Button kind="primary" disabled={comparison.length!==2} onClick={()=>{const ordered=[...comparison].sort((a,b)=>a.created_at_us-b.created_at_us);go(withReturnDestination('/reports?'+new URLSearchParams({view:'compare',baseline:ordered[0].run_id,current:ordered[1].run_id}),here),projectId)}}>查看本轮变化</Button></footer>}
        {(stack.length>0||state.data.next_cursor)&&<div className="jj-pagination jj-history-pagination"><Button disabled={!stack.length} onClick={() => { setCursor(stack.at(-1)); setStack(value => value.slice(0, -1)); }}>上一页</Button><span>第 {stack.length + 1} 页</span><Button disabled={!state.data.next_cursor} onClick={() => { setStack(value => [...value, cursor]); setCursor(state.data!.next_cursor ?? undefined); }}>下一页</Button></div>}
      </> : !state.data ? null : <Empty layout="section" title={search || filter !== 'ALL' ? '没有符合筛选条件的检查' : archive ? '这份示例没有检查记录' : '这里将保存你的检查报告'} action={search || filter !== 'ALL' ? <Button onClick={() => { setQuery(''); setSearch(''); setFilter('ALL'); setCursor(undefined); setStack([]); }}>清除筛选</Button> : !archive && <ActionLink navigationScope="page" href={'#'+scopedPath('/reports?view=plan')} kind="primary">发起检查</ActionLink>}>{!search&&filter==='ALL'&&!archive&&'完成一次检查后，可以在这里查阅结果、原始依据和后续复验。'}</Empty>}
    </section>
  </>;
}
