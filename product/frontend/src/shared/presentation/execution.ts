// 只格式化既有生命周期，不从其他事实推断执行状态。
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

export function lifecycleLabel(value: unknown) {
  return lifecycleLabels[String(value ?? '')] ?? '未知'
}
