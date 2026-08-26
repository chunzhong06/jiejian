// 工作台先展示确定性 guidance，再将已白名单化的 AI 排序解释作为辅助信息。

import { useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Col, List, Row, Space, Statistic, Tag, Typography } from 'antd'
import { assistantApi, type AssistantGuidance } from '../../api/assistant'
import { LLMProfile } from '../../api/llm'
import { SystemStatus } from '../../api/system'
import type { ProjectDto, ProjectReadinessDto } from '../../api/projects'
import type { RunDto } from '../../api/runs'
import { formatTimestamp, integrityLabel, lifecycleLabel, verdictLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'

function statusLabel(value: unknown) {
  const raw = String(value ?? 'unknown')
  if (raw === 'available' || raw === 'running') return '可用'
  if (raw === 'configured') return '已配置'
  if (raw === 'unavailable' || raw === 'stopped') return '不可用'
  return '未知'
}

const nextActions: Record<ProjectReadinessDto['next_required_action'], { label: string; path: string }> = {
  CONNECT_APPLICATION: { label: '接入应用', path: '/apps/access' },
  CONFIRM_TARGET: { label: '确认本地地址', path: '/apps/access' },
  AUTHORIZE_SOURCE_ANALYSIS: { label: '授权源码分析', path: '/apps/access' },
  REVIEW_DISCOVERY: { label: '确认角色与操作', path: '/apps/access' },
  RECORD_FLOW: { label: '准备测试账号并录制关键业务动作', path: '/apps/identities' },
  REVIEW_PERMISSION: { label: '确认权限规则', path: '/apps/rules' },
  RUN_CHECK: { label: '开始检查', path: '/checks/start' },
  OPEN_RESULT: { label: '查看检查结果', path: '/checks/results' },
}

function endpointLabel(readiness: ProjectReadinessDto) {
  if (readiness.endpoint_status === 'CONFIRMED' || readiness.endpoint_status === 'LEGACY_PROFILE') return '已确认'
  if (readiness.endpoint_status === 'UNAVAILABLE') return '暂不可达'
  return '待确认'
}

export function WorkbenchPage({
  selected,
  readiness,
  runs,
  systemStatus,
  profiles,
  llmLoadFailed,
  onNavigate,
}: {
  selected: ProjectDto | null
  readiness: ProjectReadinessDto | null
  runs: RunDto[]
  systemStatus: SystemStatus
  profiles: LLMProfile[]
  llmLoadFailed: boolean
  onNavigate: (path: string) => void
}) {
  const [assistant, setAssistant] = useState<AssistantGuidance | null>(null)
  const automaticRefreshKey = useRef<string | null>(null)
  const readinessKey = JSON.stringify(readiness)
  useEffect(() => {
    if (!selected) {
      setAssistant(null)
      return
    }
    let active = true
    // 页面切换或 readiness 刷新后忽略陈旧响应；同一事实指纹只允许一次自动刷新。
    void assistantApi.guidance(selected.project_id).then((value) => {
      if (!active) return
      setAssistant(value)
      if (value.status !== 'REFRESH_NEEDED') return
      const key = `${selected.project_id}:jiejian.next_step:${value.guidance.state_fingerprint}`
      if (automaticRefreshKey.current === key) return
      automaticRefreshKey.current = key
      return assistantApi.refresh(selected.project_id).then((refreshed) => {
        if (active) setAssistant(refreshed)
      }).catch(() => undefined)
    }).catch(() => undefined)
    return () => { active = false }
  }, [readinessKey, selected?.project_id])

  const retryAssistant = () => {
    if (!selected) return
    void assistantApi.refresh(selected.project_id, true).then(setAssistant).catch(() => undefined)
  }
  const latest = runs[0]
  const modelStatus = llmLoadFailed ? 'unknown' : profiles.some((profile) => profile.enabled && profile.secret_configured && profile.connection_status === 'available') ? 'available' : 'unknown'
  const issues = useMemo(() => {
    const result: string[] = []
    if (!selected) return ['还没有选择要检查的应用']
    if (!readiness) return ['正在读取应用准备状态']
    if (!['CONFIRMED', 'LEGACY_PROFILE'].includes(readiness.endpoint_status)) result.push('本地应用地址尚未确认')
    if (readiness.source_analysis_status === 'STALE') result.push('源码已变化，需要重新分析并复核候选')
    const pendingPermissionActions = readiness.permission_actions?.filter((action) => !action.compilable) ?? []
    if (pendingPermissionActions.length > 0) result.push(`${pendingPermissionActions.length} 个业务动作仍需完成权限确认`)
    if (!readiness.active_contract_available) result.push('权限规则尚未确认')
    if (systemStatus.api === 'unknown' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable') result.push('运行环境中有服务暂不可用')
    if (latest?.result_integrity === 'INVALID') result.push('最近检查的结果完整性无效')
    return result
  }, [latest?.result_integrity, readiness, selected, systemStatus.api, systemStatus.browser, systemStatus.worker])

  if (!selected) return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="工作台" description="集中查看当前应用、检查准备情况与最近结果。" status="等待选择应用" next="接入或选择要检查的应用" actionLabel="选择应用" onAction={() => onNavigate('/apps/access')} />
    <div className="workbench-empty"><Typography.Title level={3}>还没有选择要检查的应用。</Typography.Title><Typography.Paragraph type="secondary">选择应用后，这里会从后端恢复本地地址、角色、业务动作和下一步。</Typography.Paragraph></div>
  </Space>

  const guidanceOption = assistant?.guidance.options.find((item) => item.priority_tier === 'PRIMARY')
    ?? assistant?.guidance.options.find((item) => item.priority_tier === 'BLOCKING')
  const action = guidanceOption
    ? { label: guidanceOption.title, path: guidanceOption.route }
    : readiness ? nextActions[readiness.next_required_action] : null
  const recommendedOptions = new Map((assistant?.guidance.options ?? []).map((item) => [item.option_id, item]))
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="工作台" description={`当前应用：${String(selected.name ?? selected.project_id)}`} status={issues.length === 0 ? '准备状态完整' : `${issues.length} 项需要处理`} next={action?.label} actionLabel={action?.label} onAction={action ? () => onNavigate(action.path) : undefined} />
    <Card className="workbench-overview" title="应用准备情况" loading={!readiness}>
      {readiness && <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}><Statistic title="本地地址" value={endpointLabel(readiness)} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="已确认角色" value={readiness.confirmed_role_count} suffix={`/ ${readiness.discovered_role_count}`} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="已确认业务动作" value={readiness.confirmed_action_count} suffix={`/ ${readiness.discovered_action_count}`} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="权限规则" value={readiness.active_contract_available ? '已确认' : '待确认'} /></Col>
      </Row>}
      {issues.length > 0 && <List className="workbench-issues" header="当前需要处理" dataSource={issues} renderItem={(issue) => <List.Item><Typography.Text type="warning">{issue}</Typography.Text></List.Item>} />}
    </Card>
    {assistant && <Card className="assistant-assistance-card" title={<Space><span>下一步建议</span>{assistant.status === 'READY' && <span className="assistant-label">[AI辅助]</span>}</Space>}>
      <Typography.Text strong>界鉴确定</Typography.Text>
      <List
        size="small"
        dataSource={assistant.guidance.options}
        renderItem={(option) => <List.Item><Typography.Text>{option.title}</Typography.Text></List.Item>}
      />
      {assistant.status === 'READY' && assistant.recommendations.length > 0 && <>
        <Typography.Text strong className="assistant-label">[AI辅助] 推荐优先</Typography.Text>
        <List
          size="small"
          dataSource={assistant.recommendations.filter((item) => recommendedOptions.has(item.option_id))}
          renderItem={(item) => <List.Item><List.Item.Meta title={recommendedOptions.get(item.option_id)?.title} description={item.explanation} /></List.Item>}
        />
      </>}
      {assistant.status === 'BACKOFF' && <Space direction="vertical"><Typography.Text type="secondary">AI 辅助暂未更新，确定性主流程仍可继续。</Typography.Text><Button size="small" onClick={retryAssistant}>重试 AI 辅助</Button></Space>}
    </Card>}
    <Card title="最近检查" extra={<Typography.Text type="secondary">服务：{statusLabel(systemStatus.api)} · 模型服务：{statusLabel(modelStatus)}</Typography.Text>}>
      <List dataSource={runs.slice(0, 5)} locale={{ emptyText: '尚未开始检查' }} renderItem={(run, index) => <List.Item className={index === 0 ? 'latest-run' : undefined}>
        <List.Item.Meta title={<Space wrap><Typography.Text strong>{index === 0 ? '最近一次 · ' : ''}{lifecycleLabel(run.lifecycle)}</Typography.Text><Tag>{integrityLabel(run.result_integrity)}</Tag></Space>} description={<Space direction="vertical" size={2}><Typography.Text>{run.verdict ? verdictLabel(run.verdict) : '尚无结论'}</Typography.Text><Typography.Text type="secondary">{formatTimestamp(run.created_at_us ?? run.created_at)}</Typography.Text></Space>} />
      </List.Item>} />
    </Card>
  </Space>
}
