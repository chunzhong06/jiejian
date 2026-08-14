export const lifecycleLabels: Record<string, string> = {
  PENDING: '等待后台处理',
  QUEUED: '等待后台处理',
  RUNNING: '正在检查',
  COMPLETED: '已完成',
  SUCCEEDED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
  SAFETY_STOPPED: '已安全停止',
  RETRY_WAIT: '等待重试',
}

export const verdictLabels: Record<string, string> = {
  PASS: '当前规则覆盖范围内未发现越权',
  BLOCK: '发现可能的权限越界，需要处理',
  INCONCLUSIVE: '证据不足，暂时不能下结论',
}

export function lifecycleLabel(value: unknown) {
  const raw = String(value ?? '')
  return lifecycleLabels[raw] ?? `未知（${raw || '未提供'}）`
}

export function verdictLabel(value: unknown) {
  const raw = String(value ?? '')
  return verdictLabels[raw] ?? `未知（${raw || '未提供'}）`
}
