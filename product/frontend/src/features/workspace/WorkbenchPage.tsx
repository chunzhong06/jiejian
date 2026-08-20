// 工作台聚合应用、权限规则、最近检查和环境状态，提供下一步主操作。

import { useEffect, useMemo, useState } from 'react'
import { Card, Col, List, Row, Space, Statistic, Tag, Typography } from 'antd'
import { contractsApi, type ContractSummaryDto, type GovernanceWorkspaceDto } from '../../api/contracts'
import { ApiError } from '../../api/http'
import { LLMProfile } from '../../api/llm'
import { SystemStatus } from '../../api/system'
import type { ProjectDto } from '../../api/projects'
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

function statusColor(value: unknown) {
  const raw = String(value ?? 'unknown')
  return raw === 'available' || raw === 'running' || raw === 'configured' ? 'green' : raw === 'unavailable' || raw === 'stopped' ? 'red' : 'default'
}

function ruleCount(contracts: ContractSummaryDto[], governance: GovernanceWorkspaceDto | null) {
  const project = governance?.project ?? {}
  const versions = governance?.versions ?? []
  const active = versions.find((version) => version.status === 'ACTIVE'
    && String(version.contract_id) === String(project.governed_contract_id)
    && Number(version.version) === Number(project.governed_contract_version))
  if (active) return Array.isArray(active.snapshot?.rules) ? active.snapshot.rules.length : 0
  return contracts.reduce((total, item) => total + item.rules.length, 0)
}

export function WorkbenchPage({
  selected,
  runs,
  systemStatus,
  profiles,
  llmLoadFailed,
  onNavigate,
  onError,
}: {
  selected: ProjectDto | null
  runs: RunDto[]
  systemStatus: SystemStatus
  profiles: LLMProfile[]
  llmLoadFailed: boolean
  onNavigate: (path: string) => void
  onError: (error: ApiError) => void
}) {
  const [contracts, setContracts] = useState<ContractSummaryDto[] | null>(null)
  const [governance, setGovernance] = useState<GovernanceWorkspaceDto | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setContracts(null)
    setGovernance(null)
    if (!selected?.project_id) return
    setLoading(true)
    // Contract 列表与治理快照共同决定就绪状态，必须成对成功后再开放下一步入口。
    Promise.all([contractsApi.contracts(String(selected.project_id)), contractsApi.contractGovernance(String(selected.project_id))])
      .then(([nextContracts, nextGovernance]) => {
        if (!Array.isArray(nextContracts)) throw new ApiError('INVALID_RESPONSE', '权限规则返回格式不可用')
        setContracts(nextContracts)
        setGovernance(nextGovernance)
      })
      .catch((error) => onError(error as ApiError))
      .finally(() => setLoading(false))
  }, [selected?.project_id])

  const latest = runs[0]
  const hasData = contracts !== null
  const count = hasData ? ruleCount(contracts, governance) : null
  const hasRules = count !== null && count > 0
  const modelStatus = llmLoadFailed ? 'unknown' : profiles.some((profile) => profile.enabled && profile.secret_configured && profile.connection_status === 'available') ? 'available' : 'unknown'
  const issues = useMemo(() => {
    const result: string[] = []
    if (!selected) return ['还没有选择要检查的应用']
    if (hasData && !hasRules) result.push('还没有可执行的权限规则')
    if (systemStatus.api === 'unknown' || systemStatus.worker === 'stopped' || systemStatus.browser === 'unavailable') result.push('运行环境中有服务暂不可用')
    if (latest?.result_integrity === 'INVALID') result.push('最近检查的结果完整性无效')
    return result
  }, [hasData, hasRules, latest?.result_integrity, selected, systemStatus.api, systemStatus.browser, systemStatus.worker])
  const action = !selected ? { label: '选择应用', path: '/apps/access' } : !hasData || loading ? null : !hasRules ? { label: '完善权限规则', path: '/apps/rules' } : latest && ['COMPLETED', 'SAFETY_STOPPED'].includes(String(latest.lifecycle)) && latest.result_integrity !== 'UNAVAILABLE' ? { label: '查看检查结果', path: '/checks/results' } : { label: '开始检查', path: '/checks/start' }

  if (!selected) return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="工作台" description="集中查看当前应用、检查准备情况与最近结果。" status="等待选择应用" next="接入或选择要检查的应用" actionLabel="选择应用" onAction={() => onNavigate('/apps/access')} />
    <div className="workbench-empty"><Typography.Title level={3}>还没有选择要检查的应用。</Typography.Title><Typography.Paragraph type="secondary">选择应用后，这里会显示规则、运行环境和最近检查的真实状态。</Typography.Paragraph></div>
  </Space>

  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader title="工作台" description={`当前应用：${String(selected.name ?? selected.project_id)}`} status={issues.length === 0 ? '可以开始检查' : `${issues.length} 项需要处理`} next={action?.label} actionLabel={action?.label} onAction={action ? () => onNavigate(action.path) : undefined} />
    <Card className="workbench-overview" title="检查准备情况" loading={loading}>
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}><Statistic title="应用" value="已选择" /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="权限规则" value={count === null ? '未知' : count} suffix={count === null ? undefined : '条'} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="服务" value={statusLabel(systemStatus.api)} valueStyle={{ color: statusColor(systemStatus.api) === 'green' ? '#389e0d' : undefined }} /></Col>
        <Col xs={24} sm={12} lg={6}><Statistic title="执行 / 浏览器" value={`${statusLabel(systemStatus.worker)} / ${statusLabel(systemStatus.browser)}`} /></Col>
      </Row>
      {issues.length > 0 && <List className="workbench-issues" header="当前需要处理" dataSource={issues} renderItem={(issue) => <List.Item><Typography.Text type="warning">{issue}</Typography.Text></List.Item>} />}
    </Card>
    <Card title="最近检查" extra={<Typography.Text type="secondary">模型服务：{statusLabel(modelStatus)}</Typography.Text>}>
      <List dataSource={runs.slice(0, 5)} locale={{ emptyText: '尚未开始检查' }} renderItem={(run, index) => <List.Item className={index === 0 ? 'latest-run' : undefined}>
        <List.Item.Meta title={<Space wrap><Typography.Text strong>{index === 0 ? '最近一次 · ' : ''}{lifecycleLabel(run.lifecycle)}</Typography.Text><Tag>{integrityLabel(run.result_integrity)}</Tag></Space>} description={<Space direction="vertical" size={2}><Typography.Text>{run.verdict ? verdictLabel(run.verdict) : '尚无结论'}</Typography.Text><Typography.Text type="secondary">{formatTimestamp(run.created_at_us ?? run.created_at)}</Typography.Text></Space>} />
      </List.Item>} />
    </Card>
  </Space>
}
