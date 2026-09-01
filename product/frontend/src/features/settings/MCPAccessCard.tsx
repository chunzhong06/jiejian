// AI 工具连接面板：用服务端可观测状态引导五类 MCP 客户端完成连接，并管理逐应用的本次允许范围。

import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, List, Modal, Radio, Segmented, Space, Tag, Typography } from 'antd'
import {
  mcpAccessApi,
  type MCPAccessCredentialView,
  type MCPAccessLevel,
  type MCPAccessView,
  type MCPConnectionState,
} from '../../api/mcp'
import { ApiError } from '../../api/http'

type ProjectOption = { project_id: string; name?: string }
type MCPClientKey = 'codex' | 'trae' | 'qoder' | 'codebuddy' | 'dsh'

type ClientGuide = {
  label: string
  description: string
  openLocation: string
  configInstruction: string
  credentialInstruction: string
  restartInstruction: string
  config: string
  secretMode: 'environment' | 'header'
}

const endpoint = 'http://127.0.0.1:8765/mcp'

const clientGuides: Record<MCPClientKey, ClientGuide> = {
  codex: {
    label: 'Codex',
    description: '适用于 Codex 桌面端、IDE 和命令行。三者读取同一份本机连接设置。',
    openLocation: '按 Win + R，输入 %USERPROFILE%\\.codex 并回车；用记事本打开 config.toml。',
    configInstruction: '把第 3 步复制的内容粘贴到文件末尾并保存。若文件不存在，请用记事本新建，并确认文件名是 config.toml。',
    credentialInstruction: '打开“开始”菜单，搜索 Windows PowerShell；粘贴第 4 步命令并按回车。没有出现红色错误且命令提示符重新出现，即表示保存完成。',
    config: `[mcp_servers.jiejian]\nurl = "${endpoint}"\nbearer_token_env_var = "JIEJIAN_MCP_TOKEN"`,
    secretMode: 'environment',
    restartInstruction: '完全退出 Codex，包括右下角托盘中的 Codex，再重新打开。',
  },
  trae: {
    label: 'TRAE',
    description: '在 TRAE 的 MCP 设置中添加界鉴，不需要理解连接协议。',
    openLocation: '打开 TRAE，进入“设置 → MCP → 手动添加”，找到配置编辑区。',
    configInstruction: '把第 3 步复制的完整配置粘贴到编辑区并保存。',
    credentialInstruction: '在刚才的配置中找到 Authorization，把整段“Bearer <在第4步复制的连接凭据>”替换为第 4 步复制的内容，然后再次保存。',
    config: `{
  "mcpServers": {
    "jiejian": {
      "url": "${endpoint}",
      "headers": {
        "Authorization": "Bearer <在界鉴中复制的连接凭据>"
      }
    }
  }
}`,
    secretMode: 'header',
    restartInstruction: '在 TRAE 中重新连接 jiejian；如果没有重新连接按钮，请完全退出 TRAE 后再打开。',
  },
  qoder: {
    label: 'Qoder',
    description: '在 Qoder 的 MCP 设置中添加界鉴，按页面提供的内容粘贴即可。',
    openLocation: '打开 Qoder，进入“设置 → MCP → 添加服务器”，找到配置编辑区。',
    configInstruction: '把第 3 步复制的完整配置粘贴到编辑区并保存。',
    credentialInstruction: '在刚才的配置中找到 Authorization，把整段“Bearer <在第4步复制的连接凭据>”替换为第 4 步复制的内容，然后再次保存。',
    config: `{
  "mcpServers": {
    "jiejian": {
      "type": "streamable-http",
      "url": "${endpoint}",
      "headers": {
        "Authorization": "Bearer <在界鉴中复制的连接凭据>"
      }
    }
  }
}`,
    secretMode: 'header',
    restartInstruction: '在 Qoder 中重新连接 jiejian；如果没有重新连接按钮，请完全退出 Qoder 后再打开。',
  },
  codebuddy: {
    label: 'CodeBuddy',
    description: '在 CodeBuddy 的 MCP 设置中添加界鉴，连接凭据单独保存在 Windows。',
    openLocation: '打开 CodeBuddy 设置，搜索 MCP，进入 MCP 配置编辑区。',
    configInstruction: '把第 3 步复制的完整配置粘贴到编辑区并保存。',
    credentialInstruction: '打开“开始”菜单，搜索 Windows PowerShell；粘贴第 4 步命令并按回车。没有出现红色错误且命令提示符重新出现，即表示保存完成。',
    config: `{
  "mcpServers": {
    "jiejian": {
      "type": "http",
      "url": "${endpoint}",
      "headers": {
        "Authorization": "Bearer \${JIEJIAN_MCP_TOKEN}"
      }
    }
  }
}`,
    secretMode: 'environment',
    restartInstruction: '完全退出 CodeBuddy 后重新打开。',
  },
  dsh: {
    label: 'DSH',
    description: '把界鉴添加到 DSH 的 MCP 客户端配置中，连接凭据单独保存在 Windows。',
    openLocation: '打开 DSH 的 MCP 配置页或当前使用的 MCP 配置文件。',
    configInstruction: '把第 3 步复制的内容作为一个新的 MCP 服务粘贴并保存。',
    credentialInstruction: '打开“开始”菜单，搜索 Windows PowerShell；粘贴第 4 步命令并按回车。没有出现红色错误且命令提示符重新出现，即表示保存完成。',
    config: `- id: mcp-jiejian
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: jiejian
    transport: streamable-http
    url: ${endpoint}
    headers:
      Authorization: !!js '\`Bearer \${process.env.JIEJIAN_MCP_TOKEN}\`'`,
    secretMode: 'environment',
    restartInstruction: '重新启动 DSH，或在 DSH 中重新连接 jiejian。',
  },
}

const clientOptions = (Object.entries(clientGuides) as [MCPClientKey, ClientGuide][]).map(([value, guide]) => ({
  value,
  label: guide.label,
}))

const levelLabels: Record<MCPAccessLevel, string> = {
  READ: '只查看',
  PREPARE: '协助整理',
  EXECUTE: '执行已确认任务',
}

const levelDescriptions: Record<MCPAccessLevel, string> = {
  READ: '查看当前应用、已确认的权限规则和已发布结果；不会登记变化或启动检查。',
  PREPARE: '完成一个用户任务后登记整批代码变化，整理影响并准备检查；不会自行启动检查。',
  EXECUTE: '还可以启动你已在界鉴中准备好的检查或停止受控任务；不能扩大范围或改变权限规则。',
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
  return `请使用已经配置好的 jiejian MCP 服务连接界鉴。连接成功后先读取服务说明并调用 jiejian_product_status，向我说明：当前应用是什么、当前判断是什么、下一项需要我处理什么。随后只在界鉴返回的项目范围和本次允许范围内工作。界鉴中的已确认权限基线和历史会跨任务保留，不要为新任务重新建立权限规则。处理任务期间不必因每次保存或单个文件修改反复调用界鉴；当一个完整的用户任务已经完成，且界鉴允许“协助整理”或“执行已确认任务”时，再调用一次 jiejian_change_submit 登记整批变化，并按返回状态决定是否需要回到界鉴。需要人工确认或更高范围时立即停止并提示我回到界鉴。不要在对话中索取、粘贴或回显 JIEJIAN_MCP_TOKEN。当前客户端：${client}。`
}

function detectedClient(clientName: string | null): MCPClientKey | null {
  const normalized = clientName?.trim().toLowerCase() ?? ''
  if (normalized.includes('codex')) return 'codex'
  if (normalized.includes('trae')) return 'trae'
  if (normalized.includes('qoder') || normalized.includes('lingma')) return 'qoder'
  if (normalized.includes('codebuddy')) return 'codebuddy'
  if (normalized.includes('dsh') || normalized.includes('deepseek')) return 'dsh'
  return null
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
    description: '按下方 5 步操作。界鉴只有收到客户端的真实连接后，才会显示连接成功。',
  }
  if (state === 'CREDENTIAL_READY') return {
    type: 'info' as const,
    eyebrow: '界鉴已准备好',
    title: '下一步：在 AI 工具中添加 jiejian',
    description: '从下方第 3 步继续。添加完成后还需要保存凭据并重新打开客户端。',
  }
  if (state === 'AUTHENTICATED') return {
    type: 'info' as const,
    eyebrow: '凭据校验通过',
    title: '界鉴正在等待客户端发出有效请求',
    description: '连接地址与凭据都正确，但界鉴还没有收到可处理的 MCP 请求。请确认客户端已经启用 jiejian。',
  }
  if (state === 'CONNECTED') return {
    type: 'success' as const,
    eyebrow: '连接成功',
    title: `${view?.client_name?.trim() || 'AI 工具'} 已连接到界鉴`,
    description: '客户端现在只能在界鉴返回的项目和本次允许范围内工作。',
  }
  if (state === 'CREDENTIAL_REJECTED') return {
    type: 'error' as const,
    eyebrow: '凭据需要更新',
    title: '客户端已经找到界鉴，但使用了失效凭据',
    description: '回到下方第 4 步重新复制当前凭据，保存后完全退出客户端并重新打开。',
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
  const guide = clientGuides[selectedClient]
  const grants = useMemo(
    () => new Map(view?.project_grants.map((item) => [item.project_id, item.level]) ?? []),
    [view?.project_grants],
  )

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
        const client = detectedClient(value.client_name)
        if (client) setSelectedClient(client)
        onStatusChange?.(value)
      }
    }).catch((error) => {
      if (active && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    })
    return () => { active = false }
  }, [open, onError, onStatusChange])

  const acceptView = (next: MCPAccessView) => {
    setView(next)
    const client = detectedClient(next.client_name)
    if (client) setSelectedClient(client)
    if (connectionState(next) === 'CONNECTED') setShowSetup(false)
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
          setCheckMessage(`${latest.client_name?.trim() || '客户端'} 已完成连接。`)
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
        : `界鉴还没有收到 ${guide.label} 的连接请求。请依次确认：第 3 步配置已经保存、第 4 步凭据已经保存、${guide.label} 已完全退出并重新打开。`)
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
    await copyValue(value, '第 4 步内容')
  }

  return <div className="mcp-access-shell">
    <Card className={`mcp-connection-card is-${copy.type}`}>
      <div className="mcp-connection-heading">
        <div>
          <Typography.Text className="mcp-section-label">{copy.eyebrow}</Typography.Text>
          <Typography.Title level={2}>{copy.title}</Typography.Title>
          <Typography.Paragraph>{copy.description}</Typography.Paragraph>
        </div>
        <Space wrap>
          {state === 'PAUSED' && <Button type="primary" loading={busy} onClick={() => void updateView(mcpAccessApi.resume)}>恢复连接</Button>}
          {state === 'CONNECTED' && <Button type="primary" onClick={() => void copyValue(connectionTask(view?.client_name?.trim() || guide.label), '协作任务')}>复制协作任务</Button>}
          {view?.paired && <Button onClick={() => setManagementOpen(true)}>管理连接</Button>}
        </Space>
      </div>

      {state === 'CONNECTED' && <div className="mcp-connected-facts">
        <span><small>客户端</small><strong>{view?.client_name?.trim() || '名称未提供'}{view?.client_version ? ` · ${view.client_version}` : ''}</strong></span>
        <span><small>最近活动</small><strong>{formatActivity(view?.last_seen_at_us ?? null)}</strong></span>
        <span><small>默认允许范围</small><strong>只查看；更多操作仅本次有效</strong></span>
        <Button type="link" onClick={() => setShowSetup(!showSetup)}>{showSetup ? '返回权限范围' : '查看客户端配置'}</Button>
      </div>}
    </Card>

    {(state !== 'CONNECTED' || showSetup) ? <Card className="mcp-setup-card">
      <div className="mcp-setup-heading">
        <div>
          <Typography.Text className="mcp-section-label">首次连接指引</Typography.Text>
          <Typography.Title level={3}>跟着 5 步完成连接</Typography.Title>
          <Typography.Paragraph>不需要理解 MCP 或配置格式。每一步只复制页面准备好的内容，并按说明粘贴到指定位置。</Typography.Paragraph>
        </div>
        <Segmented
          className="mcp-client-selector"
          aria-label="选择 MCP 客户端"
          options={clientOptions}
          value={selectedClient}
          onChange={(value) => {
            setSelectedClient(value as MCPClientKey)
            setCheckMessage(null)
          }}
        />
      </div>

      <Typography.Paragraph className="mcp-client-introduction">当前选择：<strong>{guide.label}</strong>。{guide.description}</Typography.Paragraph>

      <div className="mcp-beginner-guide" aria-label={`${guide.label} 连接步骤`}>
        <section className="mcp-guide-step is-done">
          <span className="mcp-guide-number">1</span>
          <div><strong>确认你正在连接 {guide.label}</strong><p>如果选错了，使用上方选项切换；页面只会展示当前工具的操作。</p><small>完成标志：上方高亮显示 {guide.label}。</small></div>
        </section>
        <section className={`mcp-guide-step ${view?.paired ? 'is-done' : 'is-current'}`}>
          <span className="mcp-guide-number">2</span>
          <div><strong>让界鉴准备本机连接</strong><p>点击按钮后，界鉴会创建一份只供本机客户端使用的连接凭据。创建完成仍不代表已经连接。</p><small>完成标志：按钮变为“界鉴已准备好”。</small></div>
          {view?.paired
            ? <Tag color="green">界鉴已准备好</Tag>
            : <Button type="primary" loading={busy || view === null} onClick={() => void updateCredential(mcpAccessApi.pair)}>准备本机连接</Button>}
        </section>
        <section className={`mcp-guide-step ${view?.paired ? 'is-current' : ''}`}>
          <span className="mcp-guide-number">3</span>
          <div><strong>在 {guide.label} 中添加 jiejian</strong><p>{guide.openLocation} {guide.configInstruction}</p><small>完成标志：{guide.label} 中出现名为 jiejian 的服务。</small></div>
          <Button disabled={!view?.paired} onClick={() => void copyValue(guide.config, '第 3 步内容')}>{copied === '第 3 步内容' ? '第 3 步已复制' : '复制第 3 步内容'}</Button>
        </section>
        <section className="mcp-guide-step">
          <span className="mcp-guide-number">4</span>
          <div><strong>保存连接凭据</strong><p>{guide.credentialInstruction}</p><small>{guide.secretMode === 'header' ? '这份配置包含本机凭据，不要上传、提交或发送给他人。' : '凭据只保存在当前 Windows 用户下，不需要粘贴到聊天中。'}</small></div>
          <Button loading={busy} disabled={!view?.paired} onClick={() => void copySecret()}>{copied === '第 4 步内容' ? '第 4 步已复制' : '复制第 4 步内容'}</Button>
        </section>
        <section className={`mcp-guide-step ${state === 'AUTHENTICATED' ? 'is-current' : ''}`}>
          <span className="mcp-guide-number">5</span>
          <div><strong>打开 {guide.label}，再回到这里检查</strong><p>{guide.restartInstruction} 打开后，点击右侧按钮。</p><small>完成标志：界鉴显示连接成功和最近活动时间；客户端提供身份时还会显示名称与版本。</small></div>
          <Button type="primary" loading={checking} disabled={!view?.paired || state === 'PAUSED'} onClick={() => void checkConnection()}>检查连接</Button>
        </section>
      </div>
      {checkMessage && <Alert className="mcp-check-result" type={state === 'CONNECTED' ? 'success' : state === 'CREDENTIAL_REJECTED' ? 'error' : 'info'} showIcon message={checkMessage} />}
    </Card> : <Card className="mcp-permissions-card" title="AI 工具这次可以做什么">
      <Typography.Paragraph type="secondary">应用的权限规则、代码变化和检查历史会长期保存。连接也会保留，但每次打开界鉴后，AI 工具都只可以查看；你可以按应用临时允许更多操作，关闭界鉴后会自动恢复为只查看。</Typography.Paragraph>
      <div className="mcp-routine" aria-label="连接后的日常协作方式">
        <div className="mcp-routine-step"><small>开始一个任务</small><strong>先读取当前基线</strong><span>Codex 了解当前应用、已有判断和下一项工作。</span></div>
        <div className="mcp-routine-step"><small>完成整个任务</small><strong>一次登记整批变化</strong><span>不会在每次保存或修改单个文件后打断你。</span></div>
        <div className="mcp-routine-step"><small>界鉴继续跟进</small><strong>核对影响并安排复验</strong><span>需要人确认时停下；确认后才准备或执行检查。</span></div>
      </div>
      <List
        size="small"
        dataSource={projects}
        locale={{ emptyText: '尚未接入应用；当前只能读取不依赖应用的产品状态。' }}
        renderItem={(project) => {
          const level = grants.get(project.project_id) ?? 'READ'
          return <List.Item actions={view?.accepting_connections ? [<Button key="grant" size="small" onClick={() => openGrant(project)}>调整这次允许范围</Button>] : undefined}>
            <List.Item.Meta title={projectLabel(project)} />
            <div className="mcp-project-access"><Tag className={`mcp-access-tag is-${level.toLowerCase()}`}>{levelLabels[level]}</Tag></div>
          </List.Item>
        }}
      />
    </Card>}

    <Alert className="mcp-oracle-boundary" type="warning" showIcon message="AI 工具可以读取事实、整理整批变化和执行你已确认的任务，但不能确认或更改权限规则，也不能改变界鉴的检查结论。" />

    <Modal open={managementOpen} title="管理连接" footer={null} onCancel={() => setManagementOpen(false)}>
      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
        <Typography.Text type="secondary">这里只处理连接的暂停、更新和删除。需要重新配置客户端时，请关闭窗口并按页面上的第 3～5 步操作。</Typography.Text>
        {state === 'PAUSED'
          ? <Button loading={busy} onClick={() => void updateView(mcpAccessApi.resume)}>恢复接受连接</Button>
          : <Button loading={busy} onClick={() => void updateView(mcpAccessApi.pause, true)}>暂停本次连接</Button>}
        <Button loading={busy} onClick={() => setConfirmAction('rotate')}>重新生成连接凭据</Button>
        <Button danger loading={busy} onClick={() => setConfirmAction('forget')}>删除连接凭据</Button>
      </Space>
    </Modal>

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
