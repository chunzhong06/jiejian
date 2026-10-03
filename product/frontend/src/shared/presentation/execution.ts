// 只格式化既有生命周期和结论名称，不从其他事实推断结论。
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
