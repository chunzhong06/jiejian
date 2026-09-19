// 当前工作、权限规则、代码变化与检查历史保持自由导航；系统状态入口在导航底部。

import { AppstoreOutlined, HistoryOutlined, MenuOutlined, SafetyCertificateOutlined, BranchesOutlined, RightOutlined } from '@ant-design/icons'
import { Button, Drawer, Typography } from 'antd'
import { useRef, useState } from 'react'
import type { SystemStatus } from '../api/system'
import { systemStatusLabel } from '../app/AppHeader'
import type { WorkspaceAreaDto } from '../api/workspace'
import { productAreas, type AppRoute, type ProductAreaRoute } from '../app/presentation'

type ProductAreas = WorkspaceAreaDto[] | null
type AreaStatus = WorkspaceAreaDto['status'] | 'EMPTY'

function activeArea(route: AppRoute): ProductAreaRoute {
  if (route === '/application') return '/workspace'
  if (route === '/identities' || route === '/flows') return '/workspace'
  if (route === '/history') return '/history'
  if (route === '/tests' || route === '/preparation' || route === '/validation' || route === '/results' || route === '/verification') return '/workspace'
  return productAreas.some((area) => area.route === route) ? route as ProductAreaRoute : '/workspace'
}

function ModuleIcon({ route }: { route: ProductAreaRoute }) {
  if (route === '/workspace') return <AppstoreOutlined />
  if (route === '/permissions') return <SafetyCertificateOutlined />
  if (route === '/changes') return <BranchesOutlined />
  return <HistoryOutlined />
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
  return <ul className="module-navigation-list">
    {productAreas.map((fallback) => {
      const area = areas?.find((item) => item.route === (fallback.route === '/history' ? '/tests' : fallback.route))
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
}

export function DesktopModuleNavigation({ route, areas, onNavigate, systemStatus }: {
  systemStatus?: SystemStatus
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  return <aside className="module-navigation" aria-label="界鉴主导航">
    <div className="product-brand"><SafetyCertificateOutlined aria-hidden="true" /><strong>界鉴</strong></div>
    <nav aria-label="持续验证工作区"><ModuleList route={route} areas={areas} onNavigate={onNavigate} /></nav>
    <SystemEntry status={systemStatus} onClick={() => onNavigate('/settings/system')} />
  </aside>
}

export function MobileModuleNavigation({ route, areas, onNavigate, systemStatus }: {
  systemStatus?: SystemStatus
  route: AppRoute
  areas: ProductAreas
  onNavigate: (path: AppRoute) => void
}) {
  const [open, setOpen] = useState(false)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const selectedRoute = activeArea(route)
  const selected = areas?.find((area) => area.route === selectedRoute)
  const fallback = productAreas.find((area) => area.route === selectedRoute)
  const summary = route.startsWith('/settings/') ? '设置' : fallback?.label ?? '当前工作'
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
      <SystemEntry status={systemStatus} onClick={() => navigateFromDrawer('/settings/system')} />
    </Drawer>
  </>
}

// 系统入口同时呈现状态和诊断导航；缺少回执不能显示为正常。
function SystemEntry({ status, onClick }: { status?: SystemStatus; onClick: () => void }) {
  const label = status ? systemStatusLabel(status) : "状态未知"
  return <Button className="navigation-system" type="text" onClick={onClick} aria-label={`${label}，打开系统详情`}><i data-state={label === "系统正常" ? "ready" : label === "状态未知" ? "unknown" : "warning"} aria-hidden="true"/><span>{label}</span><RightOutlined aria-hidden="true"/></Button>
}
