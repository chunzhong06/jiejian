// 刷新恢复只保存当前项目的非秘密操作身份；存储键和结构沿用原格式，读取不会重发写入。
import type {ProofOperationKind} from '../../../api/preparation/proofSources'

export type PendingProofOperation = {kind: ProofOperationKind; operation: string}
const storageKey = (project: string) => `jiejian-proof-operation:${project}`
const kinds: readonly string[] = ['SAVE_SOURCE','GRANT_SCOPE','START_PREFLIGHT','CANCEL_PREFLIGHT','ADOPT_SOURCE','REVOKE_SCOPE']

export function readProofOperation(project: string): PendingProofOperation | undefined {
  try {
    const stored = sessionStorage.getItem(storageKey(project))
    if (!stored) return undefined
    const value = JSON.parse(stored) as PendingProofOperation
    if (/^[0-9a-f]{32}$/.test(value.operation) && kinds.includes(value.kind)) {
      return {kind:value.kind,operation:value.operation}
    }
  } catch { /* 存储不可用或记录不完整时不猜测操作身份，当前页仍保留自己的内存状态。 */ }
  return undefined
}

export function saveProofOperation(project: string, value: PendingProofOperation) {
  // 写前保存失败由调用者阻止请求；白名单避免把后来新增的表单字段带入存储。
  sessionStorage.setItem(storageKey(project),JSON.stringify({kind:value.kind,operation:value.operation}))
}

export function clearProofOperation(project: string) {
  try { sessionStorage.removeItem(storageKey(project)) } catch { /* 成功事实已经成立，下次仍可查询同一回执。 */ }
}
