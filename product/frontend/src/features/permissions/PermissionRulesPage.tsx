/* 权限规则页面：编排执行配置、只读规则浏览和独立高级治理面板。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, List, Select, Space, Typography } from 'antd'
import { contractsApi, type ContractSummaryDto, type PermissionContractDto } from '../../api/contracts'
import { executionProfilesApi, type ExecutionProfileDto } from '../../api/executionProfiles'
import { ApiError } from '../../api/http'
import type { LLMProfile } from '../../api/llm'
import type { ProjectDto } from '../../api/projects'
import { expectationLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { PermissionGovernancePanel } from './governance/PermissionGovernancePanel'
import { PermissionExplorer } from './explorer/PermissionExplorer'
import './permissions.css'

export function PermissionRulesPage({ project, profiles = [], onError, onNext }: { project: ProjectDto; profiles?: LLMProfile[]; onError: (error: ApiError) => void; onNext?: () => void }) {
  const [permissionProfiles, setPermissionProfiles] = useState<ExecutionProfileDto[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [permissionContract, setPermissionContract] = useState<PermissionContractDto | null>(null)
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
    setSelectedProfileId(undefined)
    void refresh()
  }, [project.project_id])
  useEffect(() => {
    if (!selectedProfileId) { setPermissionContract(null); return }
    void executionProfilesApi.contract(project.project_id, selectedProfileId).then(setPermissionContract).catch((error) => onError(error as ApiError))
  }, [project.project_id, selectedProfileId])

  const hasRule = Boolean(permissionContract || governedContracts.some((item) => String(item.status).toUpperCase() === 'ACTIVE'))
  const governedRules = governedContracts.flatMap((contract) => contract.rules.map((rule) => ({ ...rule, contractId: contract.id, contractVersion: contract.version })))

  return <Space direction="vertical" size="middle" className="full-width">
    <PageTaskHeader title="权限规则" description="查看身份、动作和资源之间已声明的授权边界。" status={hasRule ? '规则已就绪' : '需要完善规则'} next={hasRule ? '可以开始一次检查' : '在高级规则治理中补齐并审阅规则'} actionLabel={hasRule ? '开始检查' : undefined} onAction={hasRule ? onNext : undefined} />
    <Card title="当前执行配置" extra={<Space wrap><Button onClick={() => void refresh()}>刷新</Button>{permissionProfiles.length > 1 && <Select aria-label="选择执行配置" placeholder="选择已登记执行配置" value={selectedProfileId} onChange={setSelectedProfileId} options={permissionProfiles.map((item, index) => ({ value: item.profile_id, label: item.name ?? `执行配置 ${index + 1}` }))} />}</Space>}>
      {permissionProfiles.length === 0 && <Alert type="info" showIcon message="当前应用没有已登记的执行配置。" description="下面的当前治理规则摘要只展示已激活契约的规则字段；由于缺少执行配置，不生成矩阵或关系图实体。" />}
      {permissionProfiles.length === 1 && <Typography.Paragraph type="secondary">已自动选择唯一的已登记执行配置。</Typography.Paragraph>}
      {permissionProfiles.length > 1 && !selectedProfileId && <Typography.Paragraph type="secondary">请选择要查看的已登记权限配置。</Typography.Paragraph>}
      {permissionContract && <PermissionExplorer contract={permissionContract} />}
      {!permissionContract && governedRules.length > 0 && <List header={<Typography.Text strong>当前治理规则摘要</Typography.Text>} dataSource={governedRules} renderItem={(rule) => <List.Item><Space wrap><Typography.Text code>{rule.rule_id ?? rule.id ?? '未提供'}</Typography.Text><Typography.Text>{expectationLabel(rule.expectation)}</Typography.Text><Typography.Text type="secondary">{rule.contractId} v{rule.contractVersion}</Typography.Text></Space></List.Item>} />}
      {!permissionContract && governedRules.length > 0 && permissionProfiles.length === 0 && <Typography.Paragraph type="secondary">当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。</Typography.Paragraph>}
    </Card>
    <Collapse ghost items={[{ key: 'advanced-governance', label: '高级：规则治理与当前配置', forceRender: true, children: <PermissionGovernancePanel project={project} profiles={profiles} onError={onError} onChanged={() => void refresh()} /> }]} />
  </Space>
}
