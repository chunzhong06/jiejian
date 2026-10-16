// 历史只消费有界、完整性已核验的读模型；列表与精确 Run 详情共享返回位置，不产生新检查。
import { SearchField } from '../../shared/ui/SearchField'
import { StatusBadge } from '../../shared/ui/StatusBadge'
import { Alert, Button, Select, Spin } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import { useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../../api/http'
import { currentChecksApi, type CheckHistoryCursor, type CheckHistoryItem, type CheckHistoryQuery, type RuleHistoryReference } from '../../api/checks/currentChecks'
import type { ProjectDto } from '../../api/applications/projects'
import { formatTimestamp } from '../../shared/format/time'
import { lifecycleLabel } from '../../shared/presentation/execution'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import './history.css'
import { useLiveRead } from '../../shared/runtime/useLiveRead'
import { WorkPageVisible } from '../../shared/runtime/visibility'
import {RuleHistoryFilters} from './RuleHistoryFilters'

const labels = { PASS: '通过', BLOCK: '权限问题', INCONCLUSIVE: '证据不足' }
const cursorKey = (cursor: CheckHistoryCursor | null) => cursor ? `${cursor.created_at_us}:${cursor.run_id}` : ''

export function AllCheckHistory({ project, onError, onNavigate, requestedRunId, renderRun, ruleReference,initialOptions,returnSearch,showHeader=true,ruleFilters,refreshToken=0 }: {
  project: ProjectDto
  onError: (error: ApiError) => void
  onNavigate: (path: string) => void
  requestedRunId?: string | null
  ruleReference?:RuleHistoryReference;initialOptions?:CheckHistoryQuery;returnSearch?:string;showHeader?:boolean;ruleFilters?:(controls:ReactNode)=>ReactNode;refreshToken?:number
  renderRun: (runId: string, onBack: () => void) => ReactNode
}) {
  const visible = useContext(WorkPageVisible)
  const [newRecords, setNewRecords] = useState(false)
  const [query, setQuery] = useState(initialOptions?.query??'')
  const [options, setOptions] = useState<CheckHistoryQuery>({...initialOptions,...(ruleReference?{rule:ruleReference}:{})})
  const [items, setItems] = useState<CheckHistoryItem[]>([])
  const [cursor, setCursor] = useState<CheckHistoryCursor | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const epoch = useRef(0)
  const busy = useRef(false)
  const scrollPosition = useRef(0)
  const returnTarget = useRef<string | undefined>(undefined)
  const list = useRef<HTMLElement>(null)
  const origins=useRef(new Map<string,CheckHistoryCursor|null>())
  const routeOptions=JSON.stringify(initialOptions??null),ruleKey=JSON.stringify(ruleReference??null)
  useEffect(()=>{if(initialOptions===undefined)return;const next={...initialOptions,...(ruleReference?{rule:ruleReference}:{})};setOptions(previous=>JSON.stringify(previous)===JSON.stringify(next)?previous:next);setQuery(next.query??'')},[routeOptions,ruleKey])
  const load = useCallback(async (after: CheckHistoryCursor | null = null) => {
    if (after && busy.current) return
    const request = ++epoch.current
    busy.current = true; setLoading(true); setFailed(false)
    if (!after) { setCursor(null); setNewRecords(false) }
    try {
      const page = await currentChecksApi.history(project.project_id, { ...options, cursor: after })
      if (request !== epoch.current) return
      if (page.project_id !== project.project_id || page.items.some(item => item.status.run.project_id !== project.project_id)) {
        throw new ApiError('STATE_PRECONDITION', '检查历史所属项目不一致。')
      }
      if (after && cursorKey(after) === cursorKey(page.next_cursor)) throw new ApiError('STATE_PRECONDITION', '历史读取位置未推进，请重新获取记录。')
      page.items.forEach(item=>origins.current.set(item.status.run.run_id,after))
      setItems(previous => after ? [...previous, ...page.items.filter(item => !previous.some(old => old.status.run.run_id === item.status.run.run_id))] : page.items)
      setCursor(page.next_cursor)
    } catch (error) { if (request === epoch.current) { setFailed(true); onError(error as ApiError) } }
    finally { if (request === epoch.current) { busy.current = false; setLoading(false) } }
  }, [project.project_id, options, onError])
  useEffect(() => {
    if (!visible) {
      // 离开模块后释放筛选；从某条结果返回时页面仍可见，保留原阅读位置。
      setQuery(''); setOptions(previous => Object.keys(previous).length ? ruleReference?{rule:ruleReference}:{} : previous)
      return
    }
    void load(options.cursor??null)
    return () => { epoch.current += 1; busy.current = false }
  }, [load, visible,refreshToken])
  // 详情关闭后恢复选中行和滚动位置；后台结果变化不抢走正在阅读的历史。
  useEffect(() => {
    if (requestedRunId || !returnTarget.current) return
    const frame = requestAnimationFrame(() => {
      const target = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[data-run]') ?? []).find(button => button.dataset.run === returnTarget.current)
      target?.focus({ preventScroll: true }); window.scrollTo({ top: scrollPosition.current, behavior: 'instant' })
    })
    return () => cancelAnimationFrame(frame)
  }, [requestedRunId])
  const live = useLiveRead(visible && !requestedRunId ? project.project_id + JSON.stringify(options) : undefined, async () => {
    if (busy.current) return
    const request = epoch.current
    const page = await currentChecksApi.history(project.project_id, options)
    if (request !== epoch.current) return
    if (page.project_id !== project.project_id || page.items.some(item=>item.status.run.project_id!==project.project_id)) throw new ApiError('STATE_PRECONDITION','历史记录所属应用不一致。')
    // 空列表没有阅读位置要保护，应直接呈现新记录，不能要求先清除不存在的筛选。
    if (!items.length) {
      setItems(page.items); setCursor(page.next_cursor); setNewRecords(false); setFailed(false)
      return
    }
    // 阅读中的列表不重排；已有行就地更新，新记录提供明确提示。
    setItems(previous => {
      if (page.items.some(item=>!previous.some(old=>old.status.run.run_id===item.status.run.run_id))) setNewRecords(true)
      return previous.map(old=>page.items.find(item=>item.status.run.run_id===old.status.run.run_id) ?? old)
    })
  }, 5000, false)
  const open = (runId: string) => {
    scrollPosition.current = window.scrollY; returnTarget.current = runId
    const params=historyParams();const origin=origins.current.get(runId);if(origin){params.set('page_before_time',String(origin.created_at_us));params.set('page_before_run',origin.run_id)}else{params.delete('page_before_time');params.delete('page_before_run')}params.set('run_id',runId);const item=items.find(row=>row.status.run.run_id===runId);if(item?.matching_cases?.length===1)params.set('case_id',item.matching_cases[0]);onNavigate('/history?'+params)
  }
  const historyParams=(next=options)=>{const params=new URLSearchParams(returnSearch??'');for(const key of ['run_id','case_id','tab','evidence_id','record_id'])params.delete(key);for(const key of ['query','verdict','lifecycle'] as const){params.delete(key);if(next[key])params.set(key,next[key]!)}return params}
  const applyOptions=(next:CheckHistoryQuery)=>{const cleared={...next};delete cleared.cursor;setOptions(cleared);if(returnSearch!==undefined){const params=historyParams(cleared);params.delete('page_before_time');params.delete('page_before_run');onNavigate('/history?'+params)}}
  const clear = () => { setQuery('');setOptions({});if(returnSearch!==undefined)onNavigate('/history');else applyOptions({}) }
  const filtered = Boolean(ruleReference || options.query || options.verdict || options.lifecycle)
  const resultFilters = <>
    <Select aria-label="筛选检查结论" value={options.verdict ?? ''} options={[{ value: '', label: '全部结论' }, ...Object.entries(labels).map(([value, label]) => ({ value, label }))]} onChange={value => applyOptions({ ...options, query: query.trim(), verdict: value ? value as CheckHistoryQuery['verdict'] : undefined })} />
    <Select aria-label="筛选执行状态" value={options.lifecycle ?? ''} options={[{ value: '', label: '全部执行状态' }, ...['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].map(value => ({ value, label: lifecycleLabel(value) }))]} onChange={value => applyOptions({ ...options, lifecycle: value ? value as CheckHistoryQuery['lifecycle'] : undefined })} />
  </>
  const grouped = items.map((item, index) => {
    const date = new Date(item.status.run.created_at_us / 1000).toLocaleDateString('zh-CN')
    const previousDate = index ? new Date(items[index - 1].status.run.created_at_us / 1000).toLocaleDateString('zh-CN') : null
    return { item, date, heading: date !== previousDate }
  })
  return <>
    <div hidden={Boolean(requestedRunId)}>
      <EditorialPage label="项目检查历史" width="summary">
        {showHeader&&<EditorialHeader eyebrow={project.name || '当前应用'} title="检查历史"><p className="editorial-muted">回看每一次检查，沿原问题追踪复验结果。</p></EditorialHeader>}
        <div className={`history-surface${!loading && !failed && !items.length ? ' is-empty' : ''}`}><form className="history-filters" onSubmit={event => { event.preventDefault(); applyOptions({ ...options, query: query.trim() }) }}>
          <div className="history-search-controls"><SearchField aria-label="搜索检查历史" placeholder="搜索业务动作或检查编号" maxLength={128} value={query} onChange={event => setQuery(event.target.value)} allowClear />
          <Button htmlType="submit" aria-label="搜索">搜索</Button>{filtered && <Button type="link" onClick={clear}>清除筛选</Button>}</div>
          {ruleFilters ? ruleFilters(resultFilters) : <div className="history-result-filters">{resultFilters}</div>}
        </form>
        {newRecords && <div className="history-update" role="status">有新的检查记录<Button onClick={()=>void load()}>显示新记录</Button></div>}
        {live.retrying && <p role="status">暂时无法同步记录，正在重试。已有记录仍可查看。</p>}
        <section className="history-records" aria-label="历史检查列表" aria-busy={loading} ref={list}>
          {!!items.length && <div className="history-columns" aria-hidden="true"><span>检查内容</span><span>{ruleReference?'相关检查项':'安全结论'}</span><span>执行状态</span><span>查看</span></div>}
          {grouped.map(({ item, date, heading }) => {
            const { run, result_integrity } = item.status
            const verdict = result_integrity === 'VALID'&&!ruleReference ? run.verdict : null
            const matched=result_integrity==='VALID'&&ruleReference?item.matching_verdicts??[]:[]
            const related=matched.includes('VULNERABLE')?{label:'含权限问题',tone:'danger' as const}:matched.includes('INCONCLUSIVE')?{label:'含证据不足',tone:'warning' as const}:matched.length?{label:'相关项均符合要求',tone:'success' as const}:undefined
            return <div key={run.run_id}>
              {heading && <h2 className="history-date">{date}</h2>}
              <button className="history-record" data-run={run.run_id} onClick={() => open(run.run_id)}>
                <span className="history-record-copy"><strong>{item.action_labels.join('、') || '权限检查'}</strong><small>{formatTimestamp(run.created_at_us)} · 权限版本 {run.policy_epoch}{item.source_run_id ? ' · 原问题修复检查' : item.change_id ? ' · 关联代码变化' : ''}</small><small className="history-id">{run.run_id}</small></span>
                <StatusBadge kind={verdict ? 'verdict' : 'lifecycle'} tone={result_integrity === 'INVALID' ? 'warning' : related?.tone??(verdict === 'PASS' ? 'success' : verdict === 'BLOCK' ? 'danger' : verdict === 'INCONCLUSIVE' ? 'warning' : 'neutral')}>{result_integrity === 'INVALID' ? '结果完整性校验失败' : related?.label??(verdict ? labels[verdict] : '尚无安全结论')}</StatusBadge>
                <span className="history-lifecycle">{lifecycleLabel(run.lifecycle)}</span><span className="history-open"><span>查看{['QUEUED', 'RUNNING'].includes(run.lifecycle) ? '进度' : '结果'}</span><RightOutlined aria-hidden/></span>
              </button>
            </div>
          })}
          {!loading && !failed && !items.length && <div className="history-empty"><h2>{cursor ? '这一段记录中没有匹配项' : filtered ? '没有匹配的检查记录' : '尚无检查记录'}</h2><p>{cursor ? '还可以继续查找更早的记录。' : filtered ? '请调整筛选条件。' : '本应用的检查记录会自动显示在这里。'}</p>{filtered ? <Button onClick={clear}>清除筛选</Button> : !cursor && <Button onClick={() => onNavigate('/tests')}>前往检查与材料</Button>}</div>}
          {failed && <div role="alert" className="history-empty"><p>历史记录读取失败，已有记录已保留。</p><Button onClick={() => void load(cursor)}>重试读取</Button></div>}
          {loading && <div role="status" className="history-loading"><Spin size="small" />正在读取检查历史</div>}
        </section></div>
        {cursor && !failed && <Button className="history-more" loading={loading} onClick={() => void load(cursor)}>继续读取更早记录</Button>}
        <p className="editorial-muted history-boundary">历史结论对应当时的权限规则和代码版本。检查执行结束，不代表已经通过。</p>
      </EditorialPage>
    </div>
    {requestedRunId && renderRun(requestedRunId, () => onNavigate(returnSearch===undefined?'/history':'/history?'+historyParams()))}
  </>
}


export function CheckHistoryPage(props:{project:ProjectDto;onError:(error:ApiError)=>void;onNavigate:(path:string)=>void;requestedRunId?:string|null;locationSearch?:string;renderRun:(runId:string,onBack:()=>void)=>ReactNode}) {
  const [refreshToken,setRefreshToken]=useState(0)
  const params=new URLSearchParams(props.locationSearch??'')
  const intent=params.get('intent_id'),revision=Number(params.get('revision')),hash=params.get('intent_hash')
  const invalidRule=(params.has('intent_id')||params.has('revision')||params.has('intent_hash'))&&(!intent||!Number.isInteger(revision)||revision<1||!hash||!/^[0-9a-f]{64}$/.test(hash))
  const ref=invalidRule||!intent||!hash?undefined:{intent_id:intent,revision,intent_hash:hash}
  const contextParams=new URLSearchParams(params);for(const key of ['view','run_id','case_id','tab','evidence_id','record_id'])contextParams.delete(key)
  const pageTime=params.get('page_before_time'),pageRun=params.get('page_before_run')
  const invalidCursor=(params.has('page_before_time')||params.has('page_before_run'))&&(!pageTime||!pageRun||!Number.isSafeInteger(Number(pageTime))||Number(pageTime)<0)
  const initial:CheckHistoryQuery={...(pageTime&&pageRun&&!invalidCursor?{cursor:{created_at_us:Number(pageTime),run_id:pageRun}}:{}),...(params.get('query')?{query:params.get('query')!}:{}),...(params.get('verdict')?{verdict:params.get('verdict') as CheckHistoryQuery['verdict']}:{ }),...(params.get('lifecycle')?{lifecycle:params.get('lifecycle') as CheckHistoryQuery['lifecycle']}:{})}
  const selectRule=(rule?:RuleHistoryReference)=>{
    for(const key of ['intent_id','revision','intent_hash','page_before_time','page_before_run'])contextParams.delete(key)
    if(rule){contextParams.set('intent_id',rule.intent_id);contextParams.set('revision',String(rule.revision));contextParams.set('intent_hash',rule.intent_hash)}
    props.onNavigate('/history?'+contextParams)
  }
  if(invalidRule||invalidCursor)return <EditorialPage label="检查历史" width="summary"><EditorialHeader title="检查历史"/>
    <Alert type="warning" showIcon message={invalidRule?'规则筛选引用不完整，请清除筛选后重新选择。':'历史分页位置不完整，请重新读取列表。'}/>
    <Button onClick={()=>props.onNavigate('/history')}>重新读取检查历史</Button>
  </EditorialPage>
  return <AllCheckHistory {...props} ruleReference={ref} initialOptions={initial} returnSearch={contextParams.toString()} refreshToken={refreshToken}
    ruleFilters={controls=><RuleHistoryFilters projectId={props.project.project_id} onError={props.onError} active={!props.requestedRunId}
      value={ref} onSelect={selectRule} onMaintained={()=>setRefreshToken(value=>value+1)}>{controls}</RuleHistoryFilters>}/>
}
