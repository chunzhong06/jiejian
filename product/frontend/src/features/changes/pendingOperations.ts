// 刷新恢复只保留非秘密的操作定位，不保存任务正文、表单草稿或客户端凭据。
type PendingReference = { operation_id: string; kind: string; task_id?: string; context_id?: string; delivery_id?: string; expected_version?: number; expected_registration_fingerprint?: string }
const key = (project: string, scope: string) => `jiejian.pending-operation.${project}.${scope}`
export function readPendingOperation(project: string, scope: string): PendingReference | null {
  try {
    const raw = sessionStorage.getItem(key(project, scope))
    if (!raw || raw.length > 1024) return null
    const value = JSON.parse(raw) as PendingReference
    if (!/^[a-f0-9]{32}$/.test(value.operation_id) || !['CREATE', 'REVISE', 'CLOSE', 'CANCEL', 'DELIVER', 'LOAD_RUNTIME'].includes(value.kind)) return null
    if (['task_id', 'context_id', 'delivery_id'].some(field => field in value && (typeof value[field as keyof PendingReference] !== 'string' || String(value[field as keyof PendingReference]).length > 64))) return null
    if (value.expected_version !== undefined && (!Number.isSafeInteger(value.expected_version) || value.expected_version < 1)) return null
    if (value.expected_registration_fingerprint !== undefined && !/^[a-f0-9]{64}$/.test(value.expected_registration_fingerprint)) return null
    return value
  } catch { return null }
}
export function savePendingOperation(project: string, scope: string, value: PendingReference) {
  // 只写白名单字段；以后增加 DTO 字段也不能顺手把说明或秘密带入浏览器存储。
  try {
    sessionStorage.setItem(key(project, scope), JSON.stringify({ operation_id: value.operation_id, kind: value.kind,
      task_id: value.task_id, context_id: value.context_id, delivery_id: value.delivery_id, expected_version: value.expected_version, expected_registration_fingerprint: value.expected_registration_fingerprint }))
    return true
  } catch { return false }
}
export function clearPendingOperation(project: string, scope: string, operation: string) {
  try { if (readPendingOperation(project, scope)?.operation_id === operation) sessionStorage.removeItem(key(project, scope)) } catch { /* 成功事实已经持久化；清理失败仍可在下次通过原回执恢复。 */ }
}
