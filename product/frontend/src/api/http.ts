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
  executionStarted?: boolean
  constructor(code: string, message: string, traceId?: string, diagnosis?: ErrorDiagnosis, executionStarted?: boolean) {
    super(message)
    this.code = code
    this.traceId = traceId
    this.diagnosis = diagnosis
    this.executionStarted = typeof executionStarted === 'boolean' ? executionStarted : undefined
  }
}

const pendingReads = new Map<string, Promise<unknown>>()
let readGeneration = 0

export function request<T>(path: string, init?: RequestInit): Promise<T> {
  const read = !init?.method || init.method.toUpperCase() === 'GET'
  if (!read) {
    // 写入开始后，新的读取不得合并到写入前仍在途的旧请求。
    readGeneration += 1; pendingReads.clear()
    return send<T>(path, init)
  }
  if (init?.signal || init?.headers) return send<T>(path, init)
  const key = `${readGeneration}:${path}`
  const existing = pendingReads.get(key)
  if (existing) return existing as Promise<T>
  const operation = send<T>(path, init).finally(() => {
    if (pendingReads.get(key) === operation) pendingReads.delete(key)
  })
  pendingReads.set(key, operation)
  return operation
}

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const read = !init?.method || init.method.toUpperCase() === 'GET'
  const controller = read && !init?.signal ? new AbortController() : undefined
  const timer = controller ? setTimeout(() => controller.abort(), 30_000) : undefined
  try {
  const response = await fetch(path, {
    ...init,
    ...(controller ? {signal:controller.signal} : {}),
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
    // 只读取明确的执行门禁布尔值，不向页面透传任意错误 details。
    throw new ApiError(body.error?.code ?? 'API_ERROR', body.error?.message ?? '请求失败', body.trace_id, body.error?.diagnosis, body.error?.details?.execution_started)
  }
  return body.data as T
  } catch (error) {
    if (controller?.signal.aborted) throw new ApiError('READ_TIMEOUT', '读取尚未完成，可以返回或稍后重试；已提交的操作请查询原回执。')
    throw error
  } finally { if (timer) clearTimeout(timer) }
}

function isApiEnvelope(body: unknown): body is ApiEnvelope<unknown> & { error?: { code?: string; message?: string; diagnosis?: ErrorDiagnosis; details?:{execution_started?:boolean} }; trace_id?: string } {
  return typeof body === 'object' && body !== null && (body as { schema_version?: unknown }).schema_version === '1'
}
