/* =============================================================================
 * 前端 HTTP 边界
 *
 * 定位
 *   浏览器 fetch 与后端统一 schema_version envelope 之间的共享适配器
 *
 * 职责
 *   注入 JSON header｜解包成功响应｜把脱敏错误映射为 ApiError
 *
 * 调用链
 *   feature API clients → request → FastAPI control plane
 * ============================================================================= */

export type ApiEnvelope<T> = { schema_version: '1'; data: T }

export class ApiError extends Error {
  code: string
  traceId?: string
  constructor(code: string, message: string, traceId?: string) {
    super(message)
    this.code = code
    this.traceId = traceId
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(body.error?.code ?? 'API_ERROR', body.error?.message ?? '请求失败', body.trace_id)
  }
  return (body as ApiEnvelope<T>).data
}
