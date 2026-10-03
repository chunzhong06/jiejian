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
  { route: '/workspace', label: '概览', shortLabel: '概览' },
  { route: '/permissions', label: '权限要求', shortLabel: '权限要求' },
  { route: '/changes', label: '修改与验证', shortLabel: '修改与验证' },
  { route: '/history', label: '检查记录', shortLabel: '检查记录' },
] as const

export function normalizeRoute(pathname: string): AppRoute {
  if (pathname === '/environment') return pathname
  if (productAreas.some((area) => area.route === pathname)) return pathname as ProductAreaRoute
  if (pathname === '/tests' || pathname === '/changes' || pathname === '/application' || pathname === '/identities' || pathname === '/flows' || pathname === '/preparation' || pathname === '/validation' || pathname === '/results' || pathname === '/verification' || pathname === '/history') return pathname
  if (pathname === '/tools' || pathname === '/settings/system') return pathname
  return '/workspace'
}
