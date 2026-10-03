// AI 工具连接面板：用服务端可观测状态引导三类 MCP 客户端完成连接，并管理逐应用的本次允许范围。

import { StatusBadge } from '../../shared/ui/StatusBadge'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, List, Modal, Radio, Segmented, Space, Typography } from 'antd'
import {
  mcpAccessApi,
  type MCPAccessCredentialView,
  type MCPAccessLevel,
  type MCPAccessView,
  type MCPConnectionState,
} from '../../api/system/mcp'
import { ApiError } from '../../api/http'
import { clientGuide, clientOptions, type MCPClientKey } from './clientGuides'
import './connections.css'

type ProjectOption = { project_id: string; name?: string }
const levelLabels: Record<MCPAccessLevel, string> = {
  READ: '只查看',
  PREPARE: '协助整理',
  EXECUTE: '执行已确认任务',
}

const levelDescriptions: Record<MCPAccessLevel, string> = {
  READ: '查看当前应用、已确认的权限规则和已发布结果；不会登记变化或启动检查。',
  PREPARE: '保存规则与证明来源候选、登记代码变化；正式规则和来源采用仍由你确认。',
  EXECUTE: '还可在你确认的读取范围内预检查来源、执行完整权限检查或取消任务；不能批准规则、采用来源或扩大授权。',
}

function projectLabel(project: ProjectOption): string {
  return project.name?.trim() || project.project_id
}

function formatActivity(timestamp: number | null): string {
  if (timestamp === null) return '尚未记录'
  return new Date(timestamp / 1_000).toLocaleString('zh-CN')
}

function environmentCommand(accessToken: string): string {
  return `[Environment]::SetEnvironmentVariable(\n  "JIEJIAN_MCP_TOKEN",\n  "${accessToken}",\n  "User"\n)`
}

function connectionTask(client: string): string {
  return `请使用 jiejian MCP。新约定先用 jiejian_rule_context 和 jiejian_rule_candidate_save 保存带具体例子的规则候选，并给我界面确认入口。已有规则读取 jiejian_business_boundary 沿用。准备不足时读取 jiejian_preparation_context，复用已有材料，协助保存证明来源和预检查；读取范围、规则批准与来源采用交给我在界鉴确认。开发需求继续在当前对话讨论。完成一批修改后，具备 PREPARE 授权时先读取 jiejian_change_registration_preview，再调用 jiejian_change_register，将返回的 fingerprint 作为 expected_registration_fingerprint，并携带稳定 operation_id，无需另建开发任务或接单。响应不明确先用 jiejian_receipt_show 按 DELIVER 查询原键，不创建新键试探。权限只能由我批准；检查按完整现行权限要求显式执行。普通功能目标需要另行验证。不要索取或回显连接凭据。当前客户端：${client}。`
}

function legacyConnectionState(view: MCPAccessView | null): MCPConnectionState {
  if (!view?.paired) return 'DISABLED'
  if (!view.accepting_connections) return 'PAUSED'
  if (view.client_connected) return 'CONNECTED'
  return 'CREDENTIAL_READY'
}

function connectionState(view: MCPAccessView | null): MCPConnectionState {
  return view?.connection_state ?? legacyConnectionState(view)
}

function connectionCopy(view: MCPAccessView | null) {
  const state = connectionState(view)
  if (state === 'DISABLED') return {
    type: 'info' as const,
    eyebrow: '尚未开始',
    title: '先选择你的 AI 工具，再准备本机连接',
    description: '先准备本机连接，再配置客户端。界鉴收到有效请求后才会显示验证结果。',
  }
  if (state === 'CREDENTIAL_READY') return {
    type: 'info' as const,
    eyebrow: '界鉴已准备好',
    title: '下一步：在 AI 工具中添加 jiejian',
    description: '继续配置客户端：连接地址和配置可以公开查看，凭据单独复制。',
  }
  if (state === 'AUTHENTICATED') return {
    type: 'info' as const,
    eyebrow: '凭据校验通过',
    title: '界鉴正在等待客户端发出有效请求',
    description: '连接地址与凭据都正确，但界鉴还没有收到可处理的 MCP 请求。请确认客户端已经启用 jiejian。',
  }
  if (state === 'CONNECTED') return {
    type: 'success' as const,
    eyebrow: '连接已验证',
    title: `${view?.client_name?.trim() || '客户端'} 的连接已验证`,
    description: '已收到该客户端的有效请求。最近活动不代表实时在线，也不代表正在修改代码。',
  }
  if (state === 'CREDENTIAL_REJECTED') return {
    type: 'error' as const,
    eyebrow: '凭据需要更新',
    title: '客户端已经找到界鉴，但使用了失效凭据',
    description: '在配置区域重新复制当前凭据，保存后重新连接客户端。',
  }
  return {
    type: 'warning' as const,
    eyebrow: '连接已暂停',
    title: '界鉴暂时不接受 AI 工具连接',
    description: '长期凭据仍然保留；恢复后客户端可以继续使用同一份配置。',
  }
}

function errorValue(error: unknown): ApiError {
  return error as ApiError
}

export function MCPAccessCard({
  open, projects, onError, onStatusChange,
}: {
  open: boolean
  projects: ProjectOption[]
  onError: (error: ApiError) => void
  onStatusChange?: (view: MCPAccessView) => void
}) {
  const [view, setView] = useState<MCPAccessView | null>(null)
  const [selectedClient, setSelectedClient] = useState<MCPClientKey>('codex')
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [checking, setChecking] = useState(false)
  const [checkMessage, setCheckMessage] = useState<string | null>(null)
  const [copied, setCopied] = useState<string | null>(null)
  const [showSetup, setShowSetup] = useState(true)
  const [grantProject, setGrantProject] = useState<ProjectOption | null>(null)
  const [grantLevel, setGrantLevel] = useState<MCPAccessLevel>('PREPARE')
  const [confirmAction, setConfirmAction] = useState<'rotate' | 'forget' | null>(null)
  const [managementOpen, setManagementOpen] = useState(false)
  const openRef = useRef(open)
  const requestEpochRef = useRef(0)
  openRef.current = open

  const state = connectionState(view)
  const copy = connectionCopy(view)
  const guide = clientGuide(selectedClient, view?.endpoint ?? '')
  const grants = useMemo(
    () => new Map(view?.project_grants.map((item) => [item.project_id, item.level]) ?? []),
    [view?.project_grants],
  )

  // 只有服务端确认配对已不存在，才退出其管理面；删除回执未知时仍保留原操作上下文。
  useEffect(() => {
    if (view?.paired === false) { setManagementOpen(false); setConfirmAction(null) }
  }, [view?.paired])

  useEffect(() => {
    // 每次关闭或重开都切换请求代际，避免旧请求污染新一轮页面状态。
    const requestEpoch = ++requestEpochRef.current
    if (!open) {
      setView(null)
      setAccessToken(null)
      setBusy(false)
      setChecking(false)
      setCheckMessage(null)
      setGrantProject(null)
      setConfirmAction(null)
      setManagementOpen(false)
      return
    }
    let active = true
    void mcpAccessApi.status().then((value) => {
      if (active && requestEpochRef.current === requestEpoch) {
        setView(value)
        setShowSetup(connectionState(value) !== 'CONNECTED')
        onStatusChange?.(value)
      }
    }).catch((error) => {
      if (active && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    })
    return () => { active = false }
  }, [open, onError, onStatusChange])

  const acceptView = (next: MCPAccessView) => {
    setView(next)
    onStatusChange?.(next)
  }

  const updateView = async (operation: () => Promise<MCPAccessView>, clearToken = false) => {
    const requestEpoch = requestEpochRef.current
    setBusy(true)
    try {
      const next = await operation()
      if (!openRef.current || requestEpochRef.current !== requestEpoch) return
      acceptView(next)
      if (clearToken) setAccessToken(null)
    } catch (error) {
      if (openRef.current && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    } finally {
      if (openRef.current && requestEpochRef.current === requestEpoch) setBusy(false)
    }
  }

  const updateCredential = async (operation: () => Promise<MCPAccessCredentialView>) => {
    const requestEpoch = requestEpochRef.current
    setBusy(true)
    try {
      const next = await operation()
      if (!openRef.current || requestEpochRef.current !== requestEpoch) return
      acceptView(next)
      setAccessToken(next.access_token)
      setShowSetup(true)
    } catch (error) {
      if (openRef.current && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    } finally {
      if (openRef.current && requestEpochRef.current === requestEpoch) setBusy(false)
    }
  }

  const copyValue = async (value: string, label: string) => {
    const requestEpoch = requestEpochRef.current
    try {
      await navigator.clipboard.writeText(value)
      if (openRef.current && requestEpochRef.current === requestEpoch) {
        setCopied(label)
        window.setTimeout(() => {
          if (openRef.current && requestEpochRef.current === requestEpoch) setCopied(null)
        }, 1800)
      }
    } catch {
      if (openRef.current && requestEpochRef.current === requestEpoch) {
        onError(new ApiError('MCP_COPY_FAILED', '复制失败，请手工选择并复制'))
      }
    }
  }

  const checkConnection = async () => {
    const requestEpoch = requestEpochRef.current
    setChecking(true)
    setCheckMessage(null)
    try {
      let latest = view
      for (let attempt = 0; attempt < 5; attempt += 1) {
        latest = await mcpAccessApi.status()
        if (!openRef.current || requestEpochRef.current !== requestEpoch) return
        acceptView(latest)
        const latestState = connectionState(latest)
        if (latestState === 'CONNECTED') {
          setCheckMessage(`${latest.client_name?.trim() || '客户端'} 的连接已验证。`)
          return
        }
        if (latestState === 'CREDENTIAL_REJECTED') {
          setCheckMessage('客户端已访问界鉴，但使用的连接凭据无效。请更新凭据后重新连接。')
          return
        }
        if (attempt < 4) await new Promise((resolve) => window.setTimeout(resolve, 1200))
      }
      const latestState = connectionState(latest)
      setCheckMessage(latestState === 'AUTHENTICATED'
        ? `凭据已经通过，但界鉴还没有收到 ${guide.label} 的有效 MCP 请求。请确认 jiejian 已启用；如果刚保存配置，再重新打开客户端后检查。`
        : `界鉴还没有收到 ${guide.label} 的连接请求。请依次确认：配置与凭据已经保存、${guide.label} 已完全退出并重新打开。`)
    } catch (error) {
      if (openRef.current && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    } finally {
      if (openRef.current && requestEpochRef.current === requestEpoch) setChecking(false)
    }
  }

  const openGrant = (project: ProjectOption) => {
    setGrantProject(project)
    setGrantLevel(grants.get(project.project_id) ?? 'PREPARE')
  }

  const saveGrant = async () => {
    if (!grantProject) return
    const requestEpoch = requestEpochRef.current
    setBusy(true)
    try {
      const next = await mcpAccessApi.setProjectAccess(grantProject.project_id, grantLevel)
      if (!openRef.current || requestEpochRef.current !== requestEpoch) return
      acceptView(next)
      setGrantProject(null)
    } catch (error) {
      if (openRef.current && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    } finally {
      if (openRef.current && requestEpochRef.current === requestEpoch) setBusy(false)
    }
  }

  const runConfirmedAction = async () => {
    if (confirmAction === 'rotate') await updateCredential(mcpAccessApi.rotate)
    if (confirmAction === 'forget') await updateView(mcpAccessApi.forget, true)
    if (openRef.current) setConfirmAction(null)
  }

  const copySecret = async () => {
    let token = accessToken
    if (!token && view?.paired) {
      const requestEpoch = requestEpochRef.current
      setBusy(true)
      try {
        const next = await mcpAccessApi.reveal()
        if (!openRef.current || requestEpochRef.current !== requestEpoch) return
        acceptView(next)
        token = next.access_token
        setAccessToken(token)
      } catch (error) {
        if (openRef.current && requestEpochRef.current === requestEpoch) onError(errorValue(error))
        return
      } finally {
        if (openRef.current && requestEpochRef.current === requestEpoch) setBusy(false)
      }
    }
    if (!token) return
    const value = guide.secretMode === 'environment' ? environmentCommand(token) : `Bearer ${token}`
    await copyValue(value, '凭据')
  }

  return <div className="mcp-access-shell connection-page">
    <header className="connection-header"><div><p className="editorial-eyebrow">修改与验证 / 连接</p><h2>把开发工具接入工作流</h2><p>读取权限要求，登记每批修改，带着证据继续验证。</p></div>
      {view?.paired && <Button aria-expanded={managementOpen} onClick={() => setManagementOpen(!managementOpen)}>{managementOpen ? '收起连接管理' : '管理连接'}</Button>}
    </header>
    <section className={`connection-status is-${copy.type}`} aria-label="连接事实">
      <div><span className="connection-status-label">{view ? copy.eyebrow : '正在读取状态'}</span><h3>{view ? copy.title : '读取本机连接信息'}</h3><p>{view ? copy.description : '尚未取得服务端状态。'}</p></div>
      {state === 'PAUSED' && <Button type="primary" loading={busy} onClick={() => void updateView(mcpAccessApi.resume)}>恢复连接</Button>}
      {state === 'CONNECTED' && <Button type="primary" onClick={() => void copyValue(connectionTask(view?.client_name?.trim() || 'MCP Agent'), '使用说明')}>{copied === '使用说明' ? '使用说明已复制' : '复制使用说明'}</Button>}
    </section>
    {state === 'CONNECTED' && <div className="connection-facts"><span><small>实际报告的客户端</small><strong>{view?.client_name?.trim() || '名称未提供'}{view?.client_version ? ` · ${view.client_version}` : ''}</strong></span><span><small>最近活动</small><strong>{formatActivity(view?.last_seen_at_us ?? null)}</strong></span><span><small>默认允许范围</small><strong>只查看 · 更多操作仅本次有效</strong></span></div>}
    <nav className="connection-tabs product-view-tabs" aria-label="连接设置内容"><Button type="text" aria-pressed={showSetup} onClick={() => setShowSetup(true)}>客户端配置</Button><Button type="text" aria-pressed={!showSetup} onClick={() => setShowSetup(false)}>应用授权</Button></nav>
    {showSetup ? <section className="connection-setup" aria-label="客户端配置">
      <header className="connection-setup-heading"><div><h3>三步完成连接</h3><p>选择要配置的客户端。这里的选择不会改变实际连接，也不会改写客户端设置。</p></div><Segmented className="mcp-client-selector" aria-label="选择 MCP 客户端" options={clientOptions} value={selectedClient} onChange={value => { setSelectedClient(value as MCPClientKey); setCheckMessage(null) }}/></header>
      <div className="connection-guide-intro"><strong>{guide.label}</strong><span>{guide.description}</span><a href={guide.source} target="_blank" rel="noreferrer">官方配置说明 ↗</a></div>
      {selectedClient !== 'codex' && <p className="connection-validation-note">配置依据已核验；此客户端尚未完成本机实测。连接验证以实际请求为准。</p>}
      <ol className="connection-steps" aria-label={`${guide.label} 连接步骤`}>
        <li><div className="connection-step-title"><span aria-hidden>01</span><h4>准备本机连接</h4><div>{view?.paired ? <StatusBadge kind="preparation">界鉴已准备好</StatusBadge> : <Button type="primary" loading={busy || view === null} onClick={() => void updateCredential(mcpAccessApi.pair)}>准备本机连接</Button>}</div></div><p>界鉴生成本机连接凭据。准备完成后，仍需客户端发出有效请求。</p></li>
        <li><div className="connection-step-title"><span aria-hidden>02</span><h4>在 {guide.label} 中添加 jiejian</h4></div><p>{guide.openLocation} {guide.configInstruction}</p>
          <div className="connection-address"><span>连接地址</span><code>{view?.endpoint ?? '正在读取'}</code><Button disabled={!view?.endpoint} onClick={() => void copyValue(view!.endpoint, '地址')}>{copied === '地址' ? '地址已复制' : '复制地址'}</Button></div>
          <div className="connection-code"><div><span>配置片段 · 不含凭据</span><Button disabled={!view?.paired || !view.endpoint} onClick={() => void copyValue(guide.config, '配置')}>{copied === '配置' ? '配置已复制' : '复制配置'}</Button></div><pre><code>{view?.endpoint ? guide.config : '正在读取本机地址…'}</code></pre></div>
          <div className="connection-secret"><div><strong>凭据单独保存</strong><p>{guide.credentialInstruction}</p><small>只在明确点击时复制；请勿粘贴到聊天或提交到代码仓库。</small></div><Button loading={busy} disabled={!view?.paired} onClick={() => void copySecret()}>{copied === '凭据' ? '凭据已复制' : guide.secretMode === 'environment' ? '复制凭据保存命令' : '复制 Bearer 凭据'}</Button></div>
        </li>
        <li><div className="connection-step-title"><span aria-hidden>03</span><h4>验证连接，再设置应用授权</h4><Button type="primary" loading={checking} disabled={!view?.paired || state === 'PAUSED'} onClick={() => void checkConnection()}>检查连接</Button></div><p>{guide.restartInstruction} 在客户端启用服务，再回到这里检查。</p>
          {checkMessage && <Alert className="mcp-check-result" type={state === 'CONNECTED' ? 'success' : state === 'CREDENTIAL_REJECTED' ? 'error' : 'info'} showIcon message={checkMessage}/>}
        </li>
      </ol>
    </section> : <section className="connection-permissions" aria-label="应用授权"><h3>AI 工具这次可以做什么</h3><p>权限要求和历史长期保留。每次打开界鉴后，客户端默认只查看；更多操作由你逐应用授权。</p>
      <List dataSource={projects} locale={{ emptyText: '尚未接入应用；接入后可设置本次允许范围。' }} renderItem={project => { const level = grants.get(project.project_id) ?? 'READ'; return <List.Item actions={view?.accepting_connections ? [<Button key="grant" onClick={() => openGrant(project)}>调整这次允许范围</Button>] : undefined}><List.Item.Meta title={projectLabel(project)}/><StatusBadge kind="lifecycle" tone="info">{levelLabels[level]}</StatusBadge></List.Item> }}/>
      <div className="connection-routine"><span><b>1. 保留权限约定</b>候选由你确认，已有规则沿用</span><span><b>2. 准备可检验的规则</b>Agent 补缺口，你确认必要范围</span><span><b>3. 修改、检查与继续开发</b>复用材料，保留每批证据</span></div>
    </section>}
    {managementOpen && <section className="connection-management" aria-label="管理连接"><h3>管理本机连接</h3><p>当前连接凭据由所有客户端共用。更新或删除会影响使用此凭据的客户端。</p><Space wrap>{state === 'PAUSED' ? <Button loading={busy} onClick={() => void updateView(mcpAccessApi.resume)}>恢复接受连接</Button> : <Button loading={busy} onClick={() => void updateView(mcpAccessApi.pause, true)}>暂停本次连接</Button>}<Button disabled={busy} onClick={() => setConfirmAction('rotate')}>重新生成连接凭据</Button><Button danger disabled={busy} onClick={() => setConfirmAction('forget')}>删除连接凭据</Button></Space></section>}
    <p className="connection-boundary">AI 工具不能批准或更改权限规则，也不能改变界鉴的检查结论。复制说明不会发送消息，连接不表示 Agent 正在编码。</p>

    <Modal
      open={confirmAction !== null}
      title={confirmAction === 'rotate' ? '确认重新生成连接凭据？' : '确认删除连接凭据？'}
      okText="确认"
      cancelText="取消"
      confirmLoading={busy}
      onCancel={() => setConfirmAction(null)}
      onOk={() => void runConfirmedAction()}
    >
      {confirmAction === 'rotate' ? '现有凭据会立即失效，所有客户端都需要更新。' : '凭据和各应用这次允许的操作会被删除，之后需要重新开始连接。'}
    </Modal>

    <Modal
      open={grantProject !== null}
      title="这次允许 AI 工具做到哪一步？"
      okText="保存这次允许范围"
      cancelText="取消"
      confirmLoading={busy}
      onCancel={() => setGrantProject(null)}
      onOk={() => void saveGrant()}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text>应用：{grantProject ? projectLabel(grantProject) : ''}</Typography.Text>
        <Typography.Text type="secondary">后一项包含前一项能力，只对这个应用和本次打开界鉴期间生效。AI 工具不能自行提高范围。</Typography.Text>
        <Radio.Group className="mcp-access-levels" aria-label="这次允许 AI 工具做到哪一步" value={grantLevel} onChange={(event) => setGrantLevel(event.target.value)}>
          {(['READ', 'PREPARE', 'EXECUTE'] as MCPAccessLevel[]).map((level) => <Card key={level} size="small">
            <Radio value={level}><span className="mcp-access-level-copy"><strong>{levelLabels[level]}</strong><span>{levelDescriptions[level]}</span></span></Radio>
          </Card>)}
        </Radio.Group>
      </Space>
    </Modal>
  </div>
}

export default MCPAccessCard
