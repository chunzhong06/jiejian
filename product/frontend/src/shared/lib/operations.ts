export const operationId = () => crypto.randomUUID().replaceAll('-', '')

// 仅保存非秘密的恢复输入和操作标识，服务端回执才决定是否完成；T 不会校验读回的 JSON。
export function readPending<T>(key: string): T | undefined {
  try { const value = sessionStorage.getItem(key); return value ? JSON.parse(value) as T : undefined }
  catch { sessionStorage.removeItem(key); return undefined }
}

export function savePending(key: string, value: unknown) {
  if (value === undefined) sessionStorage.removeItem(key)
  else sessionStorage.setItem(key, JSON.stringify(value))
}
