/* 权限规则页面：展示已登记配置中的只读 Contract，并保留高级规则治理入口。 */

import { useEffect, useMemo, useState, type ChangeEvent } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, Descriptions, Divider, Form, Input, List, Select, Space, Tabs, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { contractsApi } from '../../api/contracts'
import { executionProfilesApi } from '../../api/executionProfiles'
import { LLMProfile } from '../../api/llm'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { expectationLabel, severityLabel } from '../../app/presentation'

type Item = Record<string, any>
type MatrixRule = Item & { batch_rule_id?: string; atomic?: boolean }
const MAX_PERMISSION_CONTRACT_BYTES = 1024 * 1024

function label(value: unknown) { return String(value ?? '未知') }
function contextSummary(value: unknown) {
  if (!value || typeof value !== 'object' || Object.keys(value as Item).length === 0) return '无附加条件'
  return Object.entries(value as Item).filter(([, item]) => item !== undefined && item !== null).map(([key, item]) => `${key}：${Array.isArray(item) ? item.join('、') : String(item)}`).join('；') || '无附加条件'
}
function endpointKey(value: Item | undefined) { return `${String(value?.endpoint_type ?? '').toLowerCase()}:${String(value?.endpoint_id ?? '')}` }

function expandedRules(contract: Item): MatrixRule[] {
  const ordinary = (Array.isArray(contract.rules) ? contract.rules : []).map((rule: Item) => ({ ...rule }))
  const batch = (Array.isArray(contract.batch_rules) ? contract.batch_rules : []).flatMap((rule: Item) =>
    (Array.isArray(rule.resource_expectations) ? rule.resource_expectations : []).map((expectation: Item) => ({
      ...rule,
      resource_id: expectation.resource_id,
      expectation: expectation.expectation,
      relation_path: expectation.relation_path ?? [],
      batch_rule_id: rule.rule_id,
      atomic: Boolean(rule.atomic),
      resource_expectation: expectation,
    })),
  )
  return [...ordinary, ...batch]
}

function ruleColumns(contract: Item) {
  const rules = expandedRules(contract)
  const seen = new Set<string>()
  return rules
    .map((rule) => ({ action_id: String(rule.action_id), resource_id: String(rule.resource_id), key: `${rule.action_id}:${rule.resource_id}` }))
    .filter((column) => !seen.has(column.key) && seen.add(column.key))
    .sort((left, right) => left.key.localeCompare(right.key))
}

function graphNodes(contract: Item) {
  const subjects = (Array.isArray(contract.subjects) ? contract.subjects : []).map((item: Item) => ({ id: String(item.subject_id), type: 'subject', roles: item.roles ?? [] }))
  const resources = (Array.isArray(contract.resources) ? contract.resources : []).map((item: Item) => ({ id: String(item.resource_id), type: 'resource', roles: [item.resource_type] }))
  return [...subjects, ...resources].sort((left, right) => `${left.type}:${left.id}`.localeCompare(`${right.type}:${right.id}`))
}

function PermissionMatrix({ contract }: { contract: Item }) {
  const [selected, setSelected] = useState<MatrixRule[] | null>(null)
  const columns = ruleColumns(contract)
  const rules = expandedRules(contract)
  const subjects = [...(Array.isArray(contract.subjects) ? contract.subjects : [])].sort((left: Item, right: Item) => String(left.subject_id).localeCompare(String(right.subject_id)))
  const rows = subjects.map((subject: Item) => {
    const row: Item = { key: String(subject.subject_id), subject }
    for (const column of columns) {
      row[column.key] = rules.filter((rule) => String(rule.subject_id) === String(subject.subject_id) && `${rule.action_id}:${rule.resource_id}` === column.key)
    }
    return row
  })
  return <Space direction="vertical" className="full-width">
    {columns.length === 0 && <Alert type="info" showIcon message="当前权限配置没有可展示的动作与资源组合。" />}
    <div className="permission-matrix-scroll"><table className="permission-matrix-table"><thead><tr><th>身份</th>{columns.map((column) => <th key={column.key}><div>{column.action_id}</div><small>{column.resource_id}</small></th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row.key}><th scope="row"><div>{label(row.subject.subject_id)}</div><small>角色：{(row.subject.roles ?? []).join('、') || '未提供'}</small></th>{columns.map((column) => { const cell = row[column.key] as MatrixRule[]; const state = cell.length === 1 ? String(cell[0].expectation).toLowerCase() : 'multiple'; return <td key={column.key} className={`permission-matrix-${state}`}>{cell.length === 0 ? <Typography.Text type="secondary">未声明</Typography.Text> : <Button type="link" className="permission-cell" onClick={() => setSelected(cell)} aria-label={`${column.action_id} ${column.resource_id} 的 ${cell.length} 条规则`}>{cell.length === 1 ? expectationLabel(cell[0].expectation) : `${cell.length} 条规则`}</Button>}</td> })}</tr>)}</tbody></table></div>
    {selected && <Card size="small" title="规则详情" extra={<Button type="link" onClick={() => setSelected(null)}>关闭</Button>}>
      <List size="small" dataSource={selected} renderItem={(rule) => <List.Item><Descriptions size="small" column={2} className="full-width">
        <Descriptions.Item label="期望">{expectationLabel(rule.expectation)}</Descriptions.Item><Descriptions.Item label="严重度">{severityLabel(rule.severity)}</Descriptions.Item>
        <Descriptions.Item label="关系路径">{(rule.relation_path ?? []).join(' → ') || '未提供'}</Descriptions.Item><Descriptions.Item label="适用条件">{contextSummary(rule.context)}</Descriptions.Item><Descriptions.Item label="必需观察">{(rule.required_observations ?? []).join('、') || '未提供'}</Descriptions.Item>
        <Descriptions.Item label="覆盖维度">{(rule.coverage_dimensions ?? []).join('、') || '未提供'}</Descriptions.Item>
        {rule.batch_rule_id && <Descriptions.Item label="批量规则">{label(rule.batch_rule_id)} · 原子：{rule.atomic ? '是' : '否'}</Descriptions.Item>}
        <Descriptions.Item span={2}><Collapse ghost items={[{ key: 'rule-tech', label: '高级：规则标识', children: <Typography.Text code>{label(rule.rule_id)}</Typography.Text> }]} /></Descriptions.Item>
      </Descriptions></List.Item>} />
    </Card>}
  </Space>
}

function PermissionGraph({ contract }: { contract: Item }) {
  const nodes = graphNodes(contract)
  const [focus, setFocus] = useState<string>()
  const allRelations = Array.isArray(contract.relations) ? contract.relations as Item[] : []
  const allRules = expandedRules(contract)
  const relatedKeys = new Set<string>()
  if (focus) {
    relatedKeys.add(focus)
    for (const relation of allRelations) { const source = endpointKey(relation.source); const target = endpointKey(relation.target); if (source === focus || target === focus) { relatedKeys.add(source); relatedKeys.add(target) } }
    for (const rule of allRules) { const subject = `subject:${String(rule.subject_id)}`; const resource = `resource:${String(rule.resource_id)}`; if (subject === focus || resource === focus) { relatedKeys.add(subject); relatedKeys.add(resource) } }
  }
  const visible = (focus ? nodes.filter((node) => relatedKeys.has(`${node.type}:${node.id}`)) : nodes).slice(0, 24)
  const subjects = visible.filter((node) => node.type === 'subject')
  const resources = visible.filter((node) => node.type === 'resource')
  const positions = new Map<string, { x: number; y: number }>()
  subjects.forEach((node, index) => positions.set(`subject:${node.id}`, { x: 110, y: 55 + index * Math.min(70, 440 / Math.max(1, subjects.length - 1)) }))
  resources.forEach((node, index) => positions.set(`resource:${node.id}`, { x: 410, y: 55 + index * Math.min(70, 440 / Math.max(1, resources.length - 1)) }))
  const relations = allRelations.filter((relation) => positions.has(endpointKey(relation.source)) && positions.has(endpointKey(relation.target)))
  const rules = allRules.filter((rule) => positions.has(`subject:${String(rule.subject_id)}`) && positions.has(`resource:${String(rule.resource_id)}`))
  return <Space direction="vertical" className="full-width">
    <Space wrap><Select allowClear aria-label="聚焦身份或资源" placeholder="聚焦身份或资源" value={focus} onChange={setFocus} options={nodes.map((node) => ({ value: `${node.type}:${node.id}`, label: `${node.type === 'subject' ? '身份' : '资源'} · ${node.id}` }))} /><Typography.Text type="secondary">当前显示 {visible.length}/{nodes.length} 个节点；实线为关系，虚线为权限规则。</Typography.Text></Space>
    <div className="permission-graph-layout">
      <svg className="permission-graph" role="img" aria-labelledby="permission-graph-title permission-graph-description" viewBox="0 0 560 560">
        <title id="permission-graph-title">权限关系图</title><desc id="permission-graph-description">展示已声明的身份、资源、关系和权限规则。</desc>
        <defs><marker id="permission-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" /></marker></defs>
        {relations.map((relation: Item) => { const from = positions.get(endpointKey(relation.source)); const to = positions.get(endpointKey(relation.target)); return <line key={relation.relation_id} x1={from?.x} y1={from?.y} x2={to?.x} y2={to?.y} className="permission-edge" markerEnd="url(#permission-arrow)" /> })}
        {rules.map((rule, index) => { const from = positions.get(`subject:${String(rule.subject_id)}`); const to = positions.get(`resource:${String(rule.resource_id)}`); return <line key={`${rule.rule_id}-${rule.resource_id}-${index}`} x1={from?.x} y1={from?.y} x2={to?.x} y2={to?.y} className={`permission-rule-edge permission-rule-${String(rule.expectation).toLowerCase()}`} /> })}
        {visible.map((node) => { const key = `${node.type}:${node.id}`; const position = positions.get(key)!; return <g key={key} tabIndex={0} className={`permission-node permission-node-${node.type}`}><circle cx={position.x} cy={position.y} r="15" /><text x={position.x + 22} y={position.y + 5}>{node.id}</text></g> })}
      </svg>
      <div className="permission-graph-lists"><Card size="small" title="完整关系列表"><List size="small" dataSource={allRelations} locale={{ emptyText: '未声明关系' }} renderItem={(relation: Item) => <List.Item><Typography.Text>{label(relation.source?.endpoint_id)} — {label(relation.relation)} → {label(relation.target?.endpoint_id)}</Typography.Text></List.Item>} /></Card><Card size="small" title="完整权限列表"><List size="small" dataSource={allRules} locale={{ emptyText: '未声明权限规则' }} renderItem={(rule: Item) => <List.Item><Typography.Text>{label(rule.subject_id)} — {label(rule.action_id)} / {expectationLabel(rule.expectation)} → {label(rule.resource_id)}</Typography.Text></List.Item>} /></Card></div>
    </div>
  </Space>
}

function ContractView({ contract }: { contract: Item }) {
  return <Tabs items={[{ key: 'matrix', label: '权限矩阵', children: <PermissionMatrix contract={contract} /> }, { key: 'graph', label: '关系图', children: <PermissionGraph contract={contract} /> }]} />
}

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
      {permissionContract && <ContractView contract={permissionContract} />}
      {!permissionContract && governedContracts.length > 0 && <List header={<Typography.Text strong>当前治理规则摘要</Typography.Text>} dataSource={governedContracts.flatMap((item) => Array.isArray(item.rules) ? item.rules.map((rule: Item) => ({ ...rule, contract_id: item.id, contract_version: item.version })) : [])} renderItem={(rule: Item) => <List.Item><Space wrap><Typography.Text code>{label(rule.rule_id ?? rule.id)}</Typography.Text><Typography.Text>{expectationLabel(rule.expectation ?? rule.effect)}</Typography.Text><Collapse ghost items={[{ key: 'governed-rule-tech', label: '规则版本', children: <Typography.Text type="secondary">{label(rule.contract_id)} v{label(rule.contract_version)}</Typography.Text> }]} /></Space></List.Item>} />}
      {!permissionContract && governedContracts.length > 0 && permissionProfiles.length === 0 && <Typography.Paragraph type="secondary">当前治理摘要只返回规则字段，不包含身份、动作、资源和关系实体，因此关系视图不可用。</Typography.Paragraph>}
    </Card>

    <Collapse ghost items={[{ key: 'advanced-governance', label: '高级：规则治理与当前配置', forceRender: true, children: <Space direction="vertical" className="full-width"><Card title="登记 ExecutionProfile"><Typography.Paragraph type="secondary">配置文件仅在本次操作中读取，不会写入浏览器本地存储。</Typography.Paragraph><Input aria-label="ExecutionProfile 文件路径" placeholder="D:\\profiles\\execution-profile.json" value={profilePath} onChange={(event) => setProfilePath(event.target.value)} /><Space wrap><Button loading={profileLoading} onClick={() => void registerProfile()}>登记 ExecutionProfile</Button></Space>{profileMessage && <Alert type={profileMessage.type} showIcon message={profileMessage.text} />}</Card><Card title="新增检查需求"><Form layout="inline" onFinish={addRequirement}><Form.Item name="text" rules={[{ required: true, message: '请输入受控需求模板' }]}><Input placeholder="rule id=foreign-read kind=foreign_read observers=http severity=high" style={{ width: 470 }} /></Form.Item><Form.Item name="tags"><Input placeholder="标签，用逗号分隔" /></Form.Item><Input value={actor} onChange={(event) => setActor(event.target.value)} placeholder="操作者" style={{ width: 130 }} /><Button type="primary" htmlType="submit" loading={loading}>新增需求</Button></Form></Card><Card title="需求与候选" extra={<Button type="primary" disabled={loading || selectedRequirements.length === 0} onClick={() => void derive()}>派生候选</Button>}><Space direction="vertical" className="full-width"><Checkbox.Group value={selectedRequirements} onChange={(value) => setSelectedRequirements(value as string[])} options={requirements.map((item) => ({ label: `${item.requirement_id} · ${item.text}`, value: item.requirement_id }))} /><Select aria-label="模型服务" placeholder="选择模型服务" value={selectedProfile} onChange={setSelectedProfile} options={usableProfiles.map((item) => ({ label: `${item.profile_name} · ${item.provider}`, value: item.profile_name }))} notFoundContent="无可用模型服务" /><Button disabled={!selectedProfile || selectedRequirements.length === 0} onClick={() => void mutate(() => contractsApi.llmCandidates(project.project_id, selectedRequirements, actor, selectedProfile!))}>生成候选</Button><Typography.Text type="secondary">模型只生成待审候选，不能决定安全结论。</Typography.Text>{derivation && <Alert type={blockingIssues.length ? 'error' : 'success'} showIcon message={blockingIssues.length ? '存在阻断问题，本批候选未落盘' : `候选派生完成：${(derivation.persisted_candidates as Item[]).length} 项已落盘`} description={derivationIssues.length ? derivationIssues.map((item) => `${item.severity ?? 'INFO'}:${item.code ?? item.reason_code ?? item.detail}`).join('、') : undefined} />}<List size="small" dataSource={candidates} locale={{ emptyText: '尚无候选' }} renderItem={(item) => <List.Item><Checkbox checked={selectedCandidates.includes(item.candidate_id)} onChange={(event) => setSelectedCandidates((current) => event.target.checked ? [...current, item.candidate_id] : current.filter((id) => id !== item.candidate_id))} />{item.candidate_id} · {item.rule?.id}</List.Item>} /></Space></Card><Card title="规则版本治理"><Typography.Paragraph type="secondary">选择一次 PermissionContract JSON；文件只在本次页面操作中读取，不会写入浏览器本地存储。</Typography.Paragraph><input id="permission-contract-file" type="file" accept="application/json,.json" aria-label="PermissionContract JSON 文件" onChange={(event) => void selectContract(event)} />{contractFileName && <Typography.Paragraph type="secondary">已选择：{contractFileName}</Typography.Paragraph>}{contractFileMessage && <Alert type="warning" showIcon message={contractFileMessage} />}{contractSnapshot && <Descriptions size="small" column={3}><Descriptions.Item label="contract_id">{selectedContractId}</Descriptions.Item><Descriptions.Item label="version">{selectedContractVersion}</Descriptions.Item><Descriptions.Item label="规则数量">{(Array.isArray(contractSnapshot.rules) ? contractSnapshot.rules.length : 0) + (Array.isArray(contractSnapshot.batch_rules) ? contractSnapshot.batch_rules.length : 0)}</Descriptions.Item></Descriptions>}<Space wrap><Button disabled={!canCreateDraft || loading} onClick={() => void mutate(() => contractsApi.createGovernanceContract(project.project_id, contractSnapshot!, selectedCandidates, actor))}>创建草稿</Button><Button disabled={!canReviseActive || loading} onClick={() => void mutate(() => contractsApi.reviseGovernanceContract(project.project_id, contractSnapshot!, selectedCandidates, actor))}>修订已激活规则</Button><Divider /><List size="small" dataSource={versions} locale={{ emptyText: "尚无规则版本" }} renderItem={(version) => <List.Item actions={[version.status === "DRAFT" ? <Button size="small" onClick={() => void transition(version, "submit")}>提交审阅</Button> : null, version.status === "REVIEW" ? <><Button size="small" onClick={() => void transition(version, "activate")}>激活</Button><Button size="small" onClick={() => void transition(version, "reject")}>拒绝</Button></> : null, <Button size="small" onClick={() => void inspect(version, "assessment")}>评估</Button>, <Button size="small" onClick={() => void inspect(version, "drift")}>漂移</Button>, Number(version.version) > 1 ? <Button size="small" onClick={() => void inspect(version, "diff")}>差异</Button> : null].filter(Boolean) as any}><List.Item.Meta title={String(version.contract_id) + " v" + String(version.version) + " · " + String(version.status)} description={"规则 " + (version.snapshot?.rules ?? []).map((rule: Item) => rule.id ?? rule.rule_id).join(", ")} /></List.Item>} />{selectedVersion && analysis && <Card size="small" title={String(selectedVersion.contract_id) + " v" + String(selectedVersion.version) + " 分析结果"}><pre className="report-view">{JSON.stringify(analysis, null, 2)}</pre></Card>}</Space></Card></Space> }]} />
  </Space>
}
