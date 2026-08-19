// 集中维护用户可见路由、状态标签和时间格式，避免页面直接展示内部枚举。

export type AppRoute =
  | '/workspace'
  | '/apps/access'
  | '/apps/rules'
  | '/checks/start'
  | '/checks/results'
  | '/checks/history'
  | '/advanced/recording'
  | '/advanced/models'
  | '/advanced/system'

export const navigationGroups = [
  { key: 'apps', label: '应用', items: [{ key: '/apps/access', label: '应用接入' }, { key: '/apps/rules', label: '权限规则' }] },
  { key: 'checks', label: '检查', items: [{ key: '/checks/start', label: '开始检查' }, { key: '/checks/results', label: '检查结果' }, { key: '/checks/history', label: '历史变化' }] },
  { key: 'advanced', label: '高级', items: [{ key: '/advanced/recording', label: '流程录制' }, { key: '/advanced/models', label: '模型服务' }, { key: '/advanced/system', label: '运行环境' }] },
] as const

export function normalizeRoute(pathname: string): AppRoute {
  if (pathname === '/workspace') return pathname
  if (navigationGroups.some((group) => group.items.some((item) => item.key === pathname))) return pathname as AppRoute
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

export const integrityLabels: Record<string, string> = {
  VERIFIED: '结果完整',
  INVALID: '结果无效',
  UNAVAILABLE: '结果尚未确认',
}

export function lifecycleLabel(value: unknown) {
  return lifecycleLabels[String(value ?? '')] ?? '未知'
}

export function verdictLabel(value: unknown) {
  return verdictLabels[String(value ?? '')] ?? '尚无结论'
}

export function integrityLabel(value: unknown) {
  return integrityLabels[String(value ?? '')] ?? '未知'
}

export const severityLabels: Record<string, string> = {
  low: '低', medium: '中', high: '高', critical: '严重',
}

export const expectationLabels: Record<string, string> = {
  ALLOW: '允许', DENY: '拒绝',
}

export const occurrenceStatusLabels: Record<string, string> = {
  APPEARED: '首次出现', PRESENT: '仍然存在', DISAPPEARED: '已不再出现',
  REAPPEARED: '再次出现', CHANGED: '状态发生变化',
}

export const gateDecisionLabels: Record<string, string> = {
  PASS: '门禁通过', BLOCK: '门禁阻断', INCONCLUSIVE: '门禁证据不足', ERROR: '门禁错误',
}

export function severityLabel(value: unknown) {
  return severityLabels[String(value ?? '').toLowerCase()] ?? '未知'
}

export function expectationLabel(value: unknown) {
  return expectationLabels[String(value ?? '')] ?? '未知'
}

export function occurrenceStatusLabel(value: unknown) {
  return occurrenceStatusLabels[String(value ?? '')] ?? '未知'
}

export function gateDecisionLabel(value: unknown) {
  return gateDecisionLabels[String(value ?? '')] ?? '未知'
}

export function formatTimestamp(value: unknown) {
  if (value === undefined || value === null || value === '') return '时间未提供'
  const numeric = Number(value)
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000_000 ? numeric / 1000 : numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(String(value))
  return Number.isNaN(date.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
