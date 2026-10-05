// 通知状态立即更新；仅保留短暂、不可交互且不参与播报的退出画面。
import { useLayoutEffect, useState, type ReactNode } from 'react'
import { metrics } from './tokens'

export function MotionPresenceList<T extends { key:string }>({items, children}:{items:T[];children:(item:T)=>ReactNode}) {
  const [retained,setRetained] = useState(items)
  const active = new Set(items.map(item=>item.key))
  const leaving = retained.filter(item=>!active.has(item.key))
  useLayoutEffect(()=>{
    const duration = document.documentElement.dataset.motion === 'off' ? 0 : document.documentElement.dataset.motion === 'soft' ? metrics.motion.fast : metrics.motion.layer
    if (!duration || !leaving.length) { setRetained(items); return }
    // 重新出现的同一通知采用新内容；旧退出画面不会拦截点击，也不延迟业务回调。
    setRetained([...items,...leaving])
    const timer = setTimeout(()=>setRetained(items),duration)
    return ()=>clearTimeout(timer)
  },[items])
  return <>{[...items,...leaving].map(item=><div key={item.key} className="motion-presence-item" data-leaving={!active.has(item.key)} aria-hidden={!active.has(item.key) || undefined} inert={!active.has(item.key) || undefined}>{children(item)}</div>)}</>
}
