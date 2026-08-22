/* 权限规则页面：编排执行配置、只读规则浏览和独立高级治理面板。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, List, Select, Space, Tag, Typography } from 'antd'
import { contractsApi, type ContractSummaryDto, type PermissionContractDto } from '../../api/contracts'
import { executionProfilesApi, type ExecutionProfileDto, type ExecutionProfileSummaryDto } from '../../api/executionProfiles'
import { ApiError } from '../../api/http'
import type { LLMProfile } from '../../api/llm'
import type { ProjectDto } from '../../api/projects'
import { expectationLabel, productTermLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { PermissionGovernancePanel } from './governance/PermissionGovernancePanel'
import { PermissionExplorer } from './explorer/PermissionExplorer'
import './permissions.css'

export function PermissionRulesPage({ project, profiles = [], onError, onNext }: { project: ProjectDto; profiles?: LLMProfile[]; onError: (error: ApiError) => void; onNext?: () => void }) {
  const [permissionProfiles, setPermissionProfiles] = useState<ExecutionProfileDto[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [permissionContract, setPermissionContract] = useState<PermissionContractDto | null>(null)
  const [profileSummary, setProfileSummary] = useState<ExecutionProfileSummaryDto | null>(null)
  const [governedContracts, setGovernedContracts] = useState<ContractSummaryDto[]>([])

  const refresh = async () => {
    try {
      const [profileItems, governed] = await Promise.all([executionProfilesApi.profiles(project.project_id), contractsApi.contracts(project.project_id)])
      setPermissionProfiles(profileItems)
      setSelectedProfileId((current) => current && profileItems.some((item) => item.profile_id === current) ? current : profileItems.length === 1 ? profileItems[0].profile_id : undefined)
      setGovernedContracts(governed)
    } catch (error) { onError(error as ApiError) }
  }

  useEffect(() => {
    setPermissionContract(null)
    setProfileSummary(null)
    setSelectedProfileId(undefined)
    void refresh()
  }, [project.project_id])
  useEffect(() => {
    if (!selectedProfileId) { setPermissionContract(null); setProfileSummary(null); return }
    void Promise.all([
      executionProfilesApi.contract(project.project_id, selectedProfileId),
      executionProfilesApi.summary(project.project_id, selectedProfileId),
    ]).then(([contract, summary]) => { setPermissionContract(contract); setProfileSummary(summary) }).catch((error) => onError(error as ApiError))
  }, [project.project_id, selectedProfileId])

  const hasRule = Boolean(permissionContract || governedContracts.some((item) => String(item.status).toUpperCase() === 'ACTIVE'))
  const governedRules = governedContracts.flatMap((contract) => contract.rules.map((rule) => ({ ...rule, contractId: contract.id, contractVersion: contract.version })))

  return <Space direction="vertical" size="middle" className="full-width">
    <PageTaskHeader title="权限规则" description="查看身份、动作和资源之间已声明的授权边界。" status={hasRule ? '规则已就绪' : '需要完善规则'} next={hasRule ? '可以开始一次检查' : '在高级规则治理中补齐并审阅规则'} actionLabel={hasRule ? '开始检查' : undefined} onAction={hasRule ? onNext : undefined} />
    <Card title="当前执行配置" extra={<Space wrap><Button onClick={() => void refresh()}>刷新</Button>{permissionProfiles.length > 1 && <Select aria-label="选择执行配置" placeholder="选择已登记执行配置" value={selectedProfileId} onChange={setSelectedProfileId} options={permissionProfiles.map((item, index) => ({ value: item.profile_id, label: item.name ?? `执行配置 ${index + 1}` }))} />}</Space>}>
      {permissionProfiles.length === 0 && <Alert type="info" showIcon message="当前应用没有已登记的执行配置。" description="下面的当前治理规则摘要只展示已激活契约的规则字段；由于缺少执行配置，不生成矩阵或关系图实体。" />}
      {permissionProfiles.length === 1 && <Typography.Paragraph type="secondary">已自动选择唯一的已登记执行配置。</Typography.Paragraph>}
      {permissionProfiles.length > 1 && !selectedProfileId && <Typography.Paragraph type="secondary">请选择要查看的已登记权限配置。</Typography.Paragraph>}
      {permissionContract && profileSummary && <ExecutionIntentSummary contract={permissionContract} summary={profileSummary} />}
      {permissionContract && <PermissionExplorer contract={permissionContract} />}
      {!permissionContract && governedRules.length > 0 && <List header={<Typography.Text strong>当前治理规则摘要</Typography.Text>} dataSource={governedRules} renderItem={(rule) => <List.Item><Space wrap><Typography.Text code>{rule.rule_id ?? rule.id ?? '未提供'}</Typography.Text><Typography.Text>{expectationLabel(rule.expectation)}</Typography.Text><Typography.Text type="secondary">{rule.contractId} v{rule.contractVersion}</Typography.Text></Space></List.Item>} />}
      {!permissionContract && governedRules.length > 0 && permissionProfiles.length === 0 && <Typography.Paragraph type="secondary">当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。</Typography.Paragraph>}
    </Card>
    <Collapse ghost items={[{ key: 'advanced-governance', label: '高级：规则治理与当前配置', forceRender: true, children: <PermissionGovernancePanel project={project} profiles={profiles} onError={onError} onChanged={() => void refresh()} /> }]} />
  </Space>
}

const effectKindLabels: Record<string, string> = {
  STATE_MUTATION: '状态变更',
  DATA_DISCLOSURE: '受保护数据披露',
  OBJECT_CREATION: '对象创建',
  EXTERNAL_DISPATCH: '外部发送',
  RESTRICTED_FUNCTION_INVOCATION: '受限功能调用',
  CREDENTIAL_ACCESS: '凭据访问',
}
const closureLabels: Record<string, string> = {
  IMMEDIATE: '即时闭合',
  TERMINAL_STATE: '达到终态后闭合',
  BOUNDED_QUIESCENCE: '有界静默窗口闭合',
  EXCLUSIVE_CHANNEL_WINDOW: '独占观察窗口闭合',
}
const baselineLabels: Record<string, string> = {
  EXACT_RESTORE: '恢复同一资源',
  NORMALIZED_EQUIVALENCE: '安全相关状态等价',
}
const channelLabels: Record<string, string> = { resource_state: '资源状态' }

function ExecutionIntentSummary({ contract, summary }: { contract: PermissionContractDto; summary: ExecutionProfileSummaryDto }) {
  const actions = new Map((contract.actions ?? []).map((action) => [action.action_id, action]))
  const bindings = new Map(summary.effect_bindings.map((binding) => [binding.effect_id, binding]))
  return <Card type="inner" title="业务流程与真实影响" className="permission-intent-summary">
    <Typography.Paragraph type="secondary">这里显示检查时实际采用的目标步骤、基线方式和可信观察通道；协议标识仅作为辅助信息保留。</Typography.Paragraph>
    <List size="small" header={<Typography.Text strong>业务流程</Typography.Text>} dataSource={summary.workflows} locale={{ emptyText: '未登记可执行的业务流程' }} renderItem={(workflow) => <List.Item><Descriptions size="small" column={{ xs: 1, md: 2 }} className="full-width">
      <Descriptions.Item label="操作">{productTermLabel('action', workflow.action_id)}</Descriptions.Item>
      <Descriptions.Item label="目标步骤"><Tag color="blue">{workflow.target_step.method}</Tag> <Typography.Text code>{workflow.target_step.path}</Typography.Text></Descriptions.Item>
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
