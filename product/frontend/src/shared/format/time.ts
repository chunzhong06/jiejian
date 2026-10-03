// 共用时间显示，兼容已有秒、毫秒与微秒时间戳；缺失值保持明确。
export function formatTimestamp(value: unknown) {
  if (value === undefined || value === null || value === '') return '时间未提供'
  const numeric = Number(value)
  const date = Number.isFinite(numeric)
    ? new Date(numeric > 10_000_000_000_000 ? numeric / 1000 : numeric > 10_000_000_000 ? numeric : numeric * 1000)
    : new Date(String(value))
  return Number.isNaN(date.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}
