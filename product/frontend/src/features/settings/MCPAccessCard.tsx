// AI 工具连接面板：显式启停进程内 MCP 令牌，并通过单次确认管理逐应用临时权限。

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Input, List, Modal, Select, Space, Tag, Typography } from 'antd'
import { mcpAccessApi, type MCPAccessLevel, type MCPAccessView } from '../../api/mcp'
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

export function MCPAccessCard({
  open, projects, onError,
}: {
  open: boolean
  projects: ProjectOption[]
  onError: (error: ApiError) => void
}) {
  const [view, setView] = useState<MCPAccessView | null>(null)
  const [busy, setBusy] = useState(false)
  const [grantProject, setGrantProject] = useState<ProjectOption | null>(null)
  const [grantLevel, setGrantLevel] = useState<MCPAccessLevel>('PREPARE')
  const grants = useMemo(
    () => new Map(view?.project_grants.map((item) => [item.project_id, item.level]) ?? []),
    [view?.project_grants],
  )

  useEffect(() => {
    if (!open) {
      setView(null)
      setGrantProject(null)
      return
    }
    let active = true
    void mcpAccessApi.status().then((value) => {
      if (active) setView(value)
    }).catch((error) => {
      if (active) onError(error as ApiError)
    })
    return () => { active = false }
  }, [open, onError])

  const update = async (operation: () => Promise<MCPAccessView>) => {
    setBusy(true)
    try { setView(await operation()) }
    catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  const copy = async (value: string) => {
    try { await navigator.clipboard.writeText(value) }
    catch { onError(new ApiError('MCP_COPY_FAILED', '复制失败，请手工选择并复制')) }
  }

  const openGrant = (project: ProjectOption) => {
    setGrantProject(project)
    setGrantLevel(grants.get(project.project_id) ?? 'PREPARE')
  }

  const saveGrant = async () => {
    if (!grantProject) return
    setBusy(true)
    try {
      setView(await mcpAccessApi.setProjectAccess(grantProject.project_id, grantLevel))
      setGrantProject(null)
    } catch (error) { onError(error as ApiError) }
    finally { setBusy(false) }
  }

  return <Card size="small" title="AI 工具连接（MCP）">
    <Space direction="vertical" style={{ width: '100%' }}>
      <Typography.Text type="secondary">
        这是供本机 AI 工具调用界鉴控制能力的独立入口，不会把模型 API Key 用作控制凭据。令牌和提升权限会在关闭连接、重新生成令牌或退出界鉴时立即清除。
      </Typography.Text>
      {!view?.enabled ? <>
        <Alert type="info" showIcon message="当前未启用；默认不会接受任何 MCP 请求。" />
        <Button loading={busy || view === null} onClick={() => void update(mcpAccessApi.enable)}>允许本机 AI 工具连接本次界鉴会话</Button>
      </> : <>
        <Alert type="warning" showIcon message="连接已启用。默认权限为只读；准备和执行必须按应用明确确认。" />
        <Typography.Text strong>连接 URL</Typography.Text>
        <Space.Compact block><Input readOnly value={view.endpoint} aria-label="MCP 连接 URL" /><Button onClick={() => void copy(view.endpoint)}>复制 URL</Button></Space.Compact>
        <Typography.Text strong>Bearer 令牌</Typography.Text>
        <Space.Compact block><Input readOnly value={view.access_token ?? ''} aria-label="MCP Bearer 令牌" /><Button onClick={() => void copy(view.access_token ?? '')}>复制 Bearer 令牌</Button></Space.Compact>
        <Space wrap><Button loading={busy} onClick={() => void update(mcpAccessApi.regenerate)}>重新生成令牌</Button><Button danger loading={busy} onClick={() => void update(mcpAccessApi.disable)}>关闭连接</Button></Space>
        <List
          size="small"
          header="逐应用临时权限"
          dataSource={projects}
          locale={{ emptyText: '尚未接入应用；当前只能使用不依赖应用的只读工具。' }}
          renderItem={(project) => {
            const level = grants.get(project.project_id) ?? 'READ'
            return <List.Item actions={[<Button size="small" onClick={() => openGrant(project)}>调整权限</Button>]}>
              <List.Item.Meta title={projectLabel(project)} description={project.project_id} />
              <Tag color={level === 'EXECUTE' ? 'red' : level === 'PREPARE' ? 'gold' : undefined}>{levelLabels[level]}</Tag>
            </List.Item>
          }}
        />
      </>}
    </Space>
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
