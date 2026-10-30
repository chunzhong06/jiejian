// 共享 HTTP 传输：解包响应、映射脱敏错误，并按读取代次合并并发请求。
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
    return send<T>(path, init).finally(() => {
      if (typeof window !== 'undefined' && /runs|preparations|recordings|preparation-batches|controlled-runtime/.test(path))
        window.dispatchEvent(new Event('jiejian:activity-changed'))
    })
  }
  // 独立取消或自定义头的请求不共享 Promise，避免一个消费者中止或改变另一个消费者的读取。
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
  const controller = read ? new AbortController() : undefined
  const cancel = () => controller?.abort(init?.signal?.reason)
  if (init?.signal?.aborted) cancel()
  else init?.signal?.addEventListener('abort', cancel, {once:true})
  // 自动超时只施加于读取；写入结果未知时由用例查询原回执，传输层不自动重放副作用。
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
  // 这里只识别 envelope 版本；具体字段与项目归属仍由对应 API 和页面消费者核对。
  return body.data as T
  } catch (error) {
    if (controller?.signal.aborted && !init?.signal?.aborted) throw new ApiError('READ_TIMEOUT', '读取尚未完成，可以返回或稍后重试；已提交的操作请查询原回执。')
    throw error
  } finally { if (timer) clearTimeout(timer); init?.signal?.removeEventListener('abort',cancel) }
}

function isApiEnvelope(body: unknown): body is ApiEnvelope<unknown> & { error?: { code?: string; message?: string; diagnosis?: ErrorDiagnosis; details?:{execution_started?:boolean} }; trace_id?: string } {
  return typeof body === 'object' && body !== null && (body as { schema_version?: unknown }).schema_version === '1'
}
