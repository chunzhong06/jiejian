/* 权限规则高级治理：独立承载需求、候选、版本流转和只读分析。 */

import { useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from 'react'
import { Alert, Button, Card, Checkbox, Descriptions, Divider, Form, Input, List, Space, Typography } from 'antd'
import {
  contractsApi,
  type CandidateDerivationDto,
  type GovernanceAnalysisDto,
  type GovernanceCandidateDto,
  type GovernanceRequirementDto,
  type GovernanceVersionDto,
  type PermissionContractDto,
} from '../../../api/contracts'
import { executionProfilesApi } from '../../../api/executionProfiles'
import { ApiError } from '../../../api/http'
import type { ProjectDto } from '../../../api/projects'
import { productStatusLabel } from '../../../app/presentation'

const MAX_PERMISSION_CONTRACT_BYTES = 1024 * 1024

export function PermissionGovernancePanel({ project, onError, onChanged }: {
  project: ProjectDto
  onError: (error: ApiError) => void
  onChanged?: () => void
}) {
  const [requirements, setRequirements] = useState<GovernanceRequirementDto[]>([])
  const [candidates, setCandidates] = useState<GovernanceCandidateDto[]>([])
  const [versions, setVersions] = useState<GovernanceVersionDto[]>([])
  const [workspace, setWorkspace] = useState<{ governed_contract_id?: string | null; governed_contract_version?: number | null }>({})
  const [selectedRequirements, setSelectedRequirements] = useState<string[]>([])
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>([])
  const [actor, setActor] = useState('local-user')
  const [selectedVersion, setSelectedVersion] = useState<GovernanceVersionDto | null>(null)
  const [analysis, setAnalysis] = useState<GovernanceAnalysisDto | null>(null)
  const [loading, setLoading] = useState(false)
  const [derivation, setDerivation] = useState<CandidateDerivationDto | null>(null)
  const [profilePath, setProfilePath] = useState('')
  const [profileLoading, setProfileLoading] = useState(false)
  const [profileMessage, setProfileMessage] = useState<{ type: 'success' | 'info' | 'warning'; text: string } | null>(null)
  const [contractFileName, setContractFileName] = useState('')
  const [contractSnapshot, setContractSnapshot] = useState<PermissionContractDto | null>(null)
  const [contractFileMessage, setContractFileMessage] = useState<string | null>(null)

  const refresh = async () => {
    try {
      const snapshot = await contractsApi.contractGovernance(project.project_id)
      setWorkspace(snapshot.project ?? {})
      setRequirements(snapshot.requirements ?? [])
      setCandidates(snapshot.candidates ?? [])
      setVersions(snapshot.versions ?? [])
    } catch (error) { onError(error as ApiError) }
  }

  useEffect(() => {
    setSelectedRequirements([])
    setSelectedCandidates([])
    setDerivation(null)
    setSelectedVersion(null)
    setContractFileName('')
    setContractSnapshot(null)
    setContractFileMessage(null)
    void refresh()
  }, [project.project_id])

  const mutate = async (operation: () => Promise<unknown>) => {
    setLoading(true)
    try { await operation(); await refresh(); onChanged?.() }
    catch (error) { onError(error as ApiError) }
    finally { setLoading(false) }
  }
  const addRequirement = async (values: { text: string; tags?: string }) => mutate(() => contractsApi.createRequirement(project.project_id, values.text, (values.tags ?? '').split(',').map((item) => item.trim()).filter(Boolean), actor))
  const derive = async () => mutate(async () => setDerivation(await contractsApi.deriveCandidates(project.project_id, selectedRequirements, actor)))
  const transition = async (version: GovernanceVersionDto, action: 'submit' | 'reject' | 'activate') => mutate(() => contractsApi.transitionGovernanceVersion(project.project_id, version.contract_id, version.version, action, actor))
  const inspect = async (version: GovernanceVersionDto, kind: 'assessment' | 'drift' | 'diff') => {
    try {
      setSelectedVersion(version)
      setAnalysis(kind === 'assessment'
        ? await contractsApi.assessment(project.project_id, version.contract_id, version.version)
        : kind === 'drift'
          ? await contractsApi.drift(project.project_id, version.contract_id, version.version)
          : await contractsApi.diff(project.project_id, version.contract_id, version.version, version.version - 1))
    } catch (error) { onError(error as ApiError) }
  }
  const registerProfile = async () => {
    const path = profilePath.trim()
    if (!path) { setProfileMessage({ type: 'warning', text: '请输入当前 Web 执行配置的文件路径。' }); return }
    setProfileLoading(true)
    try {
      const record = await executionProfilesApi.register(path)
      setProfileMessage(record.project_id === project.project_id
        ? { type: 'success', text: '配置已登记。' }
        : { type: 'warning', text: `配置属于其他应用（${record.project_id}），与当前应用不一致。` })
      onChanged?.()
    } catch (error) { onError(error as ApiError) }
    finally { setProfileLoading(false) }
  }
  const selectContract = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    setContractFileName(file?.name ?? '')
    setContractSnapshot(null)
    setContractFileMessage(null)
    if (!file) return
    if (file.size > MAX_PERMISSION_CONTRACT_BYTES) { setContractFileMessage('权限契约文件过大，请选择不超过 1 MB 的 JSON 文件。'); return }
    try {
      const parsed = JSON.parse(await file.text()) as Partial<PermissionContractDto>
      if (typeof parsed.contract_id !== 'string' || !parsed.contract_id || !Number.isInteger(parsed.version)) throw new Error('invalid-preview')
      setContractSnapshot(parsed as PermissionContractDto)
    } catch {
      setContractFileMessage('无法读取权限契约 JSON（PermissionContract），请确认文件包含有效的 contract_id、version 和完整契约内容。')
    }
  }

  const active = useMemo(() => versions.find((item) => item.status === 'ACTIVE' && item.contract_id === workspace.governed_contract_id && item.version === workspace.governed_contract_version), [versions, workspace])
  const selectedContractId = contractSnapshot?.contract_id ?? ''
  const selectedContractVersion = Number(contractSnapshot?.version)
  const canCreateDraft = Boolean(contractSnapshot && Number.isInteger(selectedContractVersion) && selectedContractVersion === 1 && !versions.some((item) => item.contract_id === selectedContractId))
  const canReviseActive = Boolean(contractSnapshot && active && selectedContractId === active.contract_id && selectedContractVersion === active.version + 1)
  const derivationIssues = [...(derivation?.batches ?? []).flatMap((batch) => batch.issues ?? []), ...(derivation?.merge?.issues ?? [])]
  const blockingIssues = derivationIssues.filter((issue) => issue.severity === 'BLOCKING')
  return <Space direction="vertical" size="large" className="full-width governance-panel">
    <Card className="governance-form-card" title="登记 Web 执行配置"><Typography.Paragraph type="secondary">Web 执行配置文件仅在本次操作中读取，不会写入浏览器本地存储。</Typography.Paragraph><Input aria-label="Web 执行配置文件路径" placeholder="D:\\profiles\\web-execution-profile.json" value={profilePath} onChange={(event) => setProfilePath(event.target.value)} /><Space wrap><Button loading={profileLoading} onClick={() => void registerProfile()}>登记执行配置</Button></Space>{profileMessage && <Alert type={profileMessage.type} showIcon message={profileMessage.text} />}</Card>
    <Card className="governance-form-card" title="新增检查需求"><Form layout="inline" className="governance-requirement-form" onFinish={addRequirement}><Form.Item name="text" rules={[{ required: true, message: '请输入受控需求模板' }]}><Input placeholder="rule id=foreign-read kind=foreign_read observers=http severity=high" /></Form.Item><Form.Item name="tags"><Input placeholder="标签，用逗号分隔" /></Form.Item><Input aria-label="操作者" value={actor} onChange={(event) => setActor(event.target.value)} placeholder="操作者" /><Button type="primary" htmlType="submit" loading={loading}>新增需求</Button></Form></Card>
    <Card title="需求与候选" extra={<Button type="primary" disabled={loading || selectedRequirements.length === 0} onClick={() => void derive()}>派生候选</Button>}><Space direction="vertical" className="full-width"><Typography.Text type="secondary">候选只从已选择需求做确定性派生，仍需人工审阅后才能进入规则版本。</Typography.Text><Checkbox.Group value={selectedRequirements} onChange={(value) => setSelectedRequirements(value as string[])} options={requirements.map((item) => ({ label: `${item.requirement_id} · ${item.text}`, value: item.requirement_id }))} />{derivation && <Alert type={blockingIssues.length ? 'error' : 'success'} showIcon message={blockingIssues.length ? '存在阻断问题，本批候选未落盘' : `候选派生完成：${derivation.persisted_candidates?.length ?? 0} 项已落盘`} description={derivationIssues.length ? derivationIssues.map((item) => `${item.severity ?? 'INFO'}:${item.code ?? item.reason_code ?? item.detail}`).join('、') : undefined} />}<List size="small" dataSource={candidates} locale={{ emptyText: '尚无候选' }} renderItem={(item) => <List.Item><Checkbox checked={selectedCandidates.includes(item.candidate_id)} onChange={(event) => setSelectedCandidates((current) => event.target.checked ? [...current, item.candidate_id] : current.filter((id) => id !== item.candidate_id))} />{item.candidate_id} · {item.rule?.id ?? item.rule?.rule_id}</List.Item>} /></Space></Card>
    <Card title="规则版本治理"><Space direction="vertical" className="full-width" size="middle"><Typography.Paragraph type="secondary">选择一次权限契约 JSON（PermissionContract）；文件只在本次页面操作中读取，不会写入浏览器本地存储。</Typography.Paragraph><input id="permission-contract-file" type="file" accept="application/json,.json" aria-label="权限契约 JSON 文件" onChange={(event) => void selectContract(event)} />{contractFileName && <Typography.Paragraph type="secondary">已选择：{contractFileName}</Typography.Paragraph>}{contractFileMessage && <Alert type="warning" showIcon message={contractFileMessage} />}{contractSnapshot && <Descriptions size="small" column={3}><Descriptions.Item label="契约标识（contract_id）">{selectedContractId}</Descriptions.Item><Descriptions.Item label="版本（version）">{selectedContractVersion}</Descriptions.Item><Descriptions.Item label="规则数量">{(contractSnapshot.rules?.length ?? 0) + (contractSnapshot.batch_rules?.length ?? 0)}</Descriptions.Item></Descriptions>}<Space wrap><Button disabled={!canCreateDraft || loading} onClick={() => contractSnapshot && void mutate(() => contractsApi.createGovernanceContract(project.project_id, contractSnapshot, selectedCandidates, actor))}>创建草稿</Button><Button disabled={!canReviseActive || loading} onClick={() => contractSnapshot && void mutate(() => contractsApi.reviseGovernanceContract(project.project_id, contractSnapshot, selectedCandidates, actor))}>修订已激活规则</Button></Space><Divider /><List className="governance-version-list" size="small" dataSource={versions} locale={{ emptyText: '尚无规则版本' }} renderItem={(version) => <List.Item className="governance-version-item" actions={[version.status === 'DRAFT' ? <Button size="small" onClick={() => void transition(version, 'submit')}>提交审阅</Button> : null, version.status === 'REVIEW' ? <><Button size="small" onClick={() => void transition(version, 'activate')}>激活</Button><Button size="small" onClick={() => void transition(version, 'reject')}>拒绝</Button></> : null, <Button size="small" onClick={() => void inspect(version, 'assessment')}>评估</Button>, <Button size="small" onClick={() => void inspect(version, 'drift')}>漂移</Button>, version.version > 1 ? <Button size="small" onClick={() => void inspect(version, 'diff')}>差异</Button> : null].filter(Boolean) as ReactNode[]}><List.Item.Meta title={`${version.contract_id} v${version.version} · ${productStatusLabel('contract', version.status)}`} description={`规则 ${(version.snapshot?.rules ?? []).map((rule) => rule.id ?? rule.rule_id).join('、')}`} /></List.Item>} />{selectedVersion && analysis && <Card size="small" title={`${selectedVersion.contract_id} v${selectedVersion.version} 分析结果`}><pre className="report-view">{JSON.stringify(analysis, null, 2)}</pre></Card>}</Space></Card>
  </Space>
}
