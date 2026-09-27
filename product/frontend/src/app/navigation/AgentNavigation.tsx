// 协作内导航把交付流程与连接设置分开，不把修改记录藏进检查历史。
export function AgentNavigation({ active, onNavigate }: { active: 'delivery' | 'connection'; onNavigate: (path: string) => void }) {
  return <nav className="record-navigation" aria-label="Agent 协作导航"><button aria-current={active === 'delivery' ? 'page' : undefined} onClick={() => onNavigate('/changes')}>修复任务与修改</button><button aria-current={active === 'connection' ? 'page' : undefined} onClick={() => onNavigate('/tools')}>连接与授权</button></nav>
}
