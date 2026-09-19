// 集中维护用户可见路由、流程状态、状态标签和时间格式，避免页面直接展示内部枚举。

export type AppRoute =
  | '/workspace'
  | '/application'
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
  { route: '/workspace', label: '当前工作', shortLabel: '当前工作' },
  { route: '/permissions', label: '权限规则', shortLabel: '权限规则' },
  { route: '/changes', label: '代码变化', shortLabel: '代码变化' },
  { route: '/history', label: '检查历史', shortLabel: '检查历史' },
] as const

export function normalizeRoute(pathname: string): AppRoute {
  if (productAreas.some((area) => area.route === pathname)) return pathname as ProductAreaRoute
  if (pathname === '/tests' || pathname === '/changes' || pathname === '/application' || pathname === '/identities' || pathname === '/flows' || pathname === '/preparation' || pathname === '/validation' || pathname === '/results' || pathname === '/verification' || pathname === '/history') return pathname
  if (pathname === '/tools' || pathname === '/settings/system') return pathname
  return '/workspace'
}

export const lifecycleLabels: Record<string, string> = {
  PENDING: '等待处理',
  QUEUED: '等待处理',
  RUNNING: '正在检查',
  COMPLETED: '已完成',
  SUCCEEDED: '已完成',
  FAILED: '检查失败',
  CANCELLED: '已取消',
  SAFETY_STOPPED: '已安全停止',
  RETRY_WAIT: '等待重试',
}

export const verdictLabels: Record<string, string> = {
  PASS: '当前规则覆盖范围内未发现越权',
  SAFE: '当前规则覆盖范围内未发现越权',
  BLOCK: '发现可能的权限越界，需要处理',
  VULNERABLE: '发现可能的权限越界，需要处理',
  INCONCLUSIVE: '证据不足，暂时不能下结论',
  INVALID: '结果无效，不能形成安全结论',
}

export function lifecycleLabel(value: unknown) {
  return lifecycleLabels[String(value ?? '')] ?? '未知'
}

export function verdictLabel(value: unknown) {
  return verdictLabels[String(value ?? '')] ?? '尚无结论'
}

export function formatTimestamp(value: unknown) {
  if (value === undefined || value === null || value === '') return '时间未提供'
  const numeric = Number(value)
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000_000 ? numeric / 1000 : numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(String(value))
  return Number.isNaN(date.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
