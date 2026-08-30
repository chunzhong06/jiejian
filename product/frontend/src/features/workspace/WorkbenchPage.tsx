// 工作台以确定性 Readiness 给出唯一下一步，AI 只在次级区域解释可选建议。

import { Button, Divider, Modal, Space, Tag, Typography } from 'antd'
import { useMemo, useState } from 'react'
import type { OfficialExperienceDto, OfficialExperienceMode } from '../../api/experience'
import type { MCPAccessView } from '../../api/mcp'
import type { ProductNextActionDto, ProjectDto, ProjectReadinessDto } from '../../api/projects'
import type { RunDto } from '../../api/runs'
import type { SourceChangeViewDto } from '../../api/sourceChanges'
import type { SystemStatus } from '../../api/system'
import { formatTimestamp, integrityLabel, lifecycleLabel, verdictLabel } from '../../app/presentation'
import { AssistantPanel } from '../../components/AssistantPanel'
import { PageTaskHeader } from '../../components/PageTaskHeader'

function endpointLabel(readiness: ProjectReadinessDto) {
  if (readiness.endpoint_status === 'CONFIRMED') return '已确认'
  if (readiness.endpoint_status === 'UNAVAILABLE') return '暂不可达'
  return '待确认'
}

export function WorkbenchPage({
  selected,
  readiness,
  nextAction,
  runs,
  systemStatus,
  mcpStatus,
  mcpStatusFailed = false,
  latestChange,
  experience,
  experienceBusy,
  onStartExperience,
  onStopExperience,
  onNavigate,
}: {
  selected: ProjectDto | null
  readiness: ProjectReadinessDto | null
  nextAction: ProductNextActionDto | null
  runs: RunDto[]
  systemStatus: SystemStatus
  mcpStatus?: MCPAccessView | null
  mcpStatusFailed?: boolean
  latestChange?: SourceChangeViewDto | null
  experience: OfficialExperienceDto | null
  experienceBusy: boolean
  onStartExperience: (mode: OfficialExperienceMode) => Promise<boolean>
  onStopExperience?: () => Promise<void>
  onNavigate: (path: string) => void
}) {
  const [requestedMode, setRequestedMode] = useState<OfficialExperienceMode | null>(null)
  const [showChangeDetails, setShowChangeDetails] = useState(false)
  const latest = runs[0]
  const systemIssue = systemStatus.api === 'unknown' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable'
    ? '运行环境中有服务暂不可用'
    : null
  const issues = useMemo(() => {
    const result: string[] = []
    if (!selected) return ['还没有选择要检查的应用']
    if (!readiness) return ['正在读取应用准备状态']
    if (readiness.endpoint_status !== 'CONFIRMED') result.push('本地应用地址尚未确认')
    if (readiness.source_analysis_status === 'STALE') result.push('源码已变化，需要重新分析并复核候选')
    const pendingPermissionActions = readiness.permission_actions?.filter((action) => !action.compilable) ?? []
    if (pendingPermissionActions.length > 0) result.push(`${pendingPermissionActions.length} 个业务动作仍需完成权限确认`)
    if (systemIssue) result.push(systemIssue)
    if (latest?.result_integrity === 'INVALID') result.push('最近检查的结果完整性无效')
    return result
  }, [latest?.result_integrity, readiness, selected, systemIssue])

  const sampleAvailable = experience?.available === true
  const sampleActions = experience?.active
    ? <Button disabled={experienceBusy} onClick={() => { void onStopExperience?.() }}>结束体验</Button>
    : <Space wrap size={8}>
      <Button disabled={!sampleAvailable || experienceBusy} onClick={() => setRequestedMode('GUIDED')}>评委导览</Button>
      <Button type="link" disabled={!sampleAvailable || experienceBusy} onClick={() => setRequestedMode('FULL')}>完整体验</Button>
    </Space>
  const consent = <Modal
    open={requestedMode !== null}
    title={requestedMode === 'GUIDED' ? '开始评委导览？' : '开始完整体验？'}
    okText="同意并开始"
    cancelText="取消"
    confirmLoading={experienceBusy}
    onCancel={() => setRequestedMode(null)}
    onOk={async () => {
      if (!requestedMode) return
      if (await onStartExperience(requestedMode)) setRequestedMode(null)
    }}
  >
    <Typography.Paragraph>将启动随界鉴提供的本机协作空间示例，为本次体验创建独立工作区，并访问它的本机回环地址。</Typography.Paragraph>
    {requestedMode === 'GUIDED' && <Typography.Paragraph>评委导览还会授权界鉴只读分析随产品附带的示例源码。</Typography.Paragraph>}
    <Typography.Paragraph strong>不会开始真实安全检查，也不会预先生成检查结论。</Typography.Paragraph>
  </Modal>

  if (!selected) return <div className="workbench-page">
    <PageTaskHeader title="工作台" description="从一个应用开始，界鉴会沿着六个连续步骤完成权限安全验证。" status="等待选择应用" />
    <section className="workbench-primary-panel workbench-empty" aria-labelledby="workbench-empty-title">
      <Typography.Title id="workbench-empty-title" level={3}>开始一次安全检查</Typography.Title>
      <Typography.Paragraph type="secondary">接入自己的应用，界鉴会带你完成应用理解、测试账号、业务流程和权限检查。</Typography.Paragraph>
      <Button type="primary" onClick={() => onNavigate('/application')}>接入自己的应用</Button>
    </section>
    <Divider plain>或者先体验界鉴</Divider>
    <section className="workbench-sample-entry" aria-labelledby="workbench-sample-entry-title">
      <Typography.Text className="workbench-eyebrow">官方示例</Typography.Text>
      <Typography.Title id="workbench-sample-entry-title" level={3}>协作空间</Typography.Title>
      <Typography.Paragraph>Bob 是项目普通成员，按权限要求不能导出完整项目资料包。</Typography.Paragraph>
      <Typography.Paragraph type="secondary">看看界鉴能否发现“页面虽然拒绝，但后台仍然生成资料包”的问题。</Typography.Paragraph>
      {!sampleAvailable && <Typography.Paragraph type="secondary">当前版本未包含官方示例</Typography.Paragraph>}
      {sampleActions}
    </section>
    {consent}
  </div>

  const action = nextAction
  return <div className="workbench-page">
    <PageTaskHeader title="工作台" description="查看当前应用做到哪一步，并继续完成唯一的安全检查主线。" status={issues.length === 0 ? '当前准备状态完整' : `${issues.length} 项需要处理`} />

    <section className="workbench-primary-panel" aria-labelledby="workbench-current-app">
      <Typography.Text className="workbench-eyebrow">当前应用</Typography.Text>
      <Typography.Title id="workbench-current-app" level={2}>{selected.name?.trim() || '未命名应用'}</Typography.Title>
      {readiness && <Typography.Text type="secondary">本地地址：{endpointLabel(readiness)}</Typography.Text>}
      <div className="workbench-next-task">
        <Typography.Text className="workbench-eyebrow">现在继续</Typography.Text>
        <Typography.Title level={3}>{action?.label ?? '正在读取下一步'}</Typography.Title>
        <Typography.Paragraph>{action?.description ?? '界鉴正在从统一产品状态恢复当前任务。'}</Typography.Paragraph>
      </div>
      {issues.length > 0 && <ul className="workbench-issue-list">{issues.map((issue) => <li key={issue}>{issue}</li>)}</ul>}
      {systemIssue && <Button type="link" className="workbench-system-link" onClick={() => onNavigate('/settings/system')}>查看运行环境</Button>}
      <Button className="workbench-primary-action" type="primary" disabled={!action} onClick={() => action && onNavigate(action.route)}>{action?.label ?? '正在读取'}</Button>
    </section>

    <section className="workbench-secondary-panel" aria-labelledby="workbench-secondary-title">
      <div className="workbench-secondary-heading">
        <Typography.Title id="workbench-secondary-title" level={3}>其他动态</Typography.Title>
        <Typography.Text type="secondary">需要时再展开，不影响上方唯一下一步。</Typography.Text>
      </div>
      <div className="workbench-secondary-list">
        <article className="workbench-secondary-item">
          <div><Typography.Text className="workbench-secondary-label">最近检查</Typography.Text>{!latest && <Typography.Text type="secondary">尚未开始检查</Typography.Text>}{latest && <><Space wrap><Typography.Text strong>{lifecycleLabel(latest.lifecycle)}</Typography.Text><Tag>{integrityLabel(latest.result_integrity)}</Tag></Space><Typography.Text>{latest.verdict ? verdictLabel(latest.verdict) : '尚无结论'}</Typography.Text><Typography.Text type="secondary">{formatTimestamp(latest.created_at_us ?? latest.created_at)}</Typography.Text></>}</div>
          {latest && <Space direction="vertical" align="end"><Button type="link" onClick={() => onNavigate('/results')}>查看结果</Button>{latest.result_integrity === 'VERIFIED' && <Button type="link" onClick={() => onNavigate('/verification')}>现场验证</Button>}</Space>}
        </article>
        <article className="workbench-secondary-item">
          <div><Typography.Text className="workbench-secondary-label">最近代码变化</Typography.Text>{!latestChange && <Typography.Text type="secondary">尚未收到 Agent 提交的代码变化</Typography.Text>}{latestChange && <><Typography.Text strong>{latestChange.reason}</Typography.Text><Typography.Text>{latestChange.summary}</Typography.Text><Typography.Text type="secondary">界鉴确认 {latestChange.actual_changed_path_count} 个文件发生变化</Typography.Text><Typography.Text type="secondary">直接影响 {latestChange.directly_affected_count} 条权限要求</Typography.Text><Typography.Text type={latestChange.mapping_review_required_count > 0 ? 'warning' : 'secondary'}>{latestChange.mapping_review_required_count > 0 ? `有 ${latestChange.mapping_review_required_count} 条权限要求无法自动对应到修改后的代码，需要你确认` : '已确认的权限要求都能继续对应到当前代码'}</Typography.Text>{showChangeDetails && <ChangeDetails change={latestChange} />}</>}</div>
          {latestChange && <Space direction="vertical" align="end"><Button type="link" onClick={() => setShowChangeDetails((value) => !value)}>{showChangeDetails ? '收起变化明细' : '查看变化明细'}</Button>{latestChange.next_path && <Button type="link" onClick={() => onNavigate(latestChange.next_path!)}>确认权限要求</Button>}</Space>}
        </article>
        <article className="workbench-secondary-item">
          <div><Typography.Text className="workbench-secondary-label">官方示例</Typography.Text><Space wrap><Typography.Text strong>协作空间</Typography.Text>{experience?.active && <Tag color="blue">体验进行中</Tag>}</Space><Typography.Text type="secondary">体验一次页面拒绝后后台仍产生受保护资料的真实权限问题。</Typography.Text>{!sampleAvailable && <Typography.Text type="secondary">当前版本未包含官方示例</Typography.Text>}</div>
          {sampleActions}
        </article>
        <article className="workbench-secondary-item workbench-ai-item">
          <div><Typography.Text className="workbench-secondary-label">AI 工具</Typography.Text><Typography.Text strong>{mcpStatusFailed ? '当前连接状态读取失败' : !mcpStatus ? '正在读取连接状态' : !mcpStatus.paired ? '尚未连接 AI 工具' : mcpStatus.client_connected ? `${mcpStatus.client_name?.trim() || 'AI 工具'} 已连接` : mcpStatus.accepting_connections ? '已配对，正在等待客户端连接' : '连接已暂停'}</Typography.Text><Typography.Text type="secondary">AI 工具不能批准或改写人的权限要求。</Typography.Text></div>
          <Button type="link" onClick={() => onNavigate('/tools')}>连接与授权</Button>
        </article>
      </div>
      <div className="workbench-assistant-row"><AssistantPanel projectId={selected.project_id} surface="next-step" title="下一步建议" actionLabel="生成 AI 建议" /></div>
    </section>
    {consent}
  </div>
}

function ChangeDetails({ change }: { change: SourceChangeViewDto }) {
  const groups = [
    ['界鉴实际确认新增', change.added_paths],
    ['界鉴实际确认修改', change.modified_paths],
    ['界鉴实际确认删除', change.removed_paths],
  ] as const
  return <div className="workbench-change-details">
    <Typography.Text strong>Agent 说自己改了什么</Typography.Text>
    {change.claimed_paths.length > 0 ? <ul>{change.claimed_paths.map((path) => <li key={path}><Typography.Text code>{path}</Typography.Text></li>)}</ul> : <Typography.Text type="secondary">Agent 没有提供文件线索</Typography.Text>}
    <Typography.Text strong>界鉴实际确认新增/修改/删除什么</Typography.Text>
    {groups.map(([label, paths]) => <div key={label}><Typography.Text type="secondary">{label}</Typography.Text>{paths.length > 0 ? <ul>{paths.map((path) => <li key={`${label}-${path}`}><Typography.Text code>{path}</Typography.Text></li>)}</ul> : <Typography.Text type="secondary">：无</Typography.Text>}</div>)}
  </div>
}
