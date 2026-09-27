// 三个产品入口保持自由导航；记录页签保留历史与变化的独立深链。

import { AppstoreOutlined, HistoryOutlined, SafetyCertificateOutlined, BranchesOutlined, RightOutlined } from '@ant-design/icons'
import { Button } from 'antd'
import type { SystemStatus } from '../../api/system'
import { systemStatusLabel } from '../AppHeader'
import type { WorkspaceAreaDto } from '../../api/workspace'
import { productAreas, type AppRoute, type ProductAreaRoute } from '../presentation'

type ProductAreas = WorkspaceAreaDto[] | null
type AreaStatus = WorkspaceAreaDto['status'] | 'EMPTY'

function activeArea(route: AppRoute): ProductAreaRoute {
  if (route === '/application') return '/workspace'
  if (route === '/identities' || route === '/flows') return '/workspace'
  if (route === '/history' || route === '/changes') return '/history'
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
  return <div className="mobile-module-summary"><strong className="mobile-brand">界鉴</strong><nav aria-label="持续验证工作区"><ModuleList route={route} areas={areas} onNavigate={onNavigate}/></nav><SystemEntry status={systemStatus} onClick={()=>onNavigate('/settings/system')}/></div>
}

// 系统入口同时呈现状态和诊断导航；缺少回执不能显示为正常。
function SystemEntry({ status, onClick }: { status?: SystemStatus; onClick: () => void }) {
  const label = status ? systemStatusLabel(status) : "状态未知"
  return <Button className="navigation-system" type="text" onClick={onClick} aria-label={`${label}，打开系统详情`}><i data-state={label === "系统正常" ? "ready" : label === "状态未知" ? "unknown" : "warning"} aria-hidden="true"/><span>{label}</span><RightOutlined aria-hidden="true"/></Button>
}
