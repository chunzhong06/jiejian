// 只为已发布的显式父边排版；层级与坐标不是新的因果或安全判断。
import { useId, useRef, useState } from 'react'
import { AimOutlined, ApartmentOutlined, CheckCircleOutlined, FileOutlined, LoginOutlined, SafetyOutlined, UndoOutlined, UserOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons'
import type { ActionResultStory, StoryTraceEvent } from '../../api/currentChecks'

export const traceKindLabels = { ENTRY: '请求进入', IDENTITY: '身份识别', AUTHORIZATION: '权限判断', PERSISTENT_EFFECT: '持久业务变化', MESSAGE: '任务派发', DELEGATION: '委托执行', FINAL_EFFECT: '最终业务结果', RECOVERY: '恢复操作' }
const nodeIcons = { ENTRY: LoginOutlined, IDENTITY: UserOutlined, AUTHORIZATION: SafetyOutlined, PERSISTENT_EFFECT: FileOutlined, MESSAGE: ApartmentOutlined, DELEGATION: ApartmentOutlined, FINAL_EFFECT: CheckCircleOutlined, RECOVERY: UndoOutlined }

export function ExecutionPath({ action, selectedEvent, onSelect }: {
  action: ActionResultStory; selectedEvent?: string; onSelect: (event: StoryTraceEvent, refs: string[]) => void
}) {
  const path = action.execution_path
  const marker = useId().replace(/:/g, '')
  const [expanded, setExpanded] = useState(false)
  const [zoom, setZoom] = useState(1)
  const viewport = useRef<HTMLDivElement>(null)
  if (!path?.events.length) return <p className="path-unavailable">没有可展示的完整执行关系。以下只对照已发布事实，不从页面回应推断后台路径。</p>
  // 输入顺序已由严格 Trace 模型拓扑排序；布局只沿这些父引用，不连接时间上相邻节点。
  const positions = new Map<string, { x: number; y: number }>()
  const rows = new Map<number, number>()
  path.events.forEach(event => {
    const column = Math.max(-1, ...event.parent_event_ids.map(parent => (positions.get(parent)?.x ?? -256) / 256)) + 1
    const row = rows.get(column) ?? 0
    positions.set(event.event_id, { x: column * 256, y: row * 136 }); rows.set(column, row + 1)
  })
  const rowCount = Math.max(...rows.values())
  positions.forEach(position => { position.y += (rowCount - rows.get(position.x / 256)!) * 68 })
  const width = Math.max(...Array.from(positions.values(), p => p.x)) + 216
  const height = (rowCount - 1) * 136 + 96
  const fit = () => { setZoom(Math.min(1, Math.max(.5, ((viewport.current?.clientWidth ?? width) - 32) / width))); viewport.current?.scrollTo?.({ left: 0, top: 0 }) }
  return <section className="execution-path" aria-label="已发布执行路径">
    <div className="execution-path-heading"><div><h3>已发布执行路径</h3><p>{path.complete ? '已发布的父子关系' : '路径不完整 · 只展示已知关系'}</p></div><div className="path-tools" aria-label="执行路径视图"><button aria-label="缩小执行路径" disabled={zoom <= .5} onClick={() => setZoom(value => Math.max(.5, value - .1))}><ZoomOutOutlined /></button><button aria-label="放大执行路径" disabled={zoom >= 1.5} onClick={() => setZoom(value => Math.min(1.5, value + .1))}><ZoomInOutlined /></button><button aria-label="适应执行路径宽度" onClick={fit}><AimOutlined /></button></div></div>
    {path.events.length > 32 && !expanded ? <div className="path-large"><p>本项包含 {path.events.length} 个已发布节点。</p><button onClick={() => setExpanded(true)}>展开完整执行路径</button></div> : <div className="path-scroll" ref={viewport} tabIndex={0} aria-label="横向或纵向滚动查看执行路径">
      <div className="path-stage" style={{ width: width * zoom, height: height * zoom }}><div className="path-canvas" style={{ width, height, transform:`scale(${zoom})` }}>
        <svg width={width} height={height} aria-hidden="true"><defs><marker id={marker} markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto"><path d="M0,0 L7,3.5 L0,7" fill="currentColor"/></marker></defs>
          {path.events.flatMap(event => event.parent_event_ids.map(parent => {
            const start = positions.get(parent), end = positions.get(event.event_id)
            if (!start || !end) return null
            return <path key={`${parent}/${event.event_id}`} data-parent={parent} data-child={event.event_id} d={`M${start.x + 216},${start.y + 48} C${start.x + 236},${start.y + 48} ${end.x - 20},${end.y + 48} ${end.x},${end.y + 48}`} markerEnd={`url(#${marker})`}/>
          }))}
        </svg>
        {path.events.map(event => {
          const position = positions.get(event.event_id)!
          const effect = action.fact_comparison.effects.find(item => item.effect_id === event.effect_id)
          const label = event.kind === 'AUTHORIZATION' && event.authorization_decision ? `权限判断 · ${event.authorization_decision === 'DENY' ? '拒绝' : '允许'}` : traceKindLabels[event.kind]
          const exact = action.breakpoint?.precision === 'EXACT' && action.breakpoint.first_violation_event_id === event.event_id
          const Icon = nodeIcons[event.kind]
          return <button key={event.event_id} className={`path-node${exact ? ' path-node-breakpoint' : ''}`} style={{ left: position.x, top: position.y }} aria-label={`查看${label}的发布证据`} aria-pressed={selectedEvent === event.event_id} onClick={() => onSelect(event, path.evidence_refs)}>
            <Icon className="path-node-icon" aria-hidden="true"/><span className="path-node-copy"><span>{label}</span><strong>{effect?.business_label || event.source_component}</strong></span>{exact && <small>首个可证明断裂</small>}
          </button>
        })}
      </div></div>
    </div>}
    <p className="path-boundary">连线仅代表已发布的父子引用。节点存在不单独证明业务后果或权限安全。</p>
  </section>
}
