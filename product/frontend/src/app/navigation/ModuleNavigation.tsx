// 一级导航只切换业务工作面；具体准备项与历史通过所属页面或入口搜索进入。
import { useLayoutEffect, useRef } from 'react'
import type { WorkspaceAreaDto } from '../../api/workspace'
import { productAreas, type AppRoute, type ProductAreaRoute } from './routes'

function activeArea(route: AppRoute): ProductAreaRoute | null {
  if (['/tools', '/environment', '/settings/system'].includes(route)) return null
  if (route === '/application') return '/workspace'
  if (['/history', '/identities', '/flows', '/preparation', '/validation', '/results', '/verification'].includes(route)) return '/tests'
  return productAreas.some(area => area.route === route) ? route as ProductAreaRoute : '/workspace'
}

export function ModuleNavigation({ route, areas, onNavigate }: {
  route: AppRoute; areas: WorkspaceAreaDto[] | null; onNavigate: (path: AppRoute) => void
}) {
  const selectedRoute = activeArea(route)
  const list = useRef<HTMLUListElement>(null)
  const indicator = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const container = list.current
    const line = indicator.current
    if (!container || !line) return
    const measure = () => {
      const button = container.querySelector<HTMLButtonElement>('[aria-current=page]')
      line.hidden = !button
      if (!button) return
      const parent = container.getBoundingClientRect()
      const bounds = button.getBoundingClientRect()
      line.style.width = `${bounds.width}px`
      line.style.transform = `translateX(${bounds.left - parent.left}px)`
    }
    measure()
    // 只观察布局尺寸；字体到达和窄屏换行后仍跟随真实按钮，快速点击由 CSS 连续接续。
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    observer?.observe(container)
    container.querySelectorAll('button').forEach(button => observer?.observe(button))
    window.addEventListener('resize', measure)
    return () => { observer?.disconnect(); window.removeEventListener('resize', measure) }
  }, [selectedRoute])
  return <nav className="module-navigation" aria-label="界鉴主导航"><ul ref={list} className="module-navigation-list">
    {productAreas.map(item => {
      const status = areas?.find(area => area.route === item.route)
      return <li className={`module-navigation-item${selectedRoute === item.route ? ' is-selected' : ''}`} key={item.route}>
        <button type="button" className="module-navigation-button" aria-label={item.label} title={status?.status_label} aria-current={selectedRoute === item.route ? 'page' : undefined} onClick={() => onNavigate(item.route)}>
          <span className="module-navigation-label">{item.label}</span>
          {status?.status === 'NEEDS_ATTENTION' && <span className="module-navigation-dot" title={status.status_label} aria-label={status.status_label} />}
        </button>
      </li>
    })}
  </ul><span ref={indicator} className="module-navigation-indicator" aria-hidden="true" hidden={!selectedRoute} /></nav>
}
