// AI 工具连接面板：管理 MCP 长期配对、本次连接状态和逐应用临时权限。

import { useEffect, useMemo, useRef, useState } from 'react'
import { Alert, Button, Card, Input, List, Modal, Select, Space, Tabs, Tag, Typography } from 'antd'
import { mcpAccessApi, type MCPAccessCredentialView, type MCPAccessLevel, type MCPAccessView } from '../../api/mcp'
import { ApiError } from '../../api/http'

type ProjectOption = { project_id: string; name?: string }

function projectLabel(project: ProjectOption): string {
  return project.name?.trim() || project.project_id
}

const levelLabels: Record<MCPAccessLevel, string> = {
  READ: '只读',
  PREPARE: '允许准备',
  EXECUTE: '允许执行',
}

const dshConfig = `- id: mcp-jiejian
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: jiejian
    transport: streamable-http
    url: http://127.0.0.1:8765/mcp
    headers:
      Authorization: !!js '\`Bearer \${process.env.JIEJIAN_MCP_TOKEN}\`'`

function formatActivity(timestamp: number | null): string {
  if (timestamp === null) return '未记录'
  return new Date(timestamp / 1_000).toLocaleString('zh-CN')
}

function errorValue(error: unknown): ApiError {
  return error as ApiError
}

export function MCPAccessCard({
  open, projects, onError,
}: {
  open: boolean
  projects: ProjectOption[]
  onError: (error: ApiError) => void
}) {
  const [view, setView] = useState<MCPAccessView | null>(null)
  const [accessToken, setAccessToken] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [grantProject, setGrantProject] = useState<ProjectOption | null>(null)
  const [grantLevel, setGrantLevel] = useState<MCPAccessLevel>('PREPARE')
  const [confirmAction, setConfirmAction] = useState<'rotate' | 'forget' | null>(null)
  const openRef = useRef(open)
  const requestEpochRef = useRef(0)
  openRef.current = open
  const grants = useMemo(
    () => new Map(view?.project_grants.map((item) => [item.project_id, item.level]) ?? []),
    [view?.project_grants],
  )

  useEffect(() => {
    // 每次关闭或重开都切换请求代际，避免旧请求污染新一轮抽屉状态。
    const requestEpoch = ++requestEpochRef.current
    if (!open) {
      setView(null)
      setAccessToken(null)
      setBusy(false)
      setGrantProject(null)
      setConfirmAction(null)
      return
    }
    let active = true
    void mcpAccessApi.status().then((value) => {
      if (active && requestEpochRef.current === requestEpoch) setView(value)
    }).catch((error) => {
      if (active && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    })
    return () => { active = false }
  }, [open, onError])

  const updateView = async (operation: () => Promise<MCPAccessView>, clearToken = false) => {
    const requestEpoch = requestEpochRef.current
    setBusy(true)
    try {
      const next = await operation()
      if (!openRef.current || requestEpochRef.current !== requestEpoch) return
      setView(next)
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
      setView(next)
      setAccessToken(next.access_token)
    } catch (error) {
      if (openRef.current && requestEpochRef.current === requestEpoch) onError(errorValue(error))
    } finally {
      if (openRef.current && requestEpochRef.current === requestEpoch) setBusy(false)
    }
  }

  const copy = async (value: string) => {
    const requestEpoch = requestEpochRef.current
    try { await navigator.clipboard.writeText(value) }
    catch {
      if (openRef.current && requestEpochRef.current === requestEpoch) {
        onError(new ApiError('MCP_COPY_FAILED', '复制失败，请手工选择并复制'))
      }
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
      setView(next)
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

  const statusDescription = view?.client_connected
    ? view.client_name || view.client_version
      ? <Space direction="vertical"><Typography.Text>{view.client_name ? `客户端：${view.client_name}` : '客户端名称未提供'}{view.client_version ? ` · 版本：${view.client_version}` : ''}</Typography.Text><Typography.Text>最近活动：{formatActivity(view.last_seen_at_us)}</Typography.Text></Space>
      : <Space direction="vertical"><Typography.Text>已认证客户端已连接</Typography.Text><Typography.Text>最近活动：{formatActivity(view.last_seen_at_us)}</Typography.Text></Space>
    : null

  const guideItems = [
    {
      key: 'codex', label: 'Codex', children: <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text>server name：jiejian</Typography.Text>
        <Typography.Text>endpoint：http://127.0.0.1:8765/mcp</Typography.Text>
        <Typography.Text>token env：JIEJIAN_MCP_TOKEN</Typography.Text>
        <Typography.Text code style={{ whiteSpace: 'pre-wrap' }}>{`[Environment]::SetEnvironmentVariable(
  "JIEJIAN_MCP_TOKEN",
  "<当前界鉴配对令牌>",
  "User"
)

codex mcp add jiejian \`
  --url "http://127.0.0.1:8765/mcp" \`
  --bearer-token-env-var JIEJIAN_MCP_TOKEN`}</Typography.Text>
        <Typography.Paragraph type="secondary">首次设置用户级环境变量后，需要让新的 Codex 进程/会话重新读取环境；以后重启界鉴不需要重复 mcp add。界鉴不会修改 Codex 配置。</Typography.Paragraph>
      </Space>,
    },
    {
      key: 'dsh', label: 'DSH', children: <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Paragraph>固定使用官方 @deepseek-ai/dsh-mcp-client，连接方式为 Streamable HTTP。</Typography.Paragraph>
        <Typography.Text code style={{ whiteSpace: 'pre-wrap' }}>{dshConfig}</Typography.Text>
      </Space>,
    },
    {
      key: 'other', label: '其他 MCP', children: <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text>Streamable HTTP endpoint：http://127.0.0.1:8765/mcp</Typography.Text>
        <Typography.Text>认证：Bearer 认证，使用当前配对凭据。</Typography.Text>
        <Typography.Text>当前配对有效性：{view?.paired ? '已配对' : '未配对'}</Typography.Text>
        <Typography.Text>默认权限：READ（只读）</Typography.Text>
        <Typography.Paragraph type="secondary">PREPARE/EXECUTE 必须回界鉴当前会话授权。</Typography.Paragraph>
      </Space>,
    },
  ]

  return <Card size="small" title="AI 工具连接（MCP）">
    <Space direction="vertical" style={{ width: '100%' }}>
      {!view?.paired ? <>
        <Alert type="info" showIcon message="尚未配对。首次配对会把长期连接凭据安全保存到 Windows Credential Manager；默认只读。" />
        <Button loading={busy || view === null} onClick={() => void updateCredential(mcpAccessApi.pair)}>首次配对 AI 工具</Button>
      </> : <>
        {view.accepting_connections
          ? view.client_connected
            ? <Alert type="success" showIcon message="已连接" description={statusDescription} />
            : <Alert type="info" showIcon message="已配对，正在等待客户端完成 initialize。默认权限为只读。" />
          : <Alert type="warning" showIcon message="本次连接已暂停；长期配对仍保留，下次启动界鉴会自动恢复只读连接。当前 serve 不提供恢复按钮。" />}
        <Typography.Paragraph type="secondary">首次配对一次后，以后启动界鉴会自动恢复只读连接；PREPARE/EXECUTE 每次启动都要重新授权。轮换后只需更新客户端读取的 JIEJIAN_MCP_TOKEN；“忘记此连接”会彻底删除长期配对。</Typography.Paragraph>
        <Typography.Text strong>连接 URL</Typography.Text>
        <Space.Compact block><Input readOnly value={view.endpoint} aria-label="MCP 连接 URL" /><Button onClick={() => void copy(view.endpoint)}>复制 URL</Button></Space.Compact>
        {accessToken && <>
          <Typography.Text strong>连接凭据</Typography.Text>
          <Space.Compact block><Input.Password readOnly visibilityToggle={false} value={accessToken} aria-label="MCP 连接凭据" /><Button onClick={() => void copy(accessToken)}>复制连接凭据</Button></Space.Compact>
        </>}
        <Space wrap>
          {!accessToken && <Button loading={busy} onClick={() => void updateCredential(mcpAccessApi.reveal)}>显示连接凭据</Button>}
          <Button loading={busy} onClick={() => void updateView(mcpAccessApi.pause, true)}>暂停本次连接</Button>
          <Button loading={busy} onClick={() => setConfirmAction('rotate')}>重新生成连接凭据</Button>
          <Button danger loading={busy} onClick={() => setConfirmAction('forget')}>忘记此连接</Button>
        </Space>
        <Tabs items={guideItems} />
        <List
          size="small"
          header="逐应用临时权限"
          dataSource={projects}
          locale={{ emptyText: '尚未接入应用；当前只能使用不依赖应用的只读工具。' }}
          renderItem={(project) => {
            const level = grants.get(project.project_id) ?? 'READ'
            return <List.Item actions={view.accepting_connections ? [<Button size="small" onClick={() => openGrant(project)}>调整权限</Button>] : undefined}>
              <List.Item.Meta title={projectLabel(project)} description={project.project_id} />
              <Tag color={level === 'EXECUTE' ? 'red' : level === 'PREPARE' ? 'gold' : undefined}>{levelLabels[level]}</Tag>
            </List.Item>
          }}
        />
      </>}
    </Space>
    <Modal
      open={confirmAction !== null}
      title={confirmAction === 'rotate' ? '确认重新生成连接凭据？' : '确认忘记此连接？'}
      okText="确认"
      cancelText="取消"
      confirmLoading={busy}
      onCancel={() => setConfirmAction(null)}
      onOk={() => void runConfirmedAction()}
    >
      {confirmAction === 'rotate' ? '现有连接凭据会立即失效。' : '长期配对会被删除，之后必须重新首次配对。'}
    </Modal>
    <Modal
      open={grantProject !== null}
      title="调整 AI 工具权限"
      okText="确认临时权限"
      cancelText="取消"
      confirmLoading={busy}
      onCancel={() => setGrantProject(null)}
      onOk={() => void saveGrant()}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text>应用：{grantProject ? projectLabel(grantProject) : ''}</Typography.Text>
        <Typography.Text type="secondary">权限按层级包含下级能力；本次确认不会永久保存，也不会逐工具重复弹窗。</Typography.Text>
        <Select
          aria-label="AI 工具权限等级"
          value={grantLevel}
          onChange={setGrantLevel}
          style={{ width: '100%' }}
          options={[
            { value: 'READ', label: '只读：查询状态和结果' },
            { value: 'PREPARE', label: '允许准备：修改已有候选和检查准备' },
            { value: 'EXECUTE', label: '允许执行：启动或停止受控任务' },
          ]}
        />
      </Space>
    </Modal>
  </Card>
}


export default MCPAccessCard
