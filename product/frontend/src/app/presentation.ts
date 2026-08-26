// 集中维护用户可见路由、状态标签和时间格式，避免页面直接展示内部枚举。

export type AppRoute =
  | '/workspace'
  | '/apps/access'
  | '/apps/identities'
  | '/apps/flows'
  | '/apps/rules'
  | '/checks/start'
  | '/checks/results'
  | '/checks/history'
  | '/settings/models'
  | '/settings/system'

export const navigationGroups = [
  { key: 'apps', label: '应用', items: [{ key: '/apps/access', label: '应用接入' }, { key: '/apps/identities', label: '测试账号' }, { key: '/apps/flows', label: '业务流程' }, { key: '/apps/rules', label: '权限规则' }] },
  { key: 'checks', label: '检查', items: [{ key: '/checks/start', label: '开始检查' }, { key: '/checks/results', label: '检查结果' }, { key: '/checks/history', label: '历史变化' }] },
] as const

export function normalizeRoute(pathname: string): AppRoute {
  if (pathname === '/workspace') return pathname
  if (pathname === '/settings/models' || pathname === '/settings/system') return pathname
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

const productStatusLabels = {
  project: { DRAFT: '草稿', READY: '已就绪', REGISTERED: '已登记', ARCHIVED: '已归档' },
  contract: { DRAFT: '草稿', REVIEW: '待审阅', ACTIVE: '已激活', REJECTED: '已拒绝', RETIRED: '已停用' },
} as const

const productTermLabels = {
  identity: { attacker: '攻击者', owner: '所有者', peer: '同级用户', guest: '访客', admin: '管理员', member: '成员', user: '普通用户' },
  role: { attacker: '攻击者', owner: '所有者', peer: '同级用户', guest: '访客', admin: '管理员', member: '成员', user: '普通用户' },
  action: { create: '创建', read: '读取', view: '查看', list: '列出', modify: '修改', update: '修改', write: '写入', delete: '删除', approve: '审批' },
  resource: { 'attacker-resource': '攻击者资源', 'owner-resource': '所有者资源', document: '文档' },
  resourceType: { document: '文档' },
  relation: { OWNS: '拥有', owns: '拥有', SAME_TENANT: '同一租户', same_tenant: '同一租户', BELONGS_TO: '属于', belongs_to: '属于', MEMBER_OF: '隶属', member_of: '隶属' },
} as const

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

export function productStatusLabel(kind: keyof typeof productStatusLabels, value: unknown) {
  const raw = String(value ?? '')
  return (productStatusLabels[kind] as Record<string, string>)[raw] ?? (raw || '未知')
}

// 业务含义优先使用中文；协议标识仍保留在括号中，便于对照契约和排错。
export function productTermLabel(kind: keyof typeof productTermLabels, value: unknown, preserveRaw = true) {
  const raw = String(value ?? '')
  if (!raw) return '未提供'
  const translated = (productTermLabels[kind] as Record<string, string>)[raw]
  return translated ? preserveRaw ? `${translated}（${raw}）` : translated : raw
}

export function formatTimestamp(value: unknown) {
  if (value === undefined || value === null || value === '') return '时间未提供'
  const numeric = Number(value)
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000_000 ? numeric / 1000 : numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(String(value))
  return Number.isNaN(date.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
