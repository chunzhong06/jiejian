// 应用壳的页面路由与一级导航；业务状态格式不进入此入口。
export type AppRoute =
  | '/workspace'
  | '/application'
  | '/environment'
  | '/changes'
  | '/permissions'
  | '/tests'
  | '/preparation'
  | '/identities'
  | '/flows'
  | '/validation'
  | '/results'
  | '/verification'
  | '/history'
  | '/tools'
  | '/settings/system'

export type ProductAreaRoute = '/workspace' | '/changes' | '/permissions' | '/tests' | '/history'

export const productAreas = [
  { route: '/workspace', label: '总览', shortLabel: '总览' },
  { route: '/permissions', label: '权限', shortLabel: '权限' },
  { route: '/tests', label: '检查', shortLabel: '检查' },
  { route: '/changes', label: '源码改动', shortLabel: '源码改动' },
] as const

export function normalizeRoute(pathname: string): AppRoute {
  if (pathname === '/environment') return pathname
  if (productAreas.some((area) => area.route === pathname)) return pathname as ProductAreaRoute
  if (pathname === '/tests' || pathname === '/changes' || pathname === '/application' || pathname === '/identities' || pathname === '/flows' || pathname === '/preparation' || pathname === '/validation' || pathname === '/results' || pathname === '/verification' || pathname === '/history') return pathname
  if (pathname === '/tools' || pathname === '/settings/system') return pathname
  return '/workspace'
}
