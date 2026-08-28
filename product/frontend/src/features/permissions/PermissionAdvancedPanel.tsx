/* 权限高级面板：只读浏览生成配置，并提供与普通检查主线隔离的规则治理入口。 */

import { useEffect, useState } from 'react'
import { Alert, Card, Descriptions, List, Select, Space, Typography } from 'antd'
import { contractsApi, type ContractSummaryDto, type PermissionContractDto } from '../../api/contracts'
import { executionProfilesApi, type ExecutionProfileDto, type ExecutionProfileSummaryDto } from '../../api/executionProfiles'
import { ApiError } from '../../api/http'
import type { ProjectDto } from '../../api/projects'
import { expectationLabel, productTermLabel } from '../../app/presentation'
import { AdvancedDetails } from '../../components/AdvancedDetails'
import { PermissionExplorer } from './explorer/PermissionExplorer'
import { PermissionGovernancePanel } from './governance/PermissionGovernancePanel'
import './permissions.css'

export function PermissionAdvancedPanel({ project, onError, onAuthorityChanged }: {
  project: ProjectDto
  onError: (error: ApiError) => void
  onAuthorityChanged: () => void
}) {
  const [profiles, setProfiles] = useState<ExecutionProfileDto[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [contract, setContract] = useState<PermissionContractDto | null>(null)
  const [summary, setSummary] = useState<ExecutionProfileSummaryDto | null>(null)
  const [governedContracts, setGovernedContracts] = useState<ContractSummaryDto[]>([])

  const refresh = async () => {
    try {
      const [profileItems, governed] = await Promise.all([
        executionProfilesApi.profiles(project.project_id),
        contractsApi.contracts(project.project_id),
      ])
      setProfiles(profileItems)
      setGovernedContracts(governed)
      setSelectedProfileId((current) => current && profileItems.some((item) => item.profile_id === current)
        ? current
        : profileItems.length === 1 ? profileItems[0].profile_id : undefined)
    } catch (error) { onError(error as ApiError) }
  }

  useEffect(() => {
    setProfiles([])
    setSelectedProfileId(undefined)
    setContract(null)
    setSummary(null)
    setGovernedContracts([])
    void refresh()
  }, [project.project_id])

  useEffect(() => {
    if (!selectedProfileId) { setContract(null); setSummary(null); return }
    let active = true
    void Promise.all([
      executionProfilesApi.contract(project.project_id, selectedProfileId),
      executionProfilesApi.summary(project.project_id, selectedProfileId),
    ]).then(([nextContract, nextSummary]) => {
      if (active) { setContract(nextContract); setSummary(nextSummary) }
    }).catch((error) => { if (active) onError(error as ApiError) })
    return () => { active = false }
  }, [project.project_id, selectedProfileId])

  const governedRules = governedContracts.flatMap((item) => item.rules.map((rule) => ({ ...rule, contractId: item.id, contractVersion: item.version })))
  const changed = () => {
    onAuthorityChanged()
    void refresh()
  }

  return <div className="permission-advanced-panels">
    <AdvancedDetails label="高级：生成配置与规则详情">
      <Card title="当前执行配置" extra={profiles.length > 1 ? <Select aria-label="选择执行配置" placeholder="选择已登记执行配置" value={selectedProfileId} onChange={setSelectedProfileId} options={profiles.map((item, index) => ({ value: item.profile_id, label: item.name ?? `执行配置 ${index + 1}` }))} /> : undefined}>
        {profiles.length === 0 && <Alert type="info" showIcon message="当前应用没有已登记的执行配置。" description="当前治理规则可以继续查看，但关系视图需要完整执行配置。" />}
        {profiles.length === 1 && <Typography.Paragraph type="secondary">已自动选择唯一的已登记执行配置。</Typography.Paragraph>}
        {profiles.length > 1 && !selectedProfileId && <Typography.Paragraph type="secondary">请选择要查看的已登记权限配置。</Typography.Paragraph>}
        {contract && summary && <ExecutionIntentSummary contract={contract} summary={summary} />}
        {contract && <PermissionExplorer contract={contract} />}
        {!contract && governedRules.length > 0 && <List header={<Typography.Text strong>当前治理规则摘要</Typography.Text>} dataSource={governedRules} renderItem={(rule) => <List.Item><Space wrap><Typography.Text code>{rule.rule_id ?? rule.id ?? '未提供'}</Typography.Text><Typography.Text>{expectationLabel(rule.expectation)}</Typography.Text><Typography.Text type="secondary">{rule.contractId} v{rule.contractVersion}</Typography.Text></Space></List.Item>} />}
        {!contract && governedRules.length > 0 && profiles.length === 0 && <Typography.Paragraph type="secondary">当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。</Typography.Paragraph>}
      </Card>
    </AdvancedDetails>
    <AdvancedDetails label="高级：规则治理与手工配置">
      <PermissionGovernancePanel project={project} onError={onError} onChanged={changed} />
    </AdvancedDetails>
  </div>
}

const effectKindLabels: Record<string, string> = {
  STATE_MUTATION: '状态变更', DATA_DISCLOSURE: '受保护数据披露', OBJECT_CREATION: '对象创建',
  EXTERNAL_DISPATCH: '外部发送', RESTRICTED_FUNCTION_INVOCATION: '受限功能调用', CREDENTIAL_ACCESS: '凭据访问',
}
const closureLabels: Record<string, string> = {
  IMMEDIATE: '即时闭合', TERMINAL_STATE: '达到终态后闭合', BOUNDED_QUIESCENCE: '有界静默窗口闭合', EXCLUSIVE_CHANNEL_WINDOW: '独占观察窗口闭合',
}
const baselineLabels: Record<string, string> = { EXACT_RESTORE: '恢复同一资源', NORMALIZED_EQUIVALENCE: '安全相关状态等价' }
const channelLabels: Record<string, string> = { resource_state: '资源状态' }

function ExecutionIntentSummary({ contract, summary }: { contract: PermissionContractDto; summary: ExecutionProfileSummaryDto }) {
  const actions = new Map((contract.actions ?? []).map((action) => [action.action_id, action]))
  const bindings = new Map(summary.effect_bindings.map((binding) => [binding.effect_id, binding]))
  return <Card type="inner" title="业务流程与真实影响" className="permission-intent-summary">
    <Typography.Paragraph type="secondary">这里显示检查时采用的目标步骤、基线方式和可信观察通道；协议标识只作为高级信息保留。</Typography.Paragraph>
    <List size="small" header={<Typography.Text strong>业务流程</Typography.Text>} dataSource={summary.workflows} locale={{ emptyText: '未登记可执行的业务流程' }} renderItem={(workflow) => <List.Item><Descriptions size="small" column={{ xs: 1, md: 2 }} className="full-width">
      <Descriptions.Item label="操作">{productTermLabel('action', workflow.action_id)}</Descriptions.Item>
      <Descriptions.Item label="目标步骤"><Typography.Text code>{workflow.target_step.method} {workflow.target_step.path}</Typography.Text></Descriptions.Item>
      <Descriptions.Item label="准备与清理">准备 {workflow.setup_step_count} 步，清理 {workflow.cleanup_step_count} 步</Descriptions.Item>
      <Descriptions.Item label="基线可比方式">{workflow.baseline_modes.map((mode) => baselineLabels[mode] ?? mode).join('、') || '未声明基线投影'}</Descriptions.Item>
    </Descriptions></List.Item>} />
    <List size="small" header={<Typography.Text strong>真实影响与观察方式</Typography.Text>} dataSource={contract.effects ?? []} locale={{ emptyText: '权限契约未声明真实影响' }} renderItem={(effect) => {
      const binding = bindings.get(effect.effect_id)
      const actionIds = [...actions.values()].filter((action) => action.effect_ids?.includes(effect.effect_id)).map((action) => productTermLabel('action', action.action_id, false))
      return <List.Item><Descriptions size="small" column={{ xs: 1, md: 2 }} className="full-width">
        <Descriptions.Item label="真实影响"><Typography.Text strong>{effectKindLabels[effect.kind] ?? effect.kind}</Typography.Text> <Typography.Text type="secondary">{effect.effect_id}</Typography.Text></Descriptions.Item>
        <Descriptions.Item label="适用操作">{actionIds.join('、') || '未关联操作'}</Descriptions.Item>
        <Descriptions.Item label="权威观察">{binding?.required_channels.map((channel) => channelLabels[channel] ?? channel).join('、') || '未绑定'}</Descriptions.Item>
        <Descriptions.Item label="证据闭合">{binding ? closureLabels[binding.closure_policy] ?? binding.closure_policy : '未绑定'}</Descriptions.Item>
      </Descriptions></List.Item>
    }} />
  </Card>
}
