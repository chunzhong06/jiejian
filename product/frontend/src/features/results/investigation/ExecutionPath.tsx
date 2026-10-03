// 已发布显式父边的可访问排版；图形位置和缺口工作面不产生新的因果事实。
import { useEffect, useId, useRef, useState } from 'react'
import { AimOutlined, ApartmentOutlined, FileOutlined, LoginOutlined, SafetyOutlined, UndoOutlined, UserOutlined, ZoomInOutlined, ZoomOutOutlined, NodeIndexOutlined, UnorderedListOutlined } from '@ant-design/icons'
import type { ActionResultStory, StoryTraceEvent } from '../../../api/checks/currentChecks'
import { traceEventContext, traceEventLabel, traceLimitations } from './tracePresentation'
export { traceKindLabels } from './tracePresentation'
const nodeIcons = { ENTRY: LoginOutlined, IDENTITY: UserOutlined, AUTHORIZATION: SafetyOutlined, PERSISTENT_EFFECT: FileOutlined, MESSAGE: ApartmentOutlined, DELEGATION: ApartmentOutlined, FINAL_EFFECT: FileOutlined, RECOVERY: UndoOutlined }
const nodeWidth = 208, nodeHeight = 80, columnStep = 244, rowStep = 112

export function ExecutionPath({ action, selectedEvent, onSelect }: {
  action: ActionResultStory; selectedEvent?: string; onSelect: (event: StoryTraceEvent, refs: string[]) => void
}) {
  const path = action.execution_path
  const marker = useId().replace(/:/g, '')
  const [expanded, setExpanded] = useState(false)
  const [view, setView] = useState<'graph' | 'list' | 'range'>(() => action.breakpoint?.precision === 'RANGE' ? 'range' : window.matchMedia('(max-width: 760px)').matches ? 'list' : 'graph')
  const [zoom, setZoom] = useState(1)
  const [available, setAvailable] = useState(0)
  const viewport = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const element = viewport.current
    if (!element) return
    const measure = () => setAvailable(Math.max(0, element.clientWidth - 32))
    measure()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(measure); observer.observe(element)
    return () => observer.disconnect()
  }, [path, expanded, view])
  useEffect(() => {
    viewport.current?.querySelector('[aria-pressed="true"]')?.scrollIntoView?.({ block: 'nearest', inline: 'nearest', behavior: 'instant' })
  }, [selectedEvent, available])
  const events = path?.events ?? []
  const byId = new Map(events.map(event => [event.event_id, event]))
  // 服务端已经提供拓扑顺序；缺失父引用只计为缺口，不创建占位事件或连线。
  const positions = new Map<string, { x: number; y: number }>()
  const rows = new Map<number, number>()
  const depths = new Map<string, number>()
  events.forEach(event => {
    const depth = Math.max(-1, ...event.parent_event_ids.map(parent => depths.get(parent) ?? -1)) + 1
    depths.set(event.event_id, depth)
    const lane = rows.get(depth) ?? 0
    positions.set(event.event_id, { x: lane * columnStep, y: depth * rowStep }); rows.set(depth, lane + 1)
  })
  const rowCount = Math.max(1, ...rows.values())
  events.forEach(event => {
    const position = positions.get(event.event_id)!, depth = depths.get(event.event_id)!
    position.x += (rowCount - rows.get(depth)!) * columnStep / 2
    // 单分支继续沿父节点所在列向下；这只决定位置，不补造父边。
    if(rows.get(depth) === 1 && event.parent_event_ids.length === 1) position.x = positions.get(event.parent_event_ids[0])?.x ?? position.x
  })
  // 起始的单链按两列折行，减少向下阅读距离；所有节点和显式边仍逐个保留。
  const children = new Map<string, string[]>()
  events.forEach(event => event.parent_event_ids.forEach(parent => children.set(parent, [...(children.get(parent) ?? []), event.event_id])))
  const prefix: StoryTraceEvent[] = []
  let cursor = events.filter(event => !event.parent_event_ids.length).length === 1 ? events.find(event => !event.parent_event_ids.length) : undefined
  while (cursor && prefix.length < 4) {
    prefix.push(cursor)
    const next = children.get(cursor.event_id) ?? []
    cursor = next.length === 1 && byId.get(next[0])?.parent_event_ids.length === 1 ? byId.get(next[0]) : undefined
  }
  if (prefix.length >= 2) {
    const savedRows = prefix.length - Math.ceil(prefix.length / 2)
    prefix.forEach((event, index) => positions.set(event.event_id, { x: index % 2 * columnStep, y: Math.floor(index / 2) * rowStep }))
    events.filter(event => !prefix.includes(event)).forEach(event => { positions.get(event.event_id)!.y -= savedRows * rowStep })
  }
  const width = Math.max(0, ...Array.from(positions.values(), p => p.x)) + nodeWidth
  const height = Math.max(0, ...Array.from(positions.values(), p => p.y)) + nodeHeight
  // 过度缩小会使文字不可读；窄屏保留可滚动画布，并提供无缩放的列表阅读。
  const scale = Math.max(.75, Math.min(1, available ? available / width : 1)) * zoom
  const fit = () => { setZoom(1); viewport.current?.scrollTo?.({ left: 0, top: 0 }) }
  const breakpoint = action.breakpoint
  const start = breakpoint?.precision === 'RANGE' ? byId.get(breakpoint.range_start_event_id ?? '') : undefined
  const end = breakpoint?.precision === 'RANGE' ? byId.get(breakpoint.range_end_event_id ?? '') : undefined
  const exact = (event: StoryTraceEvent) => breakpoint?.precision === 'EXACT' && breakpoint.first_violation_event_id === event.event_id
  const endpoint = (event: StoryTraceEvent) => event === start || event === end
  const select = (event: StoryTraceEvent) => onSelect(event, path?.evidence_refs ?? [])
  return <section className={`execution-path${!path?.complete ? ' is-partial' : ''}`} aria-label="已发布执行路径">
    <div className="execution-path-heading"><div><p className="path-eyebrow">因果与定位</p><h3>{path?.complete ? '这次操作实际经过了什么' : '已知路径与缺失环节'}</h3><p>{path?.complete ? '路径完整 · 连线来自已发布的父子引用' : '路径不完整 · 只展示已知关系'}</p></div>
      {!!events.length && <div className="path-view-switch" aria-label="路径阅读方式">{breakpoint?.precision === 'RANGE' && <button aria-label="查看定位区间" aria-pressed={view === 'range'} onClick={() => setView('range')}>区间</button>}<button aria-label="图形查看执行路径" aria-pressed={view === 'graph'} onClick={() => setView('graph')}><NodeIndexOutlined aria-hidden="true"/>图形</button><button aria-label="列表查看执行路径" aria-pressed={view === 'list'} onClick={() => setView('list')}><UnorderedListOutlined aria-hidden="true"/>列表</button></div>}
    </div>
    {!events.length ? <div className="path-empty"><NodeIndexOutlined aria-hidden="true"/><h4>本轮没有可展示的执行路径</h4><p>以下只对照已发布事实，不从页面回应推断后台路径。</p></div> : view === 'range' && breakpoint?.precision === 'RANGE' ? null : view === 'list' ? <ol className="path-event-list" aria-label="已发布事件列表">{events.map(event => <li key={event.event_id}><button aria-label={`查看${traceEventLabel(event)}的发布证据`} className={exact(event) ? 'is-breakpoint' : ''} aria-pressed={selectedEvent === event.event_id} onClick={() => select(event)}><span>{traceEventLabel(event)}</span><strong>{traceEventContext(event, action)}</strong>{exact(event) && <small>首个可证明断裂</small>}{endpoint(event) && <small>{event === start ? '定位区间起点' : '定位区间终点'}</small>}</button><p>{event.parent_event_ids.length ? `已记录的前序：${event.parent_event_ids.map(id => byId.has(id) ? traceEventLabel(byId.get(id)!) : '前序记录缺失').join('、')}` : '未记录前序引用'}</p></li>)}</ol> : events.length > 32 && !expanded ? <div className="path-large"><h4>本项包含 {events.length} 个已发布节点</h4><p>可展开画布，或切换到列表逐项阅读。节点未展开不表示记录缺失。</p><button onClick={() => setExpanded(true)}>展开完整执行路径</button></div> : <>
      <div className="path-scroll" ref={viewport} tabIndex={0} aria-label="横向或纵向滚动查看执行路径">
        <div className="path-stage" style={{ width: width * scale, height: height * scale }}><div className="path-canvas" style={{ width, height, transform:`scale(${scale})` }}>
          <svg width={width} height={height} aria-hidden="true"><defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="currentColor"/></marker></defs>{events.flatMap(event => event.parent_event_ids.map(parent => {
            const from = positions.get(parent), to = positions.get(event.event_id)
            if (!from || !to) return null
            return <path key={`${parent}/${event.event_id}`} data-parent={parent} data-child={event.event_id} d={from.y === to.y ? `M${from.x + nodeWidth},${from.y + nodeHeight / 2} L${to.x},${to.y + nodeHeight / 2}` : `M${from.x + nodeWidth / 2},${from.y + nodeHeight} C${from.x + nodeWidth / 2},${from.y + nodeHeight + 16} ${to.x + nodeWidth / 2},${to.y - 16} ${to.x + nodeWidth / 2},${to.y}`} markerEnd={`url(#${marker})`}/>
          }))}</svg>
          {events.map(event => { const position = positions.get(event.event_id)!, Icon = nodeIcons[event.kind]
            return <button key={event.event_id} className={`path-node${exact(event) ? ' path-node-breakpoint' : ''}${endpoint(event) ? ' path-node-endpoint' : ''}`} style={{ left: position.x, top: position.y }} aria-label={`查看${traceEventLabel(event)}的发布证据`} aria-pressed={selectedEvent === event.event_id} onClick={() => select(event)}><Icon className="path-node-icon" aria-hidden="true"/><span className="path-node-copy"><span>{traceEventLabel(event)}</span><strong title={traceEventContext(event, action)}>{traceEventContext(event, action)}</strong></span>{exact(event) ? <small>首个可证明断裂</small> : endpoint(event) ? <small>{event === start ? '定位区间起点' : '定位区间终点'}</small> : selectedEvent === event.event_id ? <small>正在查看此节点</small> : null}</button>
          })}
        </div></div>
      </div>
      <div className="path-canvas-footer"><span>仅连接已记录的关系</span><div className="path-tools" aria-label="执行路径视图"><button aria-label="缩小执行路径" disabled={zoom <= .8} onClick={() => setZoom(value => Math.max(.8, value - .1))}><ZoomOutOutlined aria-hidden="true"/></button><button aria-label="放大执行路径" disabled={zoom >= 1.5} onClick={() => setZoom(value => Math.min(1.5, value + .1))}><ZoomInOutlined aria-hidden="true"/></button><button aria-label="适应执行路径宽度" onClick={fit}><AimOutlined aria-hidden="true"/></button></div></div>
    </>}
    {breakpoint?.precision === 'RANGE' && <section className="path-range" aria-label="已发布的定位区间"><div><small>区间起点</small>{start ? <button aria-pressed={selectedEvent === start.event_id} onClick={() => select(start)}>{traceEventLabel(start)}<span>{traceEventContext(start, action)}</span></button> : <p>当前路径未提供起点记录</p>}</div><div className="path-range-gap"><strong>当前可定位范围</strong><span>仅标示诊断区间，不补画内部步骤</span></div><div><small>区间终点</small>{end ? <button aria-pressed={selectedEvent === end.event_id} onClick={() => select(end)}>{traceEventLabel(end)}<span>{traceEventContext(end, action)}</span></button> : <p>当前路径未提供终点记录</p>}</div></section>}
    {!path?.complete && breakpoint?.precision !== 'RANGE' && <div className="path-missing"><strong>缺失的环节保持未知</strong>{traceLimitations(action).map(text => <p key={text}>{text}</p>)}</div>}
    <p className="path-boundary">节点存在不单独证明业务后果或权限安全。定位精度与本轮结论分别表达。</p>
  </section>
}
