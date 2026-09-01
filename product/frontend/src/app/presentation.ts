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
  | '/settings/models'
  | '/settings/system'

export type ProductAreaRoute = '/workspace' | '/changes' | '/permissions' | '/tests'

export const productAreas = [
  { route: '/workspace', label: '工作台', shortLabel: '工作台' },
  { route: '/changes', label: '变化', shortLabel: '变化' },
  { route: '/permissions', label: '权限', shortLabel: '权限' },
  { route: '/tests', label: '测试', shortLabel: '测试' },
] as const

export function normalizeRoute(pathname: string): AppRoute {
  if (productAreas.some((area) => area.route === pathname)) return pathname as ProductAreaRoute
  if (pathname === '/application' || pathname === '/identities' || pathname === '/flows' || pathname === '/preparation' || pathname === '/validation' || pathname === '/results' || pathname === '/verification' || pathname === '/history') return pathname
  if (pathname === '/tools' || pathname === '/settings/models' || pathname === '/settings/system') return pathname
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
  project: { DRAFT: '草稿', READY: '已就绪', ARCHIVED: '已归档' },
  contract: { DRAFT: '草稿', REVIEW: '待审阅', ACTIVE: '已激活', SUPERSEDED: '已被更新版本替代', REJECTED: '已拒绝' },
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

const traceSemanticLabels: Record<string, string> = {
  request_received: '请求进入目标应用',
  server_identity_resolved: '目标应用识别出实际账号',
  authorization_decided: '目标应用作出权限判断',
  export_request_created: '后台导出任务已经创建',
  export_message_sent: '导出消息进入后台链路',
  feature_export_entered: '请求进入导出功能',
  service_authority_expanded: '后台服务获得继续执行权限',
  denied_request_dispatched: '被拒绝的请求仍被派发',
  export_job_started: '后台 Worker 开始导出',
  archive_generated: '完整项目交付包已经生成',
  export_job_completed: '后台导出任务已经完成',
}

const traceKindLabels: Record<string, string> = {
  ENTRY: '请求进入目标应用',
  IDENTITY: '目标应用识别实际账号',
  AUTHORIZATION: '应用作出权限判断',
  PERSISTENT_EFFECT: '业务状态发生变化',
  MESSAGE: '任务进入消息链路',
  DELEGATION: '后台任务继续处理',
  FINAL_EFFECT: '最终业务结果形成',
  RECOVERY: '测试现场得到恢复',
}

export function traceEventLabel(event: { kind: string; semantic_key?: string }) {
  return traceSemanticLabels[String(event.semantic_key ?? '')] ?? traceKindLabels[event.kind] ?? '记录到一个业务执行节点'
}
