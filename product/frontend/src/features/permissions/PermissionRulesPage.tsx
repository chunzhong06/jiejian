/* =============================================================================
 * 权限规则工作台
 *
 * 编排只读 Contract 探索和高级治理入口；矩阵与关系图不改写契约或安全结论。
 * ============================================================================= */

import { useEffect, useMemo, useState, type ChangeEvent } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, Descriptions, Divider, Form, Input, List, Select, Space, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { contractsApi } from '../../api/contracts'
import { executionProfilesApi } from '../../api/executionProfiles'
import { LLMProfile } from '../../api/llm'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { expectationLabel } from '../../app/presentation'
import { PermissionExplorer } from './PermissionExplorer'

type Item = Record<string, any>
const MAX_PERMISSION_CONTRACT_BYTES = 1024 * 1024

function label(value: unknown) { return String(value ?? '未知') }

export function PermissionRulesPage({ project, profiles = [], onError, onNext }: { project: Item; profiles?: LLMProfile[]; onError: (e: ApiError) => void; onNext?: () => void }) {
  const [permissionProfiles, setPermissionProfiles] = useState<Item[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>()
  const [permissionContract, setPermissionContract] = useState<Item | null>(null)
  const [governedContracts, setGovernedContracts] = useState<Item[]>([])
  const [workspace, setWorkspace] = useState<Item | null>(null)
  const [requirements, setRequirements] = useState<Item[]>([])
  const [candidates, setCandidates] = useState<Item[]>([])
  const [versions, setVersions] = useState<Item[]>([])
  const [llmAvailable, setLlmAvailable] = useState(false)
  const [selectedRequirements, setSelectedRequirements] = useState<string[]>([])
  const [selectedProfile, setSelectedProfile] = useState<string>()
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([])
  const [actor, setActor] = useState('local-user')
  const [selectedVersion, setSelectedVersion] = useState<Item | null>(null)
  const [analysis, setAnalysis] = useState<Item | null>(null)
  const [loading, setLoading] = useState(false)
  const [derivation, setDerivation] = useState<Item | null>(null)
  const [profilePath, setProfilePath] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'info' | 'warning'; text: string } | null>(null)
  const [contractFileName, setContractFileName] = useState('')
  const [contractSnapshot, setContractSnapshot] = useState<Item | null>(null)
  const [contractFileMessage, setContractFileMessage] = useState<string | null>(null)

  const refresh = async () => {
    try {
      const [profileItems, snapshot, governed] = await Promise.all([executionProfilesApi.profiles(project.project_id), contractsApi.contractGovernance(project.project_id), contractsApi.contracts(project.project_id)])
      setPermissionProfiles(profileItems)
      setSelectedProfileId((current) => current && profileItems.some((item) => String(item.profile_id) === current) ? current : profileItems.length === 1 ? String(profileItems[0].profile_id) : undefined)
      setWorkspace(snapshot.project as Item)
      setRequirements((snapshot.requirements ?? []) as Item[]); setCandidates((snapshot.candidates ?? []) as Item[]); setVersions((snapshot.versions ?? []) as Item[]); setLlmAvailable(Boolean(snapshot.llm_available)); setGovernedContracts(governed)
    } catch (error) { onError(error as ApiError) }
  }
  useEffect(() => { setPermissionContract(null); setSelectedProfileId(undefined); setSelectedRequirements([]); setSelectedCandidates([]); setDerivation(null); setSelectedVersion(null); setContractFileName(''); setContractSnapshot(null); setContractFileMessage(null); void refresh() }, [project.project_id])
  useEffect(() => {
    if (!selectedProfileId) { setPermissionContract(null); return }
    void executionProfilesApi.contract(project.project_id, selectedProfileId).then(setPermissionContract).catch((error) => onError(error as ApiError))
  }, [project.project_id, selectedProfileId])

  const mutate = async (operation: () => Promise<unknown>) => { setLoading(true); try { await operation(); await refresh() } catch (error) { onError(error as ApiError) } finally { setLoading(false) } }
  const addRequirement = async (values: { text: string; tags?: string }) => mutate(() => contractsApi.createRequirement(project.project_id, values.text, (values.tags ?? '').split(',').map((item) => item.trim()).filter(Boolean), actor))
  const derive = async () => mutate(async () => setDerivation(await contractsApi.deriveCandidates(project.project_id, selectedRequirements, actor)))
  const transition = async (version: Item, action: 'submit' | 'reject' | 'activate') => mutate(() => contractsApi.transitionGovernanceVersion(project.project_id, String(version.contract_id), Number(version.version), action, actor))
  const selectContract = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    setContractFileName(file?.name ?? '')
    setContractSnapshot(null)
    setContractFileMessage(null)
    if (!file) return
    if (file.size > MAX_PERMISSION_CONTRACT_BYTES) {
      setContractFileMessage('PermissionContract 文件过大，请选择不超过 1 MB 的 JSON 文件。')
      return
    }
    try {
      const parsed = JSON.parse(await file.text()) as Item
      if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object' || typeof parsed.contract_id !== 'string' || !parsed.contract_id || !Number.isInteger(parsed.version)) throw new Error('invalid-preview')
      setContractSnapshot(parsed)
    } catch {
      setContractFileMessage('无法读取 PermissionContract JSON，请确认文件包含有效的 contract_id、version 和完整契约内容。')
    }
  }
  const inspect = async (version: Item, kind: 'assessment' | 'drift' | 'diff') => { try { setSelectedVersion(version); const number = Number(version.version); setAnalysis(kind === 'assessment' ? await contractsApi.assessment(project.project_id, String(version.contract_id), number) : kind === 'drift' ? await contractsApi.drift(project.project_id, String(version.contract_id), number) : await contractsApi.diff(project.project_id, String(version.contract_id), number, number - 1)) } catch (error) { onError(error as ApiError) } }
  const registerProfile = async () => {
    const path = profilePath.trim()
    if (!path) { setProfileMessage({ type: 'warning', text: '请输入当前 ExecutionProfile 文件路径。' }); return }
    setProfileLoading(true)
    try {
      const record = await executionProfilesApi.register(path)
      if (String(record.project_id) !== String(project.project_id)) {
        setProfileMessage({ type: 'warning', text: `配置属于其他应用（${String(record.project_id)}），与当前应用不一致，未选择。` })
        return
      }
      setProfileMessage({ type: 'success', text: '配置已登记。' })
      await refresh()
      setSelectedProfileId(String(record.profile_id))
    } catch (error) { onError(error as ApiError) } finally { setProfileLoading(false) }
  }
  const active = useMemo(() => { if (!workspace?.governed_contract_id || workspace.governed_contract_version == null) return undefined; return versions.find((item) => item.status === 'ACTIVE' && item.contract_id === workspace.governed_contract_id && Number(item.version) === Number(workspace.governed_contract_version)) }, [versions, workspace])
  const selectedContractId = typeof contractSnapshot?.contract_id === 'string' ? contractSnapshot.contract_id : ''
  const selectedContractVersion = Number(contractSnapshot?.version)
  const canCreateDraft = Boolean(contractSnapshot && Number.isInteger(selectedContractVersion) && selectedContractVersion === 1 && !versions.some((item) => String(item.contract_id) === selectedContractId))
  const canReviseActive = Boolean(contractSnapshot && active && selectedContractId === String(active.contract_id) && selectedContractVersion === Number(active.version) + 1)
  const derivationIssues = [...((derivation?.batches as Item[] | undefined) ?? []).flatMap((batch) => (batch.issues ?? []) as Item[]), ...(((derivation?.merge as Item | undefined)?.issues ?? []) as Item[])]
  const blockingIssues = derivationIssues.filter((issue) => issue.severity === 'BLOCKING')
  const usableProfiles = profiles.filter((item) => item.enabled && item.secret_configured)
  const hasRule = Boolean(permissionContract || active || governedContracts.some((item) => String(item.status).toUpperCase() === 'ACTIVE'))

  return <Space direction="vertical" size="middle" className="full-width">
    <PageTaskHeader title="权限规则" description="查看身份、动作和资源之间已声明的授权边界。" status={hasRule ? '规则已就绪' : '需要完善规则'} next={hasRule ? '可以开始一次检查' : '在高级规则治理中补齐并审阅规则'} actionLabel={hasRule ? '开始检查' : undefined} onAction={hasRule ? onNext : undefined} />
     <Card title="当前执行配置" extra={<Space wrap><Button onClick={() => void refresh()}>刷新</Button>{permissionProfiles.length > 1 && <Select aria-label="选择执行配置" placeholder="选择已登记执行配置" value={selectedProfileId} onChange={setSelectedProfileId} options={permissionProfiles.map((item, index) => ({ value: String(item.profile_id), label: `ExecutionProfile ${index + 1}` }))} />}</Space>}>
      {permissionProfiles.length === 0 && <Alert type="info" showIcon message="当前项目没有已登记的 ExecutionProfile。" description="下面的当前治理规则摘要只展示已激活契约的规则字段；由于缺少 Profile，不生成矩阵或关系图实体。" />}
      {permissionProfiles.length === 1 && <Typography.Paragraph type="secondary">已自动选择唯一的已登记执行配置。</Typography.Paragraph>}
      {permissionProfiles.length > 1 && !selectedProfileId && <Typography.Paragraph type="secondary">请选择要查看的已登记权限配置。</Typography.Paragraph>}
      {permissionContract && <PermissionExplorer contract={permissionContract} />}
      {!permissionContract && governedContracts.length > 0 && <List header={<Typography.Text strong>当前治理规则摘要</Typography.Text>} dataSource={governedContracts.flatMap((item) => Array.isArray(item.rules) ? item.rules.map((rule: Item) => ({ ...rule, contract_id: item.id, contract_version: item.version })) : [])} renderItem={(rule: Item) => <List.Item><Space wrap><Typography.Text code>{label(rule.rule_id ?? rule.id)}</Typography.Text><Typography.Text>{expectationLabel(rule.expectation ?? rule.effect)}</Typography.Text><Collapse ghost items={[{ key: 'governed-rule-tech', label: '规则版本', children: <Typography.Text type="secondary">{label(rule.contract_id)} v{label(rule.contract_version)}</Typography.Text> }]} /></Space></List.Item>} />}
      {!permissionContract && governedContracts.length > 0 && permissionProfiles.length === 0 && <Typography.Paragraph type="secondary">当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。</Typography.Paragraph>}
    </Card>

    <Collapse ghost items={[{ key: 'advanced-governance', label: '高级：规则治理与当前配置', forceRender: true, children: <Space direction="vertical" className="full-width"><Card title="登记 ExecutionProfile"><Typography.Paragraph type="secondary">配置文件仅在本次操作中读取，不会写入浏览器本地存储。</Typography.Paragraph><Input aria-label="ExecutionProfile 文件路径" placeholder="D:\\profiles\\execution-profile.json" value={profilePath} onChange={(event) => setProfilePath(event.target.value)} /><Space wrap><Button loading={profileLoading} onClick={() => void registerProfile()}>登记 ExecutionProfile</Button></Space>{profileMessage && <Alert type={profileMessage.type} showIcon message={profileMessage.text} />}</Card><Card title="新增检查需求"><Form layout="inline" onFinish={addRequirement}><Form.Item name="text" rules={[{ required: true, message: '请输入受控需求模板' }]}><Input placeholder="rule id=foreign-read kind=foreign_read observers=http severity=high" style={{ width: 470 }} /></Form.Item><Form.Item name="tags"><Input placeholder="标签，用逗号分隔" /></Form.Item><Input value={actor} onChange={(event) => setActor(event.target.value)} placeholder="操作者" style={{ width: 130 }} /><Button type="primary" htmlType="submit" loading={loading}>新增需求</Button></Form></Card><Card title="需求与候选" extra={<Button type="primary" disabled={loading || selectedRequirements.length === 0} onClick={() => void derive()}>派生候选</Button>}><Space direction="vertical" className="full-width"><Checkbox.Group value={selectedRequirements} onChange={(value) => setSelectedRequirements(value as string[])} options={requirements.map((item) => ({ label: `${item.requirement_id} · ${item.text}`, value: item.requirement_id }))} /><Select aria-label="模型服务" placeholder="选择模型服务" value={selectedProfile} onChange={setSelectedProfile} options={usableProfiles.map((item) => ({ label: `${item.profile_name} · ${item.provider}`, value: item.profile_name }))} notFoundContent="无可用模型服务" /><Button disabled={!selectedProfile || selectedRequirements.length === 0} onClick={() => void mutate(() => contractsApi.llmCandidates(project.project_id, selectedRequirements, actor, selectedProfile!))}>生成候选</Button><Typography.Text type="secondary">模型只生成待审候选，不能决定安全结论。</Typography.Text>{derivation && <Alert type={blockingIssues.length ? 'error' : 'success'} showIcon message={blockingIssues.length ? '存在阻断问题，本批候选未落盘' : `候选派生完成：${(derivation.persisted_candidates as Item[]).length} 项已落盘`} description={derivationIssues.length ? derivationIssues.map((item) => `${item.severity ?? 'INFO'}:${item.code ?? item.reason_code ?? item.detail}`).join('、') : undefined} />}<List size="small" dataSource={candidates} locale={{ emptyText: '尚无候选' }} renderItem={(item) => <List.Item><Checkbox checked={selectedCandidates.includes(item.candidate_id)} onChange={(event) => setSelectedCandidates((current) => event.target.checked ? [...current, item.candidate_id] : current.filter((id) => id !== item.candidate_id))} />{item.candidate_id} · {item.rule?.id}</List.Item>} /></Space></Card><Card title="规则版本治理"><Typography.Paragraph type="secondary">选择一次 PermissionContract JSON；文件只在本次页面操作中读取，不会写入浏览器本地存储。</Typography.Paragraph><input id="permission-contract-file" type="file" accept="application/json,.json" aria-label="PermissionContract JSON 文件" onChange={(event) => void selectContract(event)} />{contractFileName && <Typography.Paragraph type="secondary">已选择：{contractFileName}</Typography.Paragraph>}{contractFileMessage && <Alert type="warning" showIcon message={contractFileMessage} />}{contractSnapshot && <Descriptions size="small" column={3}><Descriptions.Item label="contract_id">{selectedContractId}</Descriptions.Item><Descriptions.Item label="version">{selectedContractVersion}</Descriptions.Item><Descriptions.Item label="规则数量">{(Array.isArray(contractSnapshot.rules) ? contractSnapshot.rules.length : 0) + (Array.isArray(contractSnapshot.batch_rules) ? contractSnapshot.batch_rules.length : 0)}</Descriptions.Item></Descriptions>}<Space wrap><Button disabled={!canCreateDraft || loading} onClick={() => void mutate(() => contractsApi.createGovernanceContract(project.project_id, contractSnapshot!, selectedCandidates, actor))}>创建草稿</Button><Button disabled={!canReviseActive || loading} onClick={() => void mutate(() => contractsApi.reviseGovernanceContract(project.project_id, contractSnapshot!, selectedCandidates, actor))}>修订已激活规则</Button><Divider /><List size="small" dataSource={versions} locale={{ emptyText: "尚无规则版本" }} renderItem={(version) => <List.Item actions={[version.status === "DRAFT" ? <Button size="small" onClick={() => void transition(version, "submit")}>提交审阅</Button> : null, version.status === "REVIEW" ? <><Button size="small" onClick={() => void transition(version, "activate")}>激活</Button><Button size="small" onClick={() => void transition(version, "reject")}>拒绝</Button></> : null, <Button size="small" onClick={() => void inspect(version, "assessment")}>评估</Button>, <Button size="small" onClick={() => void inspect(version, "drift")}>漂移</Button>, Number(version.version) > 1 ? <Button size="small" onClick={() => void inspect(version, "diff")}>差异</Button> : null].filter(Boolean) as any}><List.Item.Meta title={String(version.contract_id) + " v" + String(version.version) + " · " + String(version.status)} description={"规则 " + (version.snapshot?.rules ?? []).map((rule: Item) => rule.id ?? rule.rule_id).join(", ")} /></List.Item>} />{selectedVersion && analysis && <Card size="small" title={String(selectedVersion.contract_id) + " v" + String(selectedVersion.version) + " 分析结果"}><pre className="report-view">{JSON.stringify(analysis, null, 2)}</pre></Card>}</Space></Card></Space> }]} />
  </Space>
}
