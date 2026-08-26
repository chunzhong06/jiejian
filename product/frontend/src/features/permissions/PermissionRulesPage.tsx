/* 权限规则页面：编排执行配置、只读规则浏览和独立高级治理面板。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, List, Segmented, Select, Space, Tag, Typography } from 'antd'
import { contractsApi, type ContractSummaryDto, type PermissionContractDto } from '../../api/contracts'
import { executionProfilesApi, type ExecutionProfileDto, type ExecutionProfileSummaryDto } from '../../api/executionProfiles'
import { ApiError } from '../../api/http'
import { projectsApi, type ProjectDto } from '../../api/projects'
import { permissionIntentsApi, type PermissionIntentMatrixDto, type PermissionIntentExpectation, type SecuritySetupCompileResultDto } from '../../api/permissionIntents'
import { expectationLabel, productTermLabel } from '../../app/presentation'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { PermissionGovernancePanel } from './governance/PermissionGovernancePanel'
import { PermissionExplorer } from './explorer/PermissionExplorer'
import './permissions.css'

export function PermissionRulesPage({ project, onError, onResolved, onNext }: { project: ProjectDto; onError: (error: ApiError) => void; onResolved?: () => void; onNext?: () => void }) {
  const [permissionProfiles, setPermissionProfiles] = useState<ExecutionProfileDto[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [permissionContract, setPermissionContract] = useState<PermissionContractDto | null>(null)
  const [profileSummary, setProfileSummary] = useState<ExecutionProfileSummaryDto | null>(null)
  const [governedContracts, setGovernedContracts] = useState<ContractSummaryDto[]>([])
  const [matrix, setMatrix] = useState<PermissionIntentMatrixDto | null>(null)
  const [savingCell, setSavingCell] = useState<string>()
  const [compiling, setCompiling] = useState(false)
  const [compileResult, setCompileResult] = useState<SecuritySetupCompileResultDto | null>(null)
  const [ordinaryReady, setOrdinaryReady] = useState(false)

  const refresh = async () => {
    try {
      const [profileItems, governed, permissionMatrix, readiness] = await Promise.all([executionProfilesApi.profiles(project.project_id), contractsApi.contracts(project.project_id), permissionIntentsApi.matrix(project.project_id), projectsApi.readiness(project.project_id)])
      setPermissionProfiles(profileItems)
      setSelectedProfileId((current) => current && profileItems.some((item) => item.profile_id === current) ? current : profileItems.length === 1 ? profileItems[0].profile_id : undefined)
      setGovernedContracts(governed)
      setMatrix(permissionMatrix)
      const ready = readiness.current_scope_runnable === true
      setOrdinaryReady(ready)
      if (ready) onResolved?.()
    } catch (error) { onError(error as ApiError) }
  }

  useEffect(() => {
    setPermissionContract(null)
    setProfileSummary(null)
    setSelectedProfileId(undefined)
    setMatrix(null)
    setCompileResult(null)
    setOrdinaryReady(false)
    void refresh()
  }, [project.project_id])
  useEffect(() => {
    if (!selectedProfileId) { setPermissionContract(null); setProfileSummary(null); return }
    void Promise.all([
      executionProfilesApi.contract(project.project_id, selectedProfileId),
      executionProfilesApi.summary(project.project_id, selectedProfileId),
    ]).then(([contract, summary]) => { setPermissionContract(contract); setProfileSummary(summary) }).catch((error) => onError(error as ApiError))
  }, [project.project_id, selectedProfileId])

  const governedRules = governedContracts.flatMap((contract) => contract.rules.map((rule) => ({ ...rule, contractId: contract.id, contractVersion: contract.version })))

  const confirm = async (actionId: string, subjectRoleId: string, ownerRoleId: string, relation: 'OWNS' | 'SAME_ROLE_OTHER_ACCOUNT' | 'OTHER_ROLE', value: string | number) => {
    const key = `${actionId}:${subjectRoleId}:${ownerRoleId}:${relation}`
    setSavingCell(key)
    try {
      const expectation = value === 'ALLOW' || value === 'DENY' ? value as PermissionIntentExpectation : null
      setMatrix(await permissionIntentsApi.confirm(project.project_id, actionId, subjectRoleId, ownerRoleId, relation, expectation, 'local-user'))
      setCompileResult(null)
      setOrdinaryReady(false)
    } catch (error) { onError(error as ApiError) } finally { setSavingCell(undefined) }
  }

  const compile = async () => {
    setCompiling(true)
    try {
      const result = await permissionIntentsApi.compile(project.project_id, 'local-user')
      setCompileResult(result)
      await refresh()
    } catch (error) { onError(error as ApiError) } finally { setCompiling(false) }
  }

  return <Space direction="vertical" size="large" className="full-width permission-rules-page">
    <PageTaskHeader title="权限规则" description="确认每个权限组对关键业务动作应该允许还是拒绝；测试账号只作为实际检查时的执行代表。" status={ordinaryReady ? '权限检查已就绪' : '需要确认权限期望'} next={ordinaryReady ? '可以开始一次检查' : '逐项确认允许和拒绝后准备检查'} actionLabel={ordinaryReady ? '开始检查' : undefined} onAction={ordinaryReady ? onNext : undefined} />
    <Card className="permission-intent-card" title="权限期望" extra={<Button onClick={() => void refresh()}>刷新</Button>}>
      {!matrix && <Typography.Text type="secondary">正在读取权限设置……</Typography.Text>}
      {matrix?.actions.length === 0 && <Alert type="info" showIcon message="还没有可确认的业务动作" description="请先准备测试账号，并完成至少一个业务动作的录制、资源、观察和恢复确认。" />}
      <Space direction="vertical" size="large" className="full-width permission-actions-list">
        {matrix?.actions.map((action) => <Card className="permission-action-card" key={action.action_candidate_id} type="inner" title={`业务动作：${action.action_display_name}`} extra={<Tag color={action.compilable ? 'success' : 'warning'}>{action.compilable ? '允许与拒绝已齐全' : '仍需确认'}</Tag>}>
          <div className="permission-action-summary"><Typography.Text>测试资源：{action.resource_logical_name ?? '未准备测试资源'}</Typography.Text><Typography.Text>资源所属权限组：{[...new Set(action.cells.map((cell) => cell.resource_owner_role_display_name))].join('、') || '未准备'}</Typography.Text></div>
          {action.cells.map((cell) => {
            const key = `${action.action_candidate_id}:${cell.subject_role_candidate_id}:${cell.resource_owner_role_candidate_id}:${cell.relation}`
            const blocking = cell.review_reasons.some((reason) => !['PERMISSION_INTENT_UNCONFIRMED', 'PERMISSION_INTENT_STALE'].includes(reason))
            return <div className="permission-intent-row" key={key}>
              <div><Typography.Text strong>{cell.subject_role_display_name} · {relationLabels[cell.relation]}</Typography.Text><br /><Typography.Text type="secondary">资源所属权限组：{cell.resource_owner_role_display_name}</Typography.Text></div>
              <Segmented aria-label={`${cell.subject_role_display_name}权限组以${relationLabels[cell.relation]}关系对${action.action_display_name}的权限`} value={cell.expectation ?? 'UNCONFIRMED'} disabled={blocking || savingCell === key} options={[{ label: '未确认', value: 'UNCONFIRMED' }, { label: '允许', value: 'ALLOW' }, { label: '拒绝', value: 'DENY' }]} onChange={(value) => void confirm(action.action_candidate_id, cell.subject_role_candidate_id, cell.resource_owner_role_candidate_id, cell.relation, value)} />
              {cell.status === 'NEEDS_REVIEW' && <Tag color="warning">依赖事实已变化，请重新确认</Tag>}
              {blocking && <Typography.Text type="danger">{cell.review_reasons.map((reason) => gapLabels[reason] ?? reason).join('、')}</Typography.Text>}
              {cell.execution_gap && <Typography.Text type="warning">小提示：{executionGapLabel(cell.execution_gap, cell)}</Typography.Text>}
            </div>
          })}
          {action.gaps.length > 0 && <Typography.Paragraph type="secondary" className="permission-action-gaps">尚缺：{action.gaps.map((gap) => gapLabels[gap] ?? gap).join('、')}</Typography.Paragraph>}
        </Card>)}
      </Space>
      <div className="permission-compile-panel">
        <Space wrap className="permission-compile-actions"><Button type="primary" size="large" disabled={!matrix?.compilable_action_count} loading={compiling} onClick={() => void compile()}>准备检查</Button><Typography.Text type="secondary">界鉴会根据已确认权限组生成受控检查配置。</Typography.Text></Space>
        {compileResult && <Alert type="success" showIcon message={compileResult.reused ? '当前检查已经准备好' : '检查已经准备好'} description={`已准备 ${compileResult.covered_action_ids.length} 个业务动作；${matrix?.representative_gap_count ?? 0} 项权限要求暂缺测试条件。`} />}
      </div>
    </Card>
    <Collapse items={[{ key: 'advanced-generated', label: '高级：生成配置与规则详情', forceRender: true, children: <Card title="当前执行配置" extra={<Space wrap>{permissionProfiles.length > 1 && <Select aria-label="选择执行配置" placeholder="选择已登记执行配置" value={selectedProfileId} onChange={setSelectedProfileId} options={permissionProfiles.map((item, index) => ({ value: item.profile_id, label: item.name ?? `执行配置 ${index + 1}` }))} />}</Space>}>
      {permissionProfiles.length === 0 && <Alert type="info" showIcon message="当前应用没有已登记的执行配置。" description="下面的当前治理规则摘要只展示已激活契约的规则字段；由于缺少执行配置，不生成矩阵或关系图实体。" />}
      {permissionProfiles.length === 1 && <Typography.Paragraph type="secondary">已自动选择唯一的已登记执行配置。</Typography.Paragraph>}
      {permissionProfiles.length > 1 && !selectedProfileId && <Typography.Paragraph type="secondary">请选择要查看的已登记权限配置。</Typography.Paragraph>}
      {permissionContract && profileSummary && <ExecutionIntentSummary contract={permissionContract} summary={profileSummary} />}
      {permissionContract && <PermissionExplorer contract={permissionContract} />}
      {!permissionContract && governedRules.length > 0 && <List header={<Typography.Text strong>当前治理规则摘要</Typography.Text>} dataSource={governedRules} renderItem={(rule) => <List.Item><Space wrap><Typography.Text code>{rule.rule_id ?? rule.id ?? '未提供'}</Typography.Text><Typography.Text>{expectationLabel(rule.expectation)}</Typography.Text><Typography.Text type="secondary">{rule.contractId} v{rule.contractVersion}</Typography.Text></Space></List.Item>} />}
      {!permissionContract && governedRules.length > 0 && permissionProfiles.length === 0 && <Typography.Paragraph type="secondary">当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。</Typography.Paragraph>}
    </Card> }, { key: 'advanced-governance', label: '高级：规则治理与手工配置', forceRender: true, children: <PermissionGovernancePanel project={project} onError={onError} onChanged={() => void refresh()} /> }]} />
  </Space>
}

const relationLabels: Record<string, string> = { OWNS: '自己的资源', SAME_ROLE_OTHER_ACCOUNT: '同权限组其他用户的资源', OTHER_ROLE: '其他权限组的资源' }
function executionGapLabel(gap: string, cell: PermissionIntentMatrixDto['actions'][number]['cells'][number]) {
  if (gap === 'TEST_IDENTITY_MISSING' && cell.relation === 'SAME_ROLE_OTHER_ACCOUNT') return `还需要第二个${cell.subject_role_display_name}测试账号才能实际检查这一项`
  if (gap === 'TEST_IDENTITY_MISSING') return `还需要${cell.subject_role_display_name}测试账号才能实际检查这一项`
  if (gap === 'TEST_IDENTITY_NOT_PREPARED') return `还需要${cell.subject_role_display_name}测试账号完成登录准备才能实际检查这一项`
  return gapLabels[gap] ?? gap
}
const gapLabels: Record<string, string> = {
  ACTION_FLOW_OR_RESOURCE_MISSING: '尚未录制并确认业务动作',
  ACTION_SAFETY_SETUP_STALE: '业务动作准备信息已经变化',
  RESOURCE_OWNER_ROLE_UNCONFIRMED: '资源所有者权限组尚未确认',
  TEST_RESOURCE_UNCONFIRMED: '测试资源未确认',
  OBSERVATION_UNCONFIRMED: '可信观察方式未确认',
  RECOVERY_UNCONFIRMED: '安全恢复方式未确认',
  SECURITY_EFFECT_UNCONFIRMED: '真实影响未确认',
  TEST_IDENTITY_MISSING: '缺少测试账号',
  TEST_IDENTITY_NOT_PREPARED: '测试账号尚未准备',
  ALLOW_INTENT_MISSING: '缺少一个可执行的允许权限组',
  DENY_INTENT_MISSING: '缺少一个可执行的拒绝权限组',
  PERMISSION_INTENT_NEEDS_REVIEW: '已有权限期望需要重新确认',
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
