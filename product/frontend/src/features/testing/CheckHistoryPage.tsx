// 历史只消费有界、完整性已核验的读模型；列表与精确 Run 详情共享返回位置，不产生新检查。
import { Button, Input, Select, Spin } from 'antd'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError } from '../../api/http'
import { currentChecksApi, type CheckHistoryCursor, type CheckHistoryItem, type CheckHistoryQuery } from '../../api/currentChecks'
import type { ProjectDto } from '../../api/projects'
import { formatTimestamp, lifecycleLabel } from '../../app/presentation'
import { EditorialHeader, EditorialPage } from '../../shared/ui/Editorial'
import './history.css'

const labels = { PASS: '通过', BLOCK: '权限问题', INCONCLUSIVE: '证据不足' }
const cursorKey = (cursor: CheckHistoryCursor | null) => cursor ? `${cursor.created_at_us}:${cursor.run_id}` : ''

export function CheckHistoryPage({ project, onError, onNavigate, requestedRunId, renderRun }: {
  project: ProjectDto
  onError: (error: ApiError) => void
  onNavigate: (path: string) => void
  requestedRunId?: string | null
  renderRun: (runId: string, onBack: () => void) => ReactNode
}) {
  const [query, setQuery] = useState('')
  const [options, setOptions] = useState<CheckHistoryQuery>({})
  const [items, setItems] = useState<CheckHistoryItem[]>([])
  const [cursor, setCursor] = useState<CheckHistoryCursor | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const epoch = useRef(0)
  const busy = useRef(false)
  const scrollPosition = useRef(0)
  const returnTarget = useRef<string | undefined>(undefined)
  const list = useRef<HTMLElement>(null)
  const load = useCallback(async (after: CheckHistoryCursor | null = null) => {
    if (after && busy.current) return
    const request = ++epoch.current
    busy.current = true; setLoading(true); setFailed(false)
    if (!after) { setItems([]); setCursor(null) }
    try {
      const page = await currentChecksApi.history(project.project_id, { ...options, cursor: after })
      if (request !== epoch.current) return
      if (page.project_id !== project.project_id || page.items.some(item => item.status.run.project_id !== project.project_id)) {
        throw new ApiError('STATE_PRECONDITION', '检查历史所属项目不一致。')
      }
      if (after && cursorKey(after) === cursorKey(page.next_cursor)) throw new ApiError('STATE_PRECONDITION', '历史读取位置未推进，请重新获取记录。')
      setItems(previous => after ? [...previous, ...page.items.filter(item => !previous.some(old => old.status.run.run_id === item.status.run.run_id))] : page.items)
      setCursor(page.next_cursor)
    } catch (error) { if (request === epoch.current) { setFailed(true); onError(error as ApiError) } }
    finally { if (request === epoch.current) { busy.current = false; setLoading(false) } }
  }, [project.project_id, options, onError])
  useEffect(() => { void load(); return () => { epoch.current += 1; busy.current = false } }, [load])
  // 详情关闭后恢复选中行和滚动位置；后台结果变化不抢走正在阅读的历史。
  useEffect(() => {
    if (requestedRunId || !returnTarget.current) return
    const frame = requestAnimationFrame(() => {
      const target = Array.from(list.current?.querySelectorAll<HTMLButtonElement>('[data-run]') ?? []).find(button => button.dataset.run === returnTarget.current)
      target?.focus({ preventScroll: true }); window.scrollTo({ top: scrollPosition.current, behavior: 'instant' })
    })
    return () => cancelAnimationFrame(frame)
  }, [requestedRunId])
  const open = (runId: string) => {
    scrollPosition.current = window.scrollY; returnTarget.current = runId
    onNavigate(`/history?run_id=${encodeURIComponent(runId)}`)
  }
  const clear = () => { setQuery(''); setOptions({}) }
  const grouped = items.map((item, index) => {
    const date = new Date(item.status.run.created_at_us / 1000).toLocaleDateString('zh-CN')
    const previousDate = index ? new Date(items[index - 1].status.run.created_at_us / 1000).toLocaleDateString('zh-CN') : null
    return { item, date, heading: date !== previousDate }
  })
  return <>
    <div hidden={Boolean(requestedRunId)}>
      <EditorialPage label="项目检查历史">
        <EditorialHeader eyebrow={project.name || '当前项目'} title="检查历史"><p className="editorial-muted">回看每一次检查，沿原问题追踪复验结果。</p></EditorialHeader>
        <form className="history-toolbar" onSubmit={event => { event.preventDefault(); setOptions(previous => ({ ...previous, query: query.trim() })) }}>
          <Input aria-label="搜索检查历史" placeholder="搜索业务动作或检查编号" maxLength={128} value={query} onChange={event => setQuery(event.target.value)} allowClear />
          <Button htmlType="submit" aria-label="搜索">搜索</Button>
          <Select aria-label="筛选检查结论" value={options.verdict ?? ''} options={[{ value: '', label: '全部结论' }, ...Object.entries(labels).map(([value, label]) => ({ value, label }))]} onChange={value => setOptions(previous => ({ ...previous, query: query.trim(), verdict: value ? value as CheckHistoryQuery['verdict'] : undefined }))} />
          <Select aria-label="筛选执行状态" value={options.lifecycle ?? ''} options={[{ value: '', label: '全部执行状态' }, ...['QUEUED', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'].map(value => ({ value, label: lifecycleLabel(value) }))]} onChange={value => setOptions(previous => ({ ...previous, lifecycle: value ? value as CheckHistoryQuery['lifecycle'] : undefined }))} />
          <Button type="text" onClick={clear}>清除筛选</Button>
        </form>
        <section className="history-records" aria-label="历史检查列表" aria-busy={loading} ref={list}>
          {grouped.map(({ item, date, heading }) => {
            const { run, result_integrity } = item.status
            const verdict = result_integrity === 'VALID' ? run.verdict : null
            return <div key={run.run_id}>
              {heading && <h2 className="history-date">{date}</h2>}
              <button className="history-record" data-run={run.run_id} onClick={() => open(run.run_id)}>
                <span className="history-record-copy"><strong>{item.action_labels.join('、') || '权限检查'}</strong><small>{formatTimestamp(run.created_at_us)} · 权限版本 {run.policy_epoch}{item.source_run_id ? ' · 原题复验' : item.change_id ? ' · 关联代码变化' : ''}</small><small className="history-id">{run.run_id}</small></span>
                <span className={`history-verdict ${verdict ? 'is-' + verdict.toLowerCase() : ''}`}>{result_integrity === 'INVALID' ? '结果完整性校验失败' : verdict ? labels[verdict] : '尚无安全结论'}</span>
                <span className="history-lifecycle">{lifecycleLabel(run.lifecycle)}</span><span className="history-open">查看{['QUEUED', 'RUNNING'].includes(run.lifecycle) ? '进度' : '结果'} →</span>
              </button>
            </div>
          })}
          {!loading && !failed && !items.length && <div className="history-empty"><h2>{cursor ? '这一段记录中没有匹配项' : '没有匹配的检查记录'}</h2><p>{cursor ? '还可以继续查找更早的记录。' : '调整筛选条件，或从当前工作开始一次检查。'}</p><Button onClick={clear}>清除筛选</Button></div>}
          {failed && <div role="alert" className="history-empty"><p>历史记录读取失败，已有记录已保留。</p><Button onClick={() => void load(cursor)}>重试读取</Button></div>}
          {loading && <div role="status" className="history-loading"><Spin size="small" />正在读取检查历史</div>}
        </section>
        {cursor && !failed && <Button className="history-more" loading={loading} onClick={() => void load(cursor)}>继续读取更早记录</Button>}
        <p className="editorial-muted history-boundary">历史结论只覆盖当时冻结的权限与源码。执行完成不等于验证通过。</p>
      </EditorialPage>
    </div>
    {requestedRunId && renderRun(requestedRunId, () => onNavigate('/history'))}
  </>
}
