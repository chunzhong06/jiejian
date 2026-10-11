// 原Agent协作的共同入口：只读取有限上下文并复制请求，不启动模型或代替业务批准。
import { Alert, Button, Modal } from 'antd'
import { CheckOutlined, CopyOutlined, RobotOutlined } from '@ant-design/icons'
import { useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { mcpAccessApi, type MCPAccessLevel, type MCPAccessView } from '../../api/system/mcp'
import { useLiveRead } from '../runtime/useLiveRead'
import { WorkPageVisible } from '../runtime/visibility'
import { agentAccessChanged, canHandOff } from '../runtime/agentConnectionState'
import './agent-assist.css'
import { AgentConnectionDialog } from './AgentConnectionDialog'

export type AgentAssistContext = {
  projectId: string
  revisionKey: string
  requestText: string
}
type Snapshot = { context: AgentAssistContext; access: MCPAccessView; configured: boolean }
const levels = { READ: 0, PREPARE: 1, EXECUTE: 2 }

export function AgentAssistEntry({ projectId, contextKey, title, description, returnTo, loadContext, onNavigate, onRefresh, heading, actions, requiredLevel = 'PREPARE', primary = false, aside = false, dialog = false, initialOpen = false, buttonLabel = 'Agent 协助', onCopied }: {
  projectId: string; contextKey: string; title: string; description: string; returnTo: string
  loadContext: () => Promise<AgentAssistContext>
  onNavigate: (path: string) => void
  onRefresh?: () => Promise<unknown>
  heading?: ReactNode
  actions?: ReactNode
  requiredLevel?: MCPAccessLevel
  primary?: boolean
  aside?: boolean
  dialog?: boolean
  initialOpen?: boolean
  buttonLabel?: string
  onCopied?: () => void
}) {
  const visible = useContext(WorkPageVisible)
  const [open, setOpen] = useState(initialOpen)
  const [connecting, setConnecting] = useState(false)
  const [snapshot, setSnapshot] = useState<Snapshot>()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()
  const [message, setMessage] = useState<string>()
  const [copied, setCopied] = useState(false)
  const scope = `${projectId}:${contextKey}`
  const liveScope = useRef<string | undefined>(undefined)
  liveScope.current = visible && open ? scope : undefined
  const inFlight = useRef<{ scope: string; promise: Promise<Snapshot | undefined> } | undefined>(undefined)
  useEffect(() => { setOpen(initialOpen); setConnecting(false); setSnapshot(undefined); setError(undefined); setMessage(undefined); setBusy(false) }, [scope, initialOpen])
  useEffect(() => () => { liveScope.current = undefined }, [])
  useEffect(() => { setCopied(false) }, [scope])
  useEffect(() => {
    if (!copied) return
    const timer = window.setTimeout(() => setCopied(false), 2000)
    return () => window.clearTimeout(timer)
  }, [copied])

  const read = (): Promise<Snapshot | undefined> => {
    if (inFlight.current?.scope === scope) return inFlight.current.promise
    const pending = Promise.all([mcpAccessApi.status().then(async access => ({ access, configured: await canHandOff(access) })), loadContext()]).then(([{access, configured}, context]) => {
      if (liveScope.current !== scope) return undefined
      if (context.projectId !== projectId) throw new Error('context project mismatch')
      const value = { access, context, configured }
      setSnapshot(value); setError(undefined)
      return value
    }).catch(() => {
      if (liveScope.current === scope) { setSnapshot(undefined); setError('暂时无法核对协助内容，请重新读取。') }
      return undefined
    }).finally(() => { if (inFlight.current?.promise === pending) inFlight.current = undefined })
    inFlight.current = { scope, promise: pending }
    return pending
  }
  useLiveRead(visible && open ? scope : undefined, async () => { await read() }, 5000)
  useEffect(() => {
    if (!visible || !open) return
    const refreshAccess = () => { void read() }
    window.addEventListener(agentAccessChanged, refreshAccess)
    return () => window.removeEventListener(agentAccessChanged, refreshAccess)
  }, [visible, open, scope])
  const permissionProblem = (value: Snapshot) => {
    if (value.access.connection_state === 'PAUSED' || (value.access.paired && !value.access.accepting_connections)) return '开发工具连接已暂停，请先恢复连接。'
    if (!value.configured) return '尚未确认可用的客户端配置，请先查看连接状态。'
    const grant = value.access.project_grants.find(item => item.project_id === projectId)?.level ?? 'READ'
    if (levels[grant] < levels[requiredLevel]) return `当前应用授权不足。请在开发工具中允许“${requiredLevel === 'EXECUTE' ? '执行已确认任务' : '协助整理'}”。`
    return undefined
  }
  const copy = async () => {
    if (busy || !snapshot) return
    setBusy(true); setMessage(undefined); setCopied(false)
    const previous = snapshot.context.revisionKey
    const latest = await read()
    try {
      if (!latest || liveScope.current !== scope) return
      const problem = permissionProblem(latest)
      if (problem) return // 新快照已显示具体阻塞原因，避免再叠一份相同提示。
      // 复制前重读；上下文变化时先让用户看到新请求，不能把旧材料交给另一个任务。
      if (latest.context.revisionKey !== previous) { setMessage('当前内容已经变化，请核对更新后的请求，再复制。'); return }
      await navigator.clipboard.writeText(latest.context.requestText)
      if (liveScope.current === scope) { setCopied(true); onCopied?.(); setMessage('协助请求已复制。请粘贴到原来的 Agent 对话中。') }
    } catch { if (liveScope.current === scope) setError('复制失败，可以展开请求后手工复制。') }
    finally { if (liveScope.current === scope) setBusy(false) }
  }
  const refresh = async () => {
    if (busy || !onRefresh) return
    setBusy(true); setMessage(undefined)
    try { await onRefresh(); await read(); if (liveScope.current === scope) setMessage('已读取当前内容。') }
    catch { if (liveScope.current === scope) setError('读取结果失败，已有内容保留，请稍后重试。') }
    finally { if (liveScope.current === scope) setBusy(false) }
  }
  const problem = snapshot ? permissionProblem(snapshot) : undefined
  // 初次交接直接展示请求与复制入口，避免让用户先展开一个已经展开的协作区。
  const toggle = initialOpen && open ? null : <div className="agent-assist-toggle">{primary && actions}<Button type={primary ? 'primary' : 'default'} icon={<RobotOutlined aria-hidden />} aria-expanded={open} onClick={() => { setOpen(value => !value); setBusy(false) }}>{buttonLabel}</Button>{!primary && actions}</div>
  const panel = open && <div className="agent-assist-panel">{!aside && <><h3>{title}</h3><p>{description}</p></>}
      {!snapshot && !error && <p role="status">正在核对当前内容与连接…</p>}
      {error && <Alert type="warning" showIcon message={error} action={<Button onClick={() => void read()}>重新读取</Button>}/>}
      {problem && <Alert type="info" showIcon message={problem} action={<Button onClick={() => !snapshot?.configured && snapshot?.access.connection_state !== 'PAUSED' ? setConnecting(true) : onNavigate(`/tools?return_to=${encodeURIComponent(returnTo)}&source_project_id=${encodeURIComponent(projectId)}`)}>{snapshot?.access.connection_state === 'PAUSED' ? '恢复连接' : !snapshot?.configured ? '连接 Agent' : '调整允许范围'}</Button>}/>}
      {snapshot?.configured && snapshot.access.connection_state !== 'CONNECTED' && !problem && <p role="status">连接配置已核验，可继续交接任务。尚未收到本次服务的客户端请求。</p>}
      {snapshot && <details><summary>查看协助请求</summary><pre>{snapshot.context.requestText}</pre></details>}
      {message && <p className="agent-assist-message" role="status">{message}</p>}
      <div className="agent-assist-actions">{initialOpen && primary && actions}<Button type={initialOpen && primary ? 'primary' : 'default'} icon={copied?<CheckOutlined aria-hidden/>:<CopyOutlined aria-hidden/>} disabled={!snapshot || Boolean(problem)} loading={busy} onClick={() => void copy()}>复制协助请求</Button>{initialOpen && !primary && actions}{onRefresh && <Button disabled={!snapshot} loading={busy} onClick={() => void refresh()}>读取整理结果</Button>}</div>
    </div>
  return <section className={`agent-assist-entry${heading ? ' agent-assist-entry-with-heading' : ''}${aside ? ' agent-task-banner agent-task-surface' : ''}`} aria-label="Agent 协助">
    <AgentConnectionDialog open={connecting} onClose={()=>{setConnecting(false);void read()}} onConnected={()=>void read()}/>
    {aside ? <><div className="agent-task-main">{heading}</div><aside className="agent-task-assistance"><h3>{title}</h3><p className="editorial-muted">{description}</p>{toggle}{!dialog&&panel}</aside></> : <><div className="agent-assist-heading">{heading && <div className="agent-assist-heading-content">{heading}</div>}{toggle}</div>{!dialog&&panel}</>}
    {dialog&&<Modal className="agent-assist-dialog" open={open} onCancel={()=>setOpen(false)} title="Agent 协助" footer={null} width={800}>{panel}</Modal>}
  </section>
}
