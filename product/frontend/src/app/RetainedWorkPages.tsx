// 仅在当前项目的页面会话内保留工作输入与位置；不缓存设置/密钥页面，不写浏览器持久存储。
import { createContext, useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'

export const WorkPageVisible = createContext(true)

export function RetainedWorkPages({ activeKey, children }: { activeKey: string | null; children: ReactNode }) {
  const pages = useRef(new Map<string, ReactNode>())
  const positions = useRef(new Map<string, number>())
  if (activeKey) pages.current.set(activeKey, children)
  useEffect(() => {
    const remember = () => { if (activeKey) positions.current.set(activeKey, window.scrollY) }
    window.addEventListener('scroll', remember, { passive: true })
    return () => window.removeEventListener('scroll', remember)
  }, [activeKey])
  useLayoutEffect(() => {
    window.scrollTo({ top: activeKey ? positions.current.get(activeKey) ?? 0 : 0, behavior: 'instant' })
  }, [activeKey])
  return <>{Array.from(pages.current, ([key, page]) => <WorkPageVisible.Provider key={key} value={key === activeKey}><div hidden={key !== activeKey}>{page}</div></WorkPageVisible.Provider>)}{!activeKey && children}</>
}
