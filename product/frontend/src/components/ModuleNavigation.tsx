// 工作台独立承担主控入口，变化、权限和测试收在专项工作区；详细任务不进入主导航。

import { AppstoreOutlined, DiffOutlined, ExperimentOutlined, MenuOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { Button, Drawer, Typography } from 'antd'
import { useRef, useState } from 'react'
import type { WorkspaceAreaDto } from '../api/workspace'
import { productAreas, type AppRoute, type ProductAreaRoute } from '../app/presentation'

type ProductAreas = WorkspaceAreaDto[] | null
type AreaStatus = WorkspaceAreaDto['status'] | 'EMPTY'

function activeArea(route: AppRoute): ProductAreaRoute {
  if (route === '/application') return '/workspace'
  if (route === '/identities' || route === '/flows') return '/permissions'
  if (route === '/preparation' || route === '/validation' || route === '/results' || route === '/verification' || route === '/history') return '/tests'
  return productAreas.some((area) => area.route === route) ? route as ProductAreaRoute : '/workspace'
}

function ModuleIcon({ route }: { route: ProductAreaRoute }) {
  if (route === '/workspace') return <AppstoreOutlined />
  if (route === '/changes') return <DiffOutlined />
  if (route === '/permissions') return <SafetyCertificateOutlined />
  return <ExperimentOutlined />
}

function NavigationState({ status, label }: { status: AreaStatus; label: string }) {
  const marker = status === 'NEEDS_ATTENTION' ? '!' : status === 'EMPTY' ? '·' : '•'
  return <span className="module-navigation-state" title={label} aria-hidden="true">{marker}</span>
}

function ModuleList({ route, areas, onNavigate }: {
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  const selectedRoute = activeArea(route)
  const workbench = productAreas[0]
  const workbenchArea = areas?.find((item) => item.route === workbench.route)
  const workbenchStatus: AreaStatus = workbenchArea?.status ?? 'READY'
  const workbenchSelected = selectedRoute === workbench.route
  return <>
    <div className="module-workbench-group">
      <button type="button" className={`module-workbench-button is-${workbenchStatus.toLowerCase()}${workbenchSelected ? ' is-selected' : ''}`} aria-label={`${workbench.label}，${workbenchArea?.status_label ?? '可以开始'}`} aria-current={workbenchSelected ? 'page' : undefined} onClick={() => onNavigate(workbench.route)}>
        <span className="module-workbench-icon" aria-hidden="true"><AppstoreOutlined /></span>
        <span className="module-navigation-label">{workbench.label}</span>
        <NavigationState status={workbenchStatus} label={workbenchArea?.status_label ?? '可以开始'} />
      </button>
    </div>
    <div className="module-navigation-group">
      <Typography.Text className="module-navigation-title">专项工作</Typography.Text>
      <ul className="module-navigation-list">
      {productAreas.slice(1).map((fallback) => {
        const area = areas?.find((item) => item.route === fallback.route)
        const status: AreaStatus = area?.status ?? (fallback.route === '/workspace' ? 'READY' : 'EMPTY')
        const selected = selectedRoute === fallback.route
        return <li className={`module-navigation-item is-${status.toLowerCase()}${selected ? ' is-selected' : ''}`} key={fallback.route}>
          <button type="button" className="module-navigation-button" aria-label={`${fallback.label}，${area?.status_label ?? '等待应用'}`} aria-current={selected ? 'page' : undefined} onClick={() => onNavigate(fallback.route)}>
            <span className="module-navigation-icon" aria-hidden="true"><ModuleIcon route={fallback.route} /></span>
            <span className="module-navigation-label">{fallback.label}</span>
            <NavigationState status={status} label={area?.status_label ?? '等待应用'} />
          </button>
        </li>
      })}
      </ul>
    </div>
  </>
}

export function DesktopModuleNavigation({ route, areas, onNavigate }: {
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  return <aside className="module-navigation" aria-label="界鉴主导航">
    <div className="product-brand"><strong>界鉴</strong><span>持续权限验证</span></div>
    <nav aria-label="持续验证工作区"><ModuleList route={route} areas={areas} onNavigate={onNavigate} /></nav>
  </aside>
}

export function MobileModuleNavigation({ route, areas, onNavigate }: {
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const selectedRoute = activeArea(route)
  const selected = areas?.find((area) => area.route === selectedRoute)
  const fallback = productAreas.find((area) => area.route === selectedRoute)
  const summary = route.startsWith('/settings/') ? '设置' : fallback?.label ?? selected?.label ?? '持续验证工作区'
  const navigateFromDrawer = (path: AppRoute) => { setOpen(false); onNavigate(path) }
  return <>
    <div className="mobile-module-summary">
      <Button ref={triggerRef} type="text" icon={<MenuOutlined />} aria-label="打开持续验证工作区" onClick={() => setOpen(true)} />
      <Typography.Text strong>{summary}</Typography.Text>
    </div>
    <Drawer
      className="module-navigation-drawer"
      title="界鉴工作区域"
      placement="left"
      width={320}
      open={open}
      onClose={() => setOpen(false)}
      afterOpenChange={(isOpen) => {
        if (isOpen) (document.querySelector('.module-navigation-drawer .module-workbench-button.is-selected, .module-navigation-drawer .module-navigation-item.is-selected .module-navigation-button') as HTMLElement | null)?.focus()
        else triggerRef.current?.focus()
      }}
    >
      <nav aria-label="持续验证工作区"><ModuleList route={route} areas={areas} onNavigate={navigateFromDrawer} /></nav>
    </Drawer>
  </>
}
