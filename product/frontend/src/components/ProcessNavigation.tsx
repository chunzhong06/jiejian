// 长期工作区导航：状态来自后端当前事实，页面位置只表示用户正在查看哪个区域。

import { CheckCircleFilled, ExclamationCircleFilled, LoadingOutlined, LockOutlined, MenuOutlined, MinusCircleOutlined } from '@ant-design/icons'
import { Button, Drawer, Typography } from 'antd'
import { useRef, useState } from 'react'
import type { ProductStatusDto } from '../api/projects'
import { productAreas, type AppRoute, type ProductAreaRoute } from '../app/presentation'

type ProductAreas = ProductStatusDto['areas'] | null
type AreaStatus = ProductStatusDto['areas'][number]['status']

function activeArea(route: AppRoute): ProductAreaRoute {
  if (route === '/application') return '/workspace'
  if (route === '/identities' || route === '/flows') return '/preparation'
  if (route === '/verification' || route === '/history') return '/results'
  return productAreas.some((area) => area.route === route) ? route as ProductAreaRoute : '/workspace'
}

function AreaIcon({ status }: { status: AreaStatus }) {
  if (status === 'READY' || status === 'AVAILABLE') return <CheckCircleFilled />
  if (status === 'NEEDS_ATTENTION') return <ExclamationCircleFilled />
  if (status === 'RUNNING') return <LoadingOutlined />
  if (status === 'BLOCKED') return <LockOutlined />
  return <MinusCircleOutlined />
}

function AreaList({ route, areas, onNavigate }: {
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  const selectedRoute = activeArea(route)
  return <div className="process-flow-group">
    <Typography.Text className="process-group-title">持续验证工作区</Typography.Text>
    <ul className="process-step-list">
      {productAreas.map((fallback) => {
        const area = areas?.find((item) => item.route === fallback.route)
        const status: AreaStatus = area?.status ?? (fallback.route === '/workspace' ? 'READY' : 'EMPTY')
        const selected = selectedRoute === fallback.route
        return <li className={`process-step is-${status.toLowerCase()}${selected ? ' is-selected' : ''}`} key={fallback.route}>
          <button type="button" className="process-step-button" aria-current={selected ? 'page' : undefined} onClick={() => onNavigate(fallback.route)}>
            <span className="process-step-marker" aria-hidden="true"><AreaIcon status={status} /></span>
            <span className="process-step-copy">
              <span className="process-step-label">{area?.label ?? fallback.label}</span>
              <span className="process-step-state">{area?.status_label ?? (fallback.route === '/workspace' ? '可以开始' : '等待应用')}</span>
            </span>
          </button>
        </li>
      })}
    </ul>
  </div>
}

export function DesktopProcessNavigation({ route, areas, onNavigate }: {
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  return <aside className="process-navigation" aria-label="界鉴主导航">
    <div className="product-brand"><strong>界鉴</strong><span>持续权限验证</span></div>
    <nav aria-label="持续验证工作区"><AreaList route={route} areas={areas} onNavigate={onNavigate} /></nav>
  </aside>
}

export function MobileProcessNavigation({ route, areas, onNavigate }: {
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const selectedRoute = activeArea(route)
  const selected = areas?.find((area) => area.route === selectedRoute)
  const fallback = productAreas.find((area) => area.route === selectedRoute)
  const summary = route.startsWith('/settings/') ? '设置' : selected?.label ?? fallback?.label ?? '持续验证工作区'
  const navigateFromDrawer = (path: AppRoute) => { setOpen(false); onNavigate(path) }
  return <>
    <div className="mobile-process-summary">
      <Button ref={triggerRef} type="text" icon={<MenuOutlined />} aria-label="打开持续验证工作区" onClick={() => setOpen(true)} />
      <Typography.Text strong>{summary}</Typography.Text>
    </div>
    <Drawer
      className="process-drawer"
      title="界鉴持续验证工作区"
      placement="left"
      width={320}
      open={open}
      onClose={() => setOpen(false)}
      afterOpenChange={(isOpen) => {
        if (isOpen) (document.querySelector('.process-drawer .process-step.is-selected .process-step-button') as HTMLElement | null)?.focus()
        else triggerRef.current?.focus()
      }}
    >
      <nav aria-label="持续验证工作区"><AreaList route={route} areas={areas} onNavigate={navigateFromDrawer} /></nav>
    </Drawer>
  </>
}
