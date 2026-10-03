// 管理证明来源的读取、轮询与未知写回执；只有页面的明确事件调用 write，恢复只查询原操作。
import {useCallback,useEffect,useRef,useState} from 'react'
import {proofSourcesApi as api, type ProofContext, type ProofSource, type AdoptionPreview, type ProofOperationKind, type ProofReceipt} from '../../../api/preparation/proofSources'
import {ApiError} from '../../../api/http'
import {readProofOperation,saveProofOperation,clearProofOperation,type PendingProofOperation} from './proofSourceOperations'

type Options = {
  projectId: string; requestedSource?: string | null
  onChanged: () => Promise<unknown>; onReset: () => void; onAccepted: (receipt: ProofReceipt) => void
}

export function useProofSources({projectId,requestedSource,onChanged,onReset,onAccepted}: Options) {
  const [context,setContext] = useState<ProofContext>()
  const [loading,setLoading] = useState(true), [busy,setBusy] = useState(false), [issue,setIssue] = useState<string>(), [notice,setNotice] = useState<string>()
  const [pending,setPending] = useState<PendingProofOperation>()
  const generation = useRef(0), sending = useRef(false)
  const load = useCallback(async () => {
    const epoch = generation.current
    try {
      const value = await api.context(projectId)
      if (value.project_id !== projectId) throw new Error('scope')
      if (generation.current === epoch) { setContext(value); setLoading(false) }
    } catch { if (generation.current === epoch) { setIssue('准备信息暂时无法读取，请重新读取后继续。'); setLoading(false) } }
  },[projectId])
  useEffect(() => {
    generation.current += 1; setContext(undefined); setLoading(true); setIssue(undefined); setPending(undefined); onReset()
    const value = readProofOperation(projectId)
    if (value) { setPending(value); setIssue('上次操作回执尚未确认，请查询原操作。') }
    void load()
    return () => { generation.current += 1 }
  },[load,requestedSource,projectId,onReset])
  const running = context?.sources.some(item => ['PENDING','RUNNING','RETRY_WAIT'].includes(item.preflight?.state ?? ''))
  useEffect(() => { if (!running || busy) return; const timer = setInterval(() => void load(),1500); return () => clearInterval(timer) },[running,busy,load])
  const clearPending = () => { setPending(undefined); clearProofOperation(projectId) }
  const accept = async (receipt: ProofReceipt, expected: PendingProofOperation) => {
    if (receipt.project_id !== projectId || receipt.operation_id !== expected.operation || receipt.operation_kind !== expected.kind) throw new Error('receipt mismatch')
    clearPending(); onAccepted(receipt)
    setNotice(expected.kind === 'ADOPT_SOURCE' ? '证明来源已采用，可以返回检查材料。' : '操作已保存。')
    await load(); try { await onChanged() } catch { setIssue('操作已保存，检查材料的显示尚未同步。请刷新准备情况。') }
  }
  const write = async (kind: ProofOperationKind, body: object) => {
    if (sending.current || pending) return
    const epoch = generation.current, operation = crypto.randomUUID().replaceAll('-',''), next = {kind,operation}
    sending.current = true; setBusy(true); setIssue(undefined); setPending(next)
    try {
      // 先持久保存操作身份，再发写请求；刷新后只能查询同键回执，不自动重发。
      try { saveProofOperation(projectId,next) } catch { clearPending(); setIssue('浏览器暂时不能保留操作回执，本次尚未提交。请恢复浏览器存储后再试。'); return }
      const receipt = await api.write(projectId,kind,{...body,operation_id:operation})
      if (generation.current === epoch) await accept(receipt,next)
    } catch (error) { if (generation.current === epoch) {
      if (error instanceof ApiError && ['INPUT_INVALID','STATE_PRECONDITION','STORAGE_SECRET','API_VALIDATION_ERROR','RECORD_NOT_FOUND'].includes(error.code)) {
        clearPending(); setIssue(error.message)
      } else setIssue('操作回执尚未确认，请查询原操作。不要重复提交。')
    } } finally { sending.current = false; if (generation.current === epoch) setBusy(false) }
  }
  const recover = async () => {
    if (!pending || sending.current) return
    sending.current = true; setBusy(true); const epoch = generation.current
    try { const receipt = await api.receipt(projectId,pending.kind,pending.operation); if (generation.current === epoch) await accept(receipt,pending) }
    catch { if (generation.current === epoch) setIssue('原操作的回执仍未确认，当前输入不会再次提交。') }
    finally { sending.current = false; if (generation.current === epoch) setBusy(false) }
  }
  const readAdoption = async (source: ProofSource | undefined, onReady: (value: AdoptionPreview) => void) => {
    if (!source?.preflight) return
    const epoch = generation.current; setBusy(true); setIssue(undefined)
    try { const value = await api.adoptionPreview(projectId,source.source_id,source.preflight.preflight_id)
      if (value.project_id !== projectId || value.source_id !== source.source_id || value.revision !== source.revision) throw new Error('scope')
      if (epoch === generation.current) { onReady(value) }
    } catch (error) { if (epoch === generation.current) setIssue(error instanceof Error ? error.message : '采用预览未能读取。') }
    finally { if (epoch === generation.current) setBusy(false) }
  }
  return {context,loading,busy,issue,notice,pending,running,load,write,recover,readAdoption,setIssue,setNotice}
}
