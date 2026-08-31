// 项目概览聚合当前安全基线和全部待办，不把一次页面位置保存成线性进度。

import { Button, Divider, Modal, Space, Tag, Typography } from 'antd'
import { useState } from 'react'
import type { OfficialExperienceDto } from '../../api/experience'
import type { MCPAccessView } from '../../api/mcp'
import type { ProductStatusDto, ProjectDto, ProjectReadinessDto } from '../../api/projects'
import type { RunDto } from '../../api/runs'
import type { SystemStatus } from '../../api/system'
import { formatTimestamp, integrityLabel, lifecycleLabel, verdictLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'

function endpointLabel(readiness: ProjectReadinessDto) {
  if (readiness.endpoint_status === 'CONFIRMED') return '应用连接已确认'
  if (readiness.endpoint_status === 'UNAVAILABLE') return '应用当前不可达'
  return '应用连接待确认'
}

export function WorkbenchPage({
  selected,
  readiness,
  status,
  runs,
  systemStatus,
  mcpStatus,
  mcpStatusFailed = false,
  experience,
  experienceBusy,
  onStartExperience,
  onStopExperience,
  onEnterPresentation,
  onNavigate,
}: {
  selected: ProjectDto | null
  readiness: ProjectReadinessDto | null
  status: ProductStatusDto | null
  runs: RunDto[]
  systemStatus: SystemStatus
  mcpStatus?: MCPAccessView | null
  mcpStatusFailed?: boolean
  experience: OfficialExperienceDto | null
  experienceBusy: boolean
  onStartExperience: () => Promise<boolean>
  onStopExperience?: () => Promise<void>
  onEnterPresentation?: () => void
  onNavigate: (path: string) => void
}) {
  const [startConfirmOpen, setStartConfirmOpen] = useState(false)
  const latest = runs[0]
  const latestChange = status?.latest_change ?? null
  const systemIssue = systemStatus.api === 'unknown' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
  const sampleAvailable = experience?.available === true
  const activeSampleSelected = experience?.active === true && experience.project_id === selected?.project_id
  const sampleActions = experience?.active
    ? <Space wrap size={8}>
      <Button type="primary" disabled={!activeSampleSelected || experienceBusy} onClick={onEnterPresentation}>进入展示模式</Button>
      <Button disabled={experienceBusy} onClick={() => { void onStopExperience?.() }}>结束官方示例</Button>
    </Space>
    : <Button disabled={!sampleAvailable || experienceBusy} onClick={() => setStartConfirmOpen(true)}>启动官方示例</Button>
  const consent = <Modal
    open={startConfirmOpen}
    title="启动官方示例？"
    okText="同意并启动"
    cancelText="取消"
    confirmLoading={experienceBusy}
    onCancel={() => setStartConfirmOpen(false)}
    onOk={async () => { if (await onStartExperience()) setStartConfirmOpen(false) }}
  >
    <Typography.Paragraph>将启动随界鉴提供的本机协作空间示例，为本次使用创建独立工作区，并访问它的本机回环地址。</Typography.Paragraph>
    <Typography.Paragraph>界鉴会只读分析示例源码，用于建立权限基线并验证后续 Agent 代码变化。</Typography.Paragraph>
    <Typography.Paragraph strong>启动示例不会开始真实检查，也不会预先生成结论。</Typography.Paragraph>
  </Modal>

  if (!selected) return <div className="workbench-page">
    <PageTaskHeader title="项目概览" description="接入应用后，界鉴会持续跟踪权限规则、测试准备、代码变化与可信结果。" status="等待接入应用" />
    <section className="workbench-primary-panel workbench-empty" aria-labelledby="workbench-empty-title">
      <Typography.Title id="workbench-empty-title" level={3}>建立第一份权限安全基线</Typography.Title>
      <Typography.Paragraph type="secondary">先连接本地 Web 应用。应用继续开发时，界鉴会保留已确认规则，并提示新增或失效的部分。</Typography.Paragraph>
      <Button type="primary" onClick={() => onNavigate('/application')}>接入自己的应用</Button>
    </section>
    <Divider plain>或者先体验界鉴</Divider>
    <section className="workbench-sample-entry" aria-labelledby="workbench-sample-entry-title">
      <Typography.Text className="workbench-eyebrow">官方示例</Typography.Text>
      <Typography.Title id="workbench-sample-entry-title" level={3}>协作空间</Typography.Title>
      <Typography.Paragraph>Bob 可以查看日常协作资料，但不能导出完整项目交付包。界鉴会核对页面响应、后台任务与 ZIP 生成结果是否一致。</Typography.Paragraph>
      {!sampleAvailable && <Typography.Paragraph type="secondary">当前版本未包含官方示例</Typography.Paragraph>}
      {sampleActions}
    </section>
    {consent}
  </div>

  const attentionItems = status?.attention_items ?? []
  return <div className="workbench-page">
    <PageTaskHeader title="项目概览" description="这里展示当前安全基线和全部待办；Agent 每次修改后都从现有基线继续。" status={attentionItems.length ? `${attentionItems.length} 项需要处理` : '当前没有待处理事项'} />

    <section className="workbench-primary-panel" aria-labelledby="workbench-current-app">
      <Typography.Text className="workbench-eyebrow">当前应用</Typography.Text>
      <Typography.Title id="workbench-current-app" level={2}>{selected.name?.trim() || '未命名应用'}</Typography.Title>
      {readiness && <Space wrap size={12}>
        <Tag>{endpointLabel(readiness)}</Tag>
        <Tag>{readiness.confirmed_role_count} 个已确认权限组</Tag>
        <Tag>{readiness.confirmed_action_count} 个已确认业务动作</Tag>
        <Tag color={readiness.current_scope_runnable ? 'green' : 'default'}>{readiness.current_scope_runnable ? '当前范围可以检查' : '当前范围仍需准备'}</Tag>
      </Space>}
      <div className="workbench-next-task">
        <Typography.Text className="workbench-eyebrow">需要处理</Typography.Text>
        {attentionItems.length === 0 && <Typography.Paragraph>当前没有待处理事项。新的 Agent 代码变化到来后，界鉴会重新分析并保留人的权限决定。</Typography.Paragraph>}
        {attentionItems.length > 0 && <div className="workbench-attention-list">{attentionItems.map((item) => <article key={item.key} className={`workbench-attention-item is-${item.tone.toLowerCase()}`}>
          <div><Typography.Text strong>{item.label}</Typography.Text><Typography.Text type="secondary">{item.description}</Typography.Text></div>
          <Button type={item.tone === 'ACTION' ? 'primary' : 'default'} onClick={() => onNavigate(item.route)}>打开</Button>
        </article>)}</div>}
      </div>
      {systemIssue && <Button type="link" className="workbench-system-link" onClick={() => onNavigate('/settings/system')}>运行环境中有服务暂不可用，查看详情</Button>}
    </section>

    <section className="workbench-secondary-panel" aria-labelledby="workbench-secondary-title">
      <div className="workbench-secondary-heading"><Typography.Title id="workbench-secondary-title" level={3}>当前动态</Typography.Title><Typography.Text type="secondary">代码变化、检查结果和外部连接共享同一项目基线。</Typography.Text></div>
      <div className="workbench-secondary-list">
        <article className="workbench-secondary-item">
          <div><Typography.Text className="workbench-secondary-label">最近代码变化</Typography.Text>{!latestChange && <Typography.Text type="secondary">尚未收到 Agent 代码变化</Typography.Text>}{latestChange && <><Typography.Text strong>{latestChange.reason}</Typography.Text><Typography.Text>{latestChange.summary}</Typography.Text><Typography.Text type="secondary">实际确认 {latestChange.actual_changed_path_count} 个文件变化，直接影响 {latestChange.directly_affected_count} 条权限规则</Typography.Text></>}</div>
          <Button type="link" onClick={() => onNavigate('/changes')}>查看变化记录</Button>
        </article>
        <article className="workbench-secondary-item">
          <div><Typography.Text className="workbench-secondary-label">当前安全基线</Typography.Text>{!latest && <Typography.Text type="secondary">尚未形成可信结果</Typography.Text>}{latest && <><Space wrap><Typography.Text strong>{lifecycleLabel(latest.lifecycle)}</Typography.Text><Tag>{integrityLabel(latest.result_integrity)}</Tag></Space><Typography.Text>{latest.verdict ? verdictLabel(latest.verdict) : '尚无结论'}</Typography.Text><Typography.Text type="secondary">{formatTimestamp(latest.created_at_us ?? latest.created_at)}</Typography.Text></>}</div>
          {latest && <Button type="link" onClick={() => onNavigate('/results')}>查看完整结果</Button>}
        </article>
        <article className="workbench-secondary-item">
          <div><Typography.Text className="workbench-secondary-label">官方示例</Typography.Text><Space wrap><Typography.Text strong>{experience?.display_name?.trim() || '协作空间'}</Typography.Text>{experience?.active && <Tag color="blue">示例运行中</Tag>}</Space><Typography.Text type="secondary">通过正式产品流程验证页面响应、后台任务和真实文件后果。</Typography.Text></div>
          {sampleActions}
        </article>
        <article className="workbench-secondary-item workbench-ai-item">
          <div><Typography.Text className="workbench-secondary-label">AI 工具</Typography.Text><Typography.Text strong>{mcpStatusFailed ? '当前连接状态读取失败' : !mcpStatus ? '正在读取连接状态' : !mcpStatus.paired ? '尚未连接 AI 工具' : mcpStatus.client_connected ? `${mcpStatus.client_name?.trim() || 'AI 工具'} 已连接` : mcpStatus.accepting_connections ? '已配对，正在等待客户端连接' : '连接已暂停'}</Typography.Text><Typography.Text type="secondary">AI 工具可以提交代码变化，但不能批准或改写人的权限规则。</Typography.Text></div>
          <Button type="link" onClick={() => onNavigate('/tools')}>连接与授权</Button>
        </article>
      </div>
    </section>
    {consent}
  </div>
}
