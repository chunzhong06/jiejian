// 协作内导航把交付流程与连接设置分开，不把修改记录藏进检查历史。
export type CollaborationView = 'handoff' | 'deliveries' | 'acceptance'
export function AgentNavigation({ active, onNavigate, view = 'handoff', onSelectView }: { active: 'delivery' | 'connection'; onNavigate: (path: string) => void; view?: CollaborationView; onSelectView?: (view: CollaborationView) => void }) {
  return <nav className="record-navigation" aria-label="Agent 协作导航">{([['handoff', '需求与交接'], ['deliveries', '交付记录'], ['acceptance', '验收结果']] as const).map(([key, label]) => <button key={key} aria-current={active === 'delivery' && view === key ? 'page' : undefined} onClick={() => onSelectView ? onSelectView(key) : onNavigate('/changes?view=' + key)}>{label}</button>)}<button aria-current={active === 'connection' ? 'page' : undefined} onClick={() => onNavigate('/tools')}>连接与授权</button></nav>
}
