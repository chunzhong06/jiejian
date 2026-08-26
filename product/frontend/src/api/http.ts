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

export type ErrorDiagnosis = {
  route: string
  headline: string
  short_message: string
  cleanup_warnings: string[]
  phase?: string
  intervention?: string
  cause?: string
  recovery_action?: string
  [key: string]: unknown
}

export class ApiError extends Error {
  code: string
  traceId?: string
  diagnosis?: ErrorDiagnosis
  constructor(code: string, message: string, traceId?: string, diagnosis?: ErrorDiagnosis) {
    super(message)
    this.code = code
    this.traceId = traceId
    this.diagnosis = diagnosis
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!isApiEnvelope(body)) {
    throw new ApiError(
      'API_VERSION_UNSUPPORTED',
      '界鉴服务返回了不支持的 API 消息版本，请重启界鉴后重试',
    )
  }
  if (!response.ok) {
    throw new ApiError(body.error?.code ?? 'API_ERROR', body.error?.message ?? '请求失败', body.trace_id, body.error?.diagnosis)
  }
  return body.data as T
}

function isApiEnvelope(body: unknown): body is ApiEnvelope<unknown> & { error?: { code?: string; message?: string; diagnosis?: ErrorDiagnosis }; trace_id?: string } {
  return typeof body === 'object' && body !== null && (body as { schema_version?: unknown }).schema_version === '1'
}
