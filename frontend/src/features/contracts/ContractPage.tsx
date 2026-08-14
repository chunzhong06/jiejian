/* =============================================================================
 * 建约页面
 *
 * 定位
 *   Contract Candidate、治理版本、Diff 与 Drift 的用户工作台页面
 *
 * 职责
 *   添加 Requirement｜派生和审阅版本｜激活治理 Contract 并展示分析结果
 *
 * 调用链
 *   ControlShell → ContractPage → contractsApi
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, Descriptions, Divider, Form, Input, List, Select, Space, Tag, Typography } from 'antd'
import { contractsApi } from '../../api/contracts'
import { ApiError } from '../../api/http'
import { LLMProfile } from '../../api/llm'
import { StageGuide } from '../../components/StageGuide'

type Item = Record<string, any>

export function ContractPage({ project, profiles = [], onError, onNext }: { project: Item; profiles?: LLMProfile[]; onError: (e: ApiError) => void; onNext?: () => void }) {
  const [workspace, setWorkspace] = useState<Item | null>(null)
  const [requirements, setRequirements] = useState<Item[]>([])
  const [candidates, setCandidates] = useState<Item[]>([])
  const [versions, setVersions] = useState<Item[]>([])
  const [flowMerge, setFlowMerge] = useState<Item | null>(null)
  const [llmAvailable, setLlmAvailable] = useState(false)
  const [selectedRequirements, setSelectedRequirements] = useState<string[]>([])
  const [selectedProfile, setSelectedProfile] = useState<string>()
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([])
  const [includeFlow, setIncludeFlow] = useState(false)
  const [actor, setActor] = useState('local-user')
  const [contractId, setContractId] = useState('')
  const [selectedVersion, setSelectedVersion] = useState<Item | null>(null)
  const [analysis, setAnalysis] = useState<Item | null>(null)
  const [loading, setLoading] = useState(false)
  const [derivation, setDerivation] = useState<Item | null>(null)
  const [legacyContracts, setLegacyContracts] = useState<Item[]>([])

  const refresh = async () => {
    try {
      const [snapshot, legacy] = await Promise.all([contractsApi.contractGovernance(project.project_id), contractsApi.contracts(project.project_id)])
      const projectRecord = snapshot.project as Item
      setWorkspace(projectRecord)
      setRequirements((snapshot.requirements ?? []) as Item[])
      setCandidates((snapshot.candidates ?? []) as Item[])
      setVersions((snapshot.versions ?? []) as Item[])
      setFlowMerge(snapshot.flow_merge as Item)
      setLlmAvailable(Boolean(snapshot.llm_available))
      setLegacyContracts(legacy)
      if (projectRecord.governed_contract_id && projectRecord.governed_contract_version != null) {
        setContractId(String(projectRecord.governed_contract_id))
      } else {
        setContractId('')
      }
    } catch (error) { onError(error as ApiError) }
  }
  useEffect(() => {
    setSelectedRequirements([])
    setSelectedProfile(undefined)
    setSelectedCandidates([])
    setIncludeFlow(false)
    setDerivation(null)
    setAnalysis(null)
    setSelectedVersion(null)
    setContractId('')
    void refresh()
  }, [project.project_id])

  const mutate = async (operation: () => Promise<unknown>) => {
    setLoading(true)
    try { await operation(); await refresh() } catch (error) { onError(error as ApiError) } finally { setLoading(false) }
  }
  const addRequirement = async (values: { text: string; tags?: string }) => {
    await mutate(async () => {
      await contractsApi.createRequirement(project.project_id, values.text, (values.tags ?? '').split(',').map((item) => item.trim()).filter(Boolean), actor)
    })
  }
  const derive = async () => {
    await mutate(async () => {
      const result = await contractsApi.deriveCandidates(project.project_id, selectedRequirements, includeFlow, actor)
      setDerivation(result)
    })
  }
  const transition = async (version: Item, action: 'submit' | 'reject' | 'activate') => {
    await mutate(() => contractsApi.transitionGovernanceVersion(project.project_id, String(version.contract_id), Number(version.version), action, actor))
  }
  const inspect = async (version: Item, kind: 'assessment' | 'drift' | 'diff') => {
    try {
      setSelectedVersion(version)
      const contract = String(version.contract_id)
      const number = Number(version.version)
      setAnalysis(kind === 'assessment'
        ? await contractsApi.assessment(project.project_id, contract, number)
        : kind === 'drift'
          ? await contractsApi.drift(project.project_id, contract, number)
          : await contractsApi.diff(project.project_id, contract, number, number - 1))
    } catch (error) { onError(error as ApiError) }
  }
  const active = useMemo(() => {
    if (!workspace?.governed_contract_id || workspace.governed_contract_version == null) return undefined
    return versions.find((item) => item.status === 'ACTIVE'
      && item.contract_id === workspace.governed_contract_id
      && Number(item.version) === Number(workspace.governed_contract_version))
  }, [versions, workspace])
  const derivationIssues = [
    ...((derivation?.batches as Item[] | undefined) ?? []).flatMap((batch) => (batch.issues ?? []) as Item[]),
    ...(((derivation?.merge as Item | undefined)?.issues ?? []) as Item[]),
  ]
  const blockingIssues = derivationIssues.filter((issue) => issue.severity === 'BLOCKING')

  const usableProfiles = profiles.filter((item) => item.enabled && item.secret_configured)
  const profileAvailable = usableProfiles.length > 0
  const hasRule = Boolean(active || legacyContracts.some((item) => String(item.status).toUpperCase() === 'ACTIVE'))

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <StageGuide stage="建约" what="确认哪些身份不应访问哪些资源" why="明确规则后，检查结果才有可解释的授权边界" missing={hasRule ? '已有可执行检查规则' : '缺少可执行检查规则'} next={hasRule ? '可以开始一次检查' : '先在高级规则治理中补齐并审阅规则'} onNext={hasRule ? onNext : undefined} nextLabel="去测试" />
      <Card title="检查规则概览" extra={<Space><Tag color={hasRule ? 'green' : 'default'}>{hasRule ? '已有可执行检查规则' : '尚未确认规则'}</Tag><Tag>LLM {llmAvailable || profileAvailable ? '可用' : '离线'}</Tag><Button onClick={() => void refresh()}>刷新</Button></Space>}>
        <Descriptions size="small" column={2}>
          <Descriptions.Item label="当前项目">{workspace?.project_id ?? project.project_id}</Descriptions.Item>
          <Descriptions.Item label="下一步">{hasRule ? '可以开始一次检查' : '展开高级规则治理补齐规则'}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Collapse ghost items={[{ key: 'advanced-governance', label: '高级：规则治理', forceRender: true, children: <Space direction="vertical" style={{ width: '100%' }}><Card title="新增检查需求">
        <Form layout="inline" onFinish={addRequirement}>
          <Form.Item name="text" rules={[{ required: true, message: '请输入受控需求模板' }]}><Input placeholder="rule id=foreign-read kind=foreign_read observers=http severity=high" style={{ width: 470 }} /></Form.Item>
          <Form.Item name="tags"><Input placeholder="标签，用逗号分隔" /></Form.Item>
          <Input value={actor} onChange={(event) => setActor(event.target.value)} placeholder="actor" style={{ width: 130 }} />
          <Button type="primary" htmlType="submit" loading={loading}>新增 Requirement</Button>
        </Form>
      </Card><Card title="Requirement → Candidate" extra={<Button type="primary" disabled={loading || (!includeFlow && selectedRequirements.length === 0)} onClick={() => void derive()}>派生候选</Button>}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Checkbox.Group value={selectedRequirements} onChange={(value) => setSelectedRequirements(value as string[])} options={requirements.map((item) => ({ label: `${item.requirement_id} · ${item.text}`, value: item.requirement_id }))} />
          <Checkbox checked={includeFlow} onChange={(event) => setIncludeFlow(event.target.checked)}>包含当前已校验 Flow（可独立派生）</Checkbox>
          <Select
            aria-label="LLM profile"
            placeholder="选择模型服务 Profile"
            value={selectedProfile}
            onChange={setSelectedProfile}
            options={usableProfiles.map((item) => ({ label: `${item.profile_name} · ${item.provider}`, value: item.profile_name }))}
            style={{ minWidth: 260 }}
            notFoundContent="无可用模型服务，当前离线"
          />
          <Button disabled={!selectedProfile || selectedRequirements.length === 0} onClick={() => void mutate(() => contractsApi.llmCandidates(project.project_id, selectedRequirements, actor, selectedProfile!))}>生成 LLM 候选</Button>
          <Typography.Text type="secondary">LLM 只生成待审候选，不能直接激活契约或决定漏洞结论。</Typography.Text>
          {derivation && <Alert type={blockingIssues.length ? 'error' : 'success'} showIcon message={blockingIssues.length ? '存在阻断问题，本批候选未落盘' : `候选派生完成：${(derivation.persisted_candidates as Item[]).length} 项已落盘`} description={derivationIssues.length ? derivationIssues.map((item) => `${item.severity ?? 'INFO'}:${item.code ?? item.reason_code ?? item.detail}`).join('、') : undefined} />}
          <List size="small" dataSource={candidates} locale={{ emptyText: '尚无 Candidate' }} renderItem={(item) => <List.Item><Checkbox value={item.candidate_id} checked={selectedCandidates.includes(item.candidate_id)} onChange={(event) => setSelectedCandidates((current) => event.target.checked ? [...current, item.candidate_id] : current.filter((id) => id !== item.candidate_id))} /><Typography.Text>{item.candidate_id} · {item.rule?.id} · {item.source?.source_type}</Typography.Text></List.Item>} />
          {flowMerge && <Typography.Text type="secondary">当前 Flow 合并摘要：{(flowMerge.candidates ?? []).length} 项，{(flowMerge.issues ?? []).length} 个问题</Typography.Text>}
        </Space>
      </Card>

      <Card title="Contract Version 治理">
        <Space wrap>
          <Input value={contractId} onChange={(event) => setContractId(event.target.value)} placeholder="contract_id" style={{ width: 220 }} />
          <Button disabled={!contractId || !selectedCandidates.length} onClick={() => void mutate(() => contractsApi.createGovernanceContract(project.project_id, contractId, selectedCandidates, actor))}>创建 DRAFT</Button>
          <Button disabled={!active || !selectedCandidates.length} onClick={() => void mutate(() => contractsApi.reviseGovernanceContract(project.project_id, String(active?.contract_id), selectedCandidates, actor))}>修订 ACTIVE</Button>
        </Space>
        <Divider />
        <List size="small" dataSource={versions} locale={{ emptyText: '尚无 Contract Version' }} renderItem={(version) => <List.Item actions={[
          version.status === 'DRAFT' ? <Button size="small" onClick={() => void transition(version, 'submit')}>提交审阅</Button> : null,
          version.status === 'REVIEW' ? <><Button size="small" onClick={() => void transition(version, 'activate')}>激活</Button><Button size="small" onClick={() => void transition(version, 'reject')}>拒绝</Button></> : null,
          <Button size="small" onClick={() => void inspect(version, 'assessment')}>assessment</Button>,
          <Button size="small" onClick={() => void inspect(version, 'drift')}>drift</Button>,
          Number(version.version) > 1 ? <Button size="small" onClick={() => void inspect(version, 'diff')}>diff</Button> : null,
        ].filter(Boolean) as any}><List.Item.Meta title={`${version.contract_id} v${version.version} · ${version.status}`} description={`规则 ${(version.snapshot?.rules ?? []).map((rule: Item) => rule.id).join(', ')}`} /></List.Item>} />
        {selectedVersion && analysis && <Card size="small" title={`${selectedVersion.contract_id} v${selectedVersion.version} 分析结果`}><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(analysis, null, 2)}</pre></Card>}
      </Card>

      <Card title="兼容：显式 Contract 文件">
        <Form layout="inline" onFinish={({ path }) => void mutate(() => contractsApi.activateContract(project.project_id, path))}>
          <Form.Item name="path" rules={[{ required: true, message: '请输入显式 Contract 路径' }]}><Input placeholder="D:\\demo\\contract.yaml" style={{ width: 420 }} /></Form.Item>
          <Button htmlType="submit">激活 YAML</Button>
        </Form>
        <List size="small" dataSource={legacyContracts} renderItem={(item) => <List.Item><List.Item.Meta title={`${item.id} v${item.version}`} description={String(item.path)} /><Tag color="blue">{String(item.status)}</Tag></List.Item>} />
      </Card></Space> }]} />
    </Space>
  )
}

export default ContractPage
