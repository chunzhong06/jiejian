// 共享 HTTP 传输：解包响应、映射脱敏错误，并按读取代次合并并发请求。
import {beginWorkflowTiming} from '../lib/workflowTiming'
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
  reason?: string
  requestOutcome: 'NOT_ACCEPTED'|'UNKNOWN'
  fieldErrors: Array<{field:string;reason:'REQUIRED'|'TOO_LONG'|'TOO_SHORT'|'INVALID'}>
  constructor(code: string, message: string, traceId?: string, diagnosis?: ErrorDiagnosis, executionStarted?: boolean, reason?: string, requestOutcome?: unknown, fieldErrors?: unknown) {
    super(message)
    this.code = code
    this.traceId = traceId
    this.diagnosis = diagnosis
    this.executionStarted = typeof executionStarted === 'boolean' ? executionStarted : undefined
    this.reason = typeof reason==='string'&&/^[A-Z][A-Z0-9_]{0,63}$/.test(reason)?reason:undefined
    this.requestOutcome=requestOutcome==='NOT_ACCEPTED'?'NOT_ACCEPTED':'UNKNOWN'
    const fields=new Set(['name','operation_id','expected_plan_fingerprint','expected_version','expected_revision','plan_hash'])
    this.fieldErrors=Array.isArray(fieldErrors)?fieldErrors.slice(0,16).flatMap(item=>
      item&&typeof item==='object'&&fields.has(item.field)&&['REQUIRED','TOO_LONG','TOO_SHORT','INVALID'].includes(item.reason)
        ?[{field:item.field,reason:item.reason}]:[]):[]
  }
}

type PendingRead = {promise:Promise<unknown>;controller:AbortController;consumers:Set<symbol>}
const pendingReads = new Map<string, PendingRead>()
let readGeneration = 0

export function request<T>(path: string, init?: RequestInit): Promise<T> {
  const read = !init?.method || init.method.toUpperCase() === 'GET'
  if (!read) {
    // 写入开始后，新的读取不得合并到写入前仍在途的旧请求。
    readGeneration += 1; pendingReads.clear()
    return send<T>(path, init).finally(() => {
      if (typeof window !== 'undefined' && /runs|preparations|recordings|preparation-batches|controlled-runtime|flow-trials/.test(path))
        window.dispatchEvent(new Event('jiejian:activity-changed'))
    })
  }
  if (init&&Object.keys(init).some(key=>key!=='signal'&&key!=='method')) return send<T>(path, init)
  if (init?.signal?.aborted) return Promise.reject(init.signal.reason??new DOMException('读取已取消','AbortError'))
  const key = `${readGeneration}:${path}`
  let operation = pendingReads.get(key)
  if (!operation) {
    const controller=new AbortController()
    operation={controller,consumers:new Set(),promise:send<T>(path,{...init,signal:controller.signal}).finally(()=>{
      if(pendingReads.get(key)===operation)pendingReads.delete(key)
    })}
    pendingReads.set(key,operation)
  }
  const shared=operation,consumer=Symbol()
  shared.consumers.add(consumer)
  return new Promise<T>((resolve,reject)=>{
    const release=()=>{init?.signal?.removeEventListener('abort',cancel);shared.consumers.delete(consumer)}
    const cancel=()=>{release();if(!shared.consumers.size){shared.controller.abort();if(pendingReads.get(key)===shared)pendingReads.delete(key)};reject(init?.signal?.reason??new DOMException('读取已取消','AbortError'))}
    init?.signal?.addEventListener('abort',cancel,{once:true})
    // 每个订阅者独立取消，只有最后一个离开时才取消底层读取。
    shared.promise.then(value=>{release();resolve(value as T)},error=>{release();reject(error)})
  })
}

async function send<T>(path: string, init?: RequestInit): Promise<T> {
  const read = !init?.method || init.method.toUpperCase() === 'GET'
  const controller = read ? new AbortController() : undefined
  const cancel = () => controller?.abort(init?.signal?.reason)
  if (init?.signal?.aborted) cancel()
  else init?.signal?.addEventListener('abort', cancel, {once:true})
  // 自动超时只施加于读取；写入结果未知时由用例查询原回执，传输层不自动重放副作用。
  const timer = controller ? setTimeout(() => controller.abort(), 30_000) : undefined
  const finishTiming=beginWorkflowTiming(read?'http.read':'http.command')
  let timingOutcome:'COMPLETE'|'FAILED'|'ABORTED'='COMPLETE'
  try {
  const response = await fetch(path, {
    ...init,
    ...(controller ? {signal:controller.signal} : {}),
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  }).catch(error=>{
    // 浏览器网络错误没有服务端回执；保留 UNKNOWN，并用固定文案避免泄露底层地址或错误正文。
    if(error instanceof TypeError)throw new ApiError('CONTROL_CONNECTION_FAILED','与界鉴服务的连接已中断。请检查本机服务；已提交的操作先查询原回执。')
    throw error
  })
  const body = await response.json().catch(() => ({}))
  if (!isApiEnvelope(body)) {
    throw new ApiError(
      'API_VERSION_UNSUPPORTED',
      '界鉴服务返回了不支持的 API 消息版本，请重启界鉴后重试',
    )
  }
  if (!response.ok) {
    // 只读取执行门禁及有界原因码，不向页面透传任意错误 details。
    throw new ApiError(body.error?.code ?? 'API_ERROR', body.error?.message ?? '请求失败', body.trace_id, body.error?.diagnosis, body.error?.details?.execution_started, body.error?.details?.reason, body.error?.details?.request_outcome, body.error?.details?.field_errors)
  }
  // 这里只识别 envelope 版本；具体字段与项目归属仍由对应 API 和页面消费者核对。
  return body.data as T
  } catch (error) {
    timingOutcome=init?.signal?.aborted?'ABORTED':'FAILED'
    if (controller?.signal.aborted && !init?.signal?.aborted) throw new ApiError('READ_TIMEOUT', '读取尚未完成，可以返回或稍后重试；已提交的操作请查询原回执。')
    throw error
  } finally { finishTiming(timingOutcome);if (timer) clearTimeout(timer); init?.signal?.removeEventListener('abort',cancel) }
}

function isApiEnvelope(body: unknown): body is ApiEnvelope<unknown> & { error?: { code?: string; message?: string; diagnosis?: ErrorDiagnosis; details?:{execution_started?:boolean;reason?:string;request_outcome?:unknown;field_errors?:unknown} }; trace_id?: string } {
  return typeof body === 'object' && body !== null && (body as { schema_version?: unknown }).schema_version === '1'
}
