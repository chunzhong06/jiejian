// 记录与证据共用页签，历史查询和代码变化仍由各自现有页面负责。
export function RecordNavigation({active,onNavigate}:{active:'history'|'changes';onNavigate:(path:string)=>void}) {
 return <nav className="record-navigation" aria-label="记录与证据"><button aria-current={active==='history'?'page':undefined} onClick={()=>onNavigate('/history')}>检查记录</button><button aria-current={active==='changes'?'page':undefined} onClick={()=>onNavigate('/changes')}>代码变化</button></nav>
}
