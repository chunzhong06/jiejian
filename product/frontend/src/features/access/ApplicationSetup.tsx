/* =============================================================================
 * 普通应用接入向导
 *
 * 定位
 *   目录选择、IPv4 loopback 地址确认、源码分析授权和候选审阅组成的默认用户路径
 *
 * 职责
 *   恢复后端理解事实｜引导显式授权｜提交权限组与业务动作人工决定
 *
 * 边界
 *   候选不是权限结论；本组件不收集 Profile、资源 ID、恢复路径或测试凭据。
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Checkbox, Collapse, Input, List, Radio, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { onboardingApi, type DiscoveryResult } from '../../api/onboarding'
import { AssistantPanel } from '../../components/AssistantPanel'
import { TaskActionBar } from '../../components/TaskActionBar'
import {
  projectsApi,
  type ActionCandidateDto,
  type ApplicationUnderstandingDto,
  type EndpointDiscoveryDto,
  type ProjectDto,
  type ProjectReadinessDto,
  type RoleCandidateDto,
} from '../../api/projects'

const FOLDER_SELECTOR_TIMEOUT_MS = 125_000

type SetupError = { message: string; code?: string }
type CandidateDecision = 'PROPOSED' | 'CONFIRMED' | 'REJECTED'

function setupError(error: unknown, fallback: string): SetupError {
  return error instanceof ApiError ? { message: error.message, code: error.code } : { message: fallback }
}

function evidenceLabel(candidate: RoleCandidateDto | ActionCandidateDto) {
  const evidence = candidate.evidence[0]
  if (!evidence) return candidate.origin === 'MANUAL' ? '由你手工补充' : '暂无结构证据'
  return `${evidence.relative_path}:${evidence.line_start}`
}

function confidenceLabel(value: RoleCandidateDto['confidence']) {
  return value === 'HIGH' ? '高可信' : value === 'MEDIUM' ? '中等可信' : '可能还有'
}

function CandidateRow({ candidate, kind, loading, onDecide }: {
  candidate: RoleCandidateDto | ActionCandidateDto
  kind: 'role' | 'action'
  loading: boolean
  onDecide: (decision: CandidateDecision, displayName: string) => void
}) {
  const [displayName, setDisplayName] = useState(candidate.display_name)
  useEffect(() => setDisplayName(candidate.display_name), [candidate.candidate_id, candidate.display_name])
  const action = kind === 'action' ? candidate as ActionCandidateDto : null
  const noun = kind === 'role' ? '权限组' : '业务动作'
  const riskLabels: Record<ActionCandidateDto['risk_hint'], string> = {
    READ: '读取提示', WRITE: '写入提示', DELETE: '删除提示', ADMIN: '管理提示', UNKNOWN: '待判断',
  }
  return <List.Item className="candidate-row">
    <div className="candidate-main">
      <Space wrap>
        <Tag color="blue">系统发现</Tag>
        <Tag color={candidate.confidence === 'HIGH' ? 'blue' : candidate.confidence === 'MEDIUM' ? 'cyan' : 'default'}>{confidenceLabel(candidate.confidence)}</Tag>
        {candidate.stale && <Tag color="orange">源码中未再次发现，请复核</Tag>}
        {action && <Tag color="gold">{riskLabels[action.risk_hint]}</Tag>}
      </Space>
      <Input aria-label={`${noun}显示名称`} value={displayName} maxLength={kind === 'role' ? 128 : 256} onChange={(event) => setDisplayName(event.target.value)} />
      <Space wrap>
        <Button type="primary" size="small" loading={loading} disabled={!displayName.trim()} onClick={() => onDecide('CONFIRMED', displayName)}>确认这个{noun}</Button>
        <Button size="small" loading={loading} onClick={() => onDecide('REJECTED', displayName)}>不是{noun}</Button>
      </Space>
      <Typography.Text type="secondary">识别依据：{evidenceLabel(candidate)}{candidate.evidence[0]?.symbol ? ` · ${candidate.evidence[0].symbol}` : ''}</Typography.Text>
    </div>
  </List.Item>
}

function ConfirmedCandidateRow({ candidate, kind, loading, onDecide }: {
  candidate: RoleCandidateDto | ActionCandidateDto
  kind: 'role' | 'action'
  loading: boolean
  onDecide: (decision: CandidateDecision, displayName: string) => void
}) {
  const noun = kind === 'role' ? '权限组' : '业务动作'
  return <List.Item className="candidate-row candidate-row-confirmed">
    <div className="candidate-main">
      <Space wrap><Typography.Text type="secondary">已确认</Typography.Text><Typography.Text type="secondary">{candidate.origin === 'MANUAL' ? '手工补充' : '系统发现'}</Typography.Text></Space>
      <Typography.Text strong className="candidate-title">{candidate.display_name}</Typography.Text>
      <div><Button size="small" loading={loading} onClick={() => onDecide('REJECTED', candidate.display_name)}>排除这个{noun}</Button></div>
    </div>
  </List.Item>
}

function ExcludedCandidateRow({ candidate, kind, loading, onDecide }: {
  candidate: RoleCandidateDto | ActionCandidateDto
  kind: 'role' | 'action'
  loading: boolean
  onDecide: (decision: CandidateDecision, displayName: string) => void
}) {
  const noun = kind === 'role' ? '权限组' : '业务动作'
  return <List.Item className="candidate-row candidate-row-excluded">
    <div className="candidate-main">
      <Space wrap><Typography.Text type="secondary">已排除</Typography.Text><Typography.Text type="secondary">{candidate.origin === 'MANUAL' ? '手工补充' : `系统发现的${noun}`}</Typography.Text></Space>
      <Typography.Text className="candidate-title">{candidate.display_name}</Typography.Text>
      <Space wrap>
        <Button size="small" loading={loading} onClick={() => onDecide('CONFIRMED', candidate.display_name)}>恢复为已确认</Button>
        {candidate.origin === 'DETECTED' && <Button type="text" size="small" loading={loading} onClick={() => onDecide('PROPOSED', candidate.display_name)}>移回待确认</Button>}
      </Space>
      <Typography.Text type="secondary">识别依据：{evidenceLabel(candidate)}</Typography.Text>
    </div>
  </List.Item>
}

function CandidateSection({ title, candidates, kind, variant, loading, onDecide, emptyText }: {
  title: string
  candidates: Array<RoleCandidateDto | ActionCandidateDto>
  kind: 'role' | 'action'
  variant: 'confirmed' | 'pending'
  loading: boolean
  onDecide: (candidate: RoleCandidateDto | ActionCandidateDto, decision: CandidateDecision, displayName: string) => void
  emptyText: string
}) {
  return <section className={`candidate-section candidate-section-${variant}`}>
    <div className="candidate-section-heading">
      <Typography.Title level={5}>{title}</Typography.Title>
      <Tag>{candidates.length} 项</Tag>
    </div>
    <List dataSource={candidates} locale={{ emptyText }} renderItem={(candidate) => variant === 'confirmed'
      ? <ConfirmedCandidateRow key={candidate.candidate_id} candidate={candidate} kind={kind} loading={loading} onDecide={(decision, name) => onDecide(candidate, decision, name)} />
      : <CandidateRow key={candidate.candidate_id} candidate={candidate} kind={kind} loading={loading} onDecide={(decision, name) => onDecide(candidate, decision, name)} />} />
  </section>
}

export function ApplicationSetup({ selected, endpointStatus, onConnected, onChanged, onBack, onContinue }: {
  selected: ProjectDto | null
  endpointStatus?: ProjectReadinessDto['endpoint_status']
  onConnected: (project: ProjectDto) => void
  onChanged: () => void
  onBack: () => void
  onContinue: () => void
}) {
  const [understanding, setUnderstanding] = useState<ApplicationUnderstandingDto | null>(null)
  const [discovery, setDiscovery] = useState<DiscoveryResult | null>(null)
  const [endpoints, setEndpoints] = useState<EndpointDiscoveryDto | null>(null)
  const [manualPath, setManualPath] = useState('')
  const [endpoint, setEndpoint] = useState('')
  const [endpointConfirmed, setEndpointConfirmed] = useState(false)
  const [appRunningConfirmed, setAppRunningConfirmed] = useState(false)
  const [analysisAuthorized, setAnalysisAuthorized] = useState(false)
  const [manualRole, setManualRole] = useState('')
  const [manualAction, setManualAction] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState<SetupError | null>(null)

  const applyUnderstanding = (value: ApplicationUnderstandingDto) => {
    setUnderstanding(value)
    if (value.confirmed_endpoint) setEndpoint(value.confirmed_endpoint)
  }

  const loadEndpoints = async (projectId: string) => {
    const result = await projectsApi.discoverEndpoints(projectId)
    setEndpoints(result)
    setEndpoint(result.default_endpoint ?? result.candidates.find((item) => item.reachable)?.endpoint ?? '')
  }

  useEffect(() => {
    if (!selected?.project_id) {
      setUnderstanding(null)
      setEndpoints(null)
      return
    }
    let active = true
    void projectsApi.understanding(selected.project_id).then(async (value) => {
      if (!active) return
      applyUnderstanding(value)
      if (!value.confirmed_endpoint || (endpointStatus !== undefined && endpointStatus !== 'CONFIRMED')) await loadEndpoints(selected.project_id)
    }).catch((loadError) => {
      if (active && (!(loadError instanceof ApiError) || loadError.code !== 'APPLICATION_UNDERSTANDING_NOT_FOUND')) {
        setError(setupError(loadError, '无法恢复应用理解状态。'))
      }
    })
    return () => { active = false }
  }, [selected?.project_id, endpointStatus])

  const connectPath = async (sourcePath: string) => {
    if (!sourcePath.trim()) return
    setLoading(true); setError(null); setMessage('')
    try {
      const connected = await projectsApi.connectApplication(sourcePath.trim())
      applyUnderstanding(connected.understanding)
      setDiscovery(connected.discovery)
      onConnected(connected.project)
      await loadEndpoints(connected.project.project_id)
      setMessage('应用目录已连接。请选择界鉴找到的本地地址，或使用手工输入。')
    } catch (connectError) {
      setError(setupError(connectError, '连接应用目录失败，请确认路径存在且可读取。'))
    } finally { setLoading(false) }
  }

  const chooseFolder = async () => {
    setLoading(true); setError(null); setMessage('目录选择器已打开，请在系统窗口中完成选择。')
    const controller = new AbortController()
    const timeout = globalThis.setTimeout(() => controller.abort(), FOLDER_SELECTOR_TIMEOUT_MS)
    try {
      const result = await onboardingApi.selectFolder(controller.signal)
      if (result.status === 'selected' && result.path) await connectPath(result.path)
      else setMessage(result.message ?? (result.status === 'cancelled' ? '已取消选择。' : '目录选择器不可用，请手工输入绝对路径。'))
    } catch (chooseError) {
      setError(chooseError instanceof DOMException && chooseError.name === 'AbortError'
        ? { message: '目录选择器等待超时，请重试或手工输入绝对路径。' }
        : setupError(chooseError, '目录选择器失败，请手工输入绝对路径。'))
    } finally {
      globalThis.clearTimeout(timeout)
      setLoading(false)
    }
  }

  const confirmEndpoint = async () => {
    if (!understanding || !appRunningConfirmed || !endpointConfirmed || !endpoint.trim()) return
    setLoading(true); setError(null)
    try {
      const value = await projectsApi.confirmEndpoint(understanding.project_id, endpoint.trim(), understanding.revision)
      applyUnderstanding(value); setEndpoints(null); setEndpointConfirmed(false); setAppRunningConfirmed(false); onChanged()
    } catch (confirmError) { setError(setupError(confirmError, '确认本地地址失败。')) } finally { setLoading(false) }
  }

  const authorizeAndAnalyze = async () => {
    if (!understanding || !analysisAuthorized) return
    setLoading(true); setError(null)
    try {
      const authorized = understanding.source_analysis_authorized
        ? understanding
        : await projectsApi.authorizeSourceAnalysis(understanding.project_id, understanding.revision)
      applyUnderstanding(authorized)
      const analyzed = await projectsApi.analyzeSource(authorized.project_id, authorized.revision)
      applyUnderstanding(analyzed); setAnalysisAuthorized(false); onChanged()
    } catch (analysisError) { setError(setupError(analysisError, '分析权限组与关键业务动作失败。')) } finally { setLoading(false) }
  }

  const reanalyze = async () => {
    if (!understanding?.source_analysis_authorized) return
    setLoading(true); setError(null); setMessage('')
    try {
      const analyzed = await projectsApi.analyzeSource(understanding.project_id, understanding.revision)
      applyUnderstanding(analyzed); onChanged()
      setMessage('已按当前源码重新发现权限组和业务动作，请继续确认候选。')
    } catch (analysisError) { setError(setupError(analysisError, '重新分析权限组与关键业务动作失败。')) } finally { setLoading(false) }
  }

  const decide = async (kind: 'role' | 'action', candidate: RoleCandidateDto | ActionCandidateDto, decision: CandidateDecision, displayName: string) => {
    if (!understanding) return
    setLoading(true); setError(null)
    try {
      const value = kind === 'role'
        ? await projectsApi.decideRole(understanding.project_id, candidate.candidate_id, decision, displayName, understanding.revision)
        : await projectsApi.decideAction(understanding.project_id, candidate.candidate_id, decision, displayName, understanding.revision)
      applyUnderstanding(value); onChanged()
    } catch (decisionError) { setError(setupError(decisionError, '保存候选决定失败。')) } finally { setLoading(false) }
  }

  const addRole = async () => {
    if (!understanding || !manualRole.trim()) return
    setLoading(true); setError(null)
    try {
      applyUnderstanding(await projectsApi.addRole(understanding.project_id, manualRole, understanding.revision))
      setManualRole(''); onChanged()
    } catch (addError) { setError(setupError(addError, '补充权限组失败。')) } finally { setLoading(false) }
  }

  const addAction = async () => {
    if (!understanding || !manualAction.trim()) return
    setLoading(true); setError(null)
    try {
      applyUnderstanding(await projectsApi.addAction(understanding.project_id, manualAction, 'UNKNOWN', understanding.revision))
      setManualAction(''); onChanged()
    } catch (addError) { setError(setupError(addError, '补充业务动作失败。')) } finally { setLoading(false) }
  }

  const refreshUnderstanding = async () => {
    if (!understanding) return
    setLoading(true); setError(null); setMessage('')
    try {
      applyUnderstanding(await projectsApi.understanding(understanding.project_id))
      onChanged()
      setMessage('已读取当前应用的最新准备状态。')
    } catch (refreshError) { setError(setupError(refreshError, '刷新应用准备状态失败。')) } finally { setLoading(false) }
  }

  // 地址是否仍可信由后端 Readiness 实时裁决；历史上保存过地址不能跳过重新确认。
  const endpointReady = endpointStatus === undefined ? Boolean(understanding?.confirmed_endpoint) : endpointStatus === 'CONFIRMED'
  const currentStep = !understanding ? 1 : !endpointReady ? 2 : !understanding.source_fingerprint ? 3 : 4
  const reviewComplete = Boolean(understanding?.role_candidates.some((candidate) => candidate.decision === 'CONFIRMED' && !candidate.stale)
    && understanding.action_candidates.some((candidate) => candidate.decision === 'CONFIRMED' && !candidate.stale))
  const sequence = ['选择应用目录', '确认本地地址', '授权只读分析', '审阅权限组和业务动作']
  const primaryAction = currentStep === 1
    ? { label: '选择应用文件夹', onClick: () => void chooseFolder(), loading }
    : currentStep === 2
      ? { label: '确认本地地址', onClick: () => void confirmEndpoint(), loading, disabled: !endpoint.trim() || !appRunningConfirmed || !endpointConfirmed }
      : currentStep === 3
        ? { label: understanding?.source_analysis_authorized ? '重新开始分析' : '授权并开始分析', onClick: () => void authorizeAndAnalyze(), loading, disabled: !analysisAuthorized }
        : { label: reviewComplete ? '继续准备测试账号' : '确认权限组和业务动作后继续', onClick: onContinue, disabled: !reviewComplete }

  const candidateReview = endpointReady && understanding?.source_fingerprint ? <Card className="application-step" title="确认权限组与业务动作">
    <Alert type="info" showIcon message="这些是系统发现的权限组和业务动作候选，不是权限结论" description="确认候选只表示应用中存在这个权限组或业务动作；界鉴不会据此自动判断谁应该允许或拒绝什么操作。" />
    <AssistantPanel projectId={understanding.project_id} surface="candidate-review" title="候选整理建议" actionLabel="AI 帮我整理" />
    <section className="candidate-review-block" aria-labelledby="permission-group-review-title">
      <div className="candidate-review-heading">
        <Typography.Title level={4} id="permission-group-review-title">权限组</Typography.Title>
        <Typography.Text type="secondary">确认应用中真实存在的用户类别；这里不设置允许或拒绝规则。</Typography.Text>
      </div>
      <CandidateSection title="已确认的权限组" candidates={understanding.role_candidates.filter((candidate) => candidate.decision === 'CONFIRMED' && !candidate.stale)} kind="role" variant="confirmed" loading={loading} onDecide={(candidate, decision, name) => void decide('role', candidate, decision, name)} emptyText="还没有已确认的权限组。" />
      <CandidateSection title="系统发现，等待确认" candidates={understanding.role_candidates.filter((candidate) => candidate.decision !== 'REJECTED' && (candidate.decision !== 'CONFIRMED' || candidate.stale))} kind="role" variant="pending" loading={loading} onDecide={(candidate, decision, name) => void decide('role', candidate, decision, name)} emptyText="没有待确认的系统权限组。" />
      <section className="application-manual-section"><Typography.Title level={5}>没有找到？手工补充</Typography.Title><div className="application-manual"><Input aria-label="手工补充权限组" value={manualRole} onChange={(event) => setManualRole(event.target.value)} placeholder="例如：审核员" /><Button onClick={() => void addRole()} disabled={!manualRole.trim()} loading={loading}>补充并确认权限组</Button></div></section>
      {understanding.role_candidates.some((candidate) => candidate.decision === 'REJECTED') && <Collapse ghost items={[{ key: 'excluded-roles', label: `已排除的候选（${understanding.role_candidates.filter((candidate) => candidate.decision === 'REJECTED').length}）`, children: <List dataSource={understanding.role_candidates.filter((candidate) => candidate.decision === 'REJECTED')} renderItem={(candidate) => <ExcludedCandidateRow key={candidate.candidate_id} candidate={candidate} kind="role" loading={loading} onDecide={(decision, name) => void decide('role', candidate, decision, name)} />} /> }]} />}
    </section>
    <section className="candidate-review-block" aria-labelledby="business-action-review-title">
      <div className="candidate-review-heading">
        <Typography.Title level={4} id="business-action-review-title">业务动作</Typography.Title>
        <Typography.Text type="secondary">确认需要测试的真实操作；录制与权限预期会在后续步骤单独完成。</Typography.Text>
      </div>
      <CandidateSection title="已确认的业务动作" candidates={understanding.action_candidates.filter((candidate) => candidate.decision === 'CONFIRMED' && !candidate.stale)} kind="action" variant="confirmed" loading={loading} onDecide={(candidate, decision, name) => void decide('action', candidate, decision, name)} emptyText="还没有已确认的业务动作。" />
      <CandidateSection title="系统发现，等待确认" candidates={understanding.action_candidates.filter((candidate) => candidate.decision !== 'REJECTED' && (candidate.decision !== 'CONFIRMED' || candidate.stale))} kind="action" variant="pending" loading={loading} onDecide={(candidate, decision, name) => void decide('action', candidate, decision, name)} emptyText="没有待确认的系统业务动作。" />
      <section className="application-manual-section"><Typography.Title level={5}>没有找到？手工补充</Typography.Title><div className="application-manual"><Input aria-label="手工补充业务动作" value={manualAction} onChange={(event) => setManualAction(event.target.value)} placeholder="例如：批准退款" /><Button onClick={() => void addAction()} disabled={!manualAction.trim()} loading={loading}>补充并确认业务动作</Button></div></section>
      {understanding.action_candidates.some((candidate) => candidate.decision === 'REJECTED') && <Collapse ghost items={[{ key: 'excluded-actions', label: `已排除的候选（${understanding.action_candidates.filter((candidate) => candidate.decision === 'REJECTED').length}）`, children: <List dataSource={understanding.action_candidates.filter((candidate) => candidate.decision === 'REJECTED')} renderItem={(candidate) => <ExcludedCandidateRow key={candidate.candidate_id} candidate={candidate} kind="action" loading={loading} onDecide={(decision, name) => void decide('action', candidate, decision, name)} />} /> }]} />}
    </section>
  </Card> : null

  return <div className="application-setup">
    <ol className="task-sequence" aria-label="应用接入进度">
      {sequence.map((label, index) => {
        const step = index + 1
        const state = step < currentStep ? 'complete' : step === currentStep ? 'current' : 'upcoming'
        return <li key={label} className={`task-sequence-step is-${state}`}><span>{step < currentStep ? '✓' : step}</span><div><strong>{label}</strong><small>{state === 'complete' ? '已完成' : state === 'current' ? '当前任务' : '随后进行'}</small></div></li>
      })}
    </ol>
    {message && <Alert showIcon type="info" message={message} closable onClose={() => setMessage('')} />}
    {error && <Alert showIcon type="error" message={error.message} closable onClose={() => setError(null)} />}
    {!understanding && <Card className="application-step" title="选择应用文件夹">
      <Typography.Paragraph>界鉴先读取少量配置识别应用；不会启动项目、安装依赖或读取秘密。</Typography.Paragraph>
      <Collapse ghost items={[{ key: 'manual-path', label: '目录选择器不可用？', children: <Space.Compact className="application-manual-path"><Input aria-label="应用文件夹绝对路径" value={manualPath} onChange={(event) => setManualPath(event.target.value)} placeholder="输入应用文件夹绝对路径" /><Button loading={loading} onClick={() => void connectPath(manualPath)}>连接这个目录</Button></Space.Compact> }]} />
    </Card>}
    {understanding && !endpointReady && <Card className="application-step" title="确认本地访问地址">
      {discovery && <div className="application-discovery">
        <Typography.Text strong>识别结果</Typography.Text>
        <Space wrap>{discovery.detected_types.length > 0 ? discovery.detected_types.map((item) => <Tag key={item}>{item}</Tag>) : <Typography.Text type="secondary">未识别到明确技术栈</Typography.Text>}</Space>
        {discovery.start_candidates.length > 0 && <Typography.Text type="secondary">可能启动方式：{discovery.start_candidates.map((item) => item.label).join('、')}（只作提示，不会执行）</Typography.Text>}
      </div>}
      <Typography.Paragraph>界鉴只探测 127.0.0.1 的少量配置候选，不扫描任意端口。自动发现不等于授权。</Typography.Paragraph>
      <Radio.Group className="endpoint-list" value={endpoint} onChange={(event) => setEndpoint(event.target.value)}>
        <Space direction="vertical">
          {endpoints?.candidates.map((candidate) => <Radio key={candidate.endpoint} value={candidate.endpoint} disabled={!candidate.reachable}>{candidate.endpoint} · {candidate.source} · {candidate.reachable ? '已响应' : candidate.probe_detail}</Radio>)}
        </Space>
      </Radio.Group>
      <Input aria-label="手工输入本地地址" value={endpoint} onChange={(event) => setEndpoint(event.target.value)} placeholder="没有候选时输入 http://127.0.0.1:端口" />
      <Checkbox checked={appRunningConfirmed} onChange={(event) => setAppRunningConfirmed(event.target.checked)}>我确认应用已经由我启动，界鉴不需要执行任何启动命令</Checkbox>
      <Checkbox checked={endpointConfirmed} onChange={(event) => setEndpointConfirmed(event.target.checked)}>确认这是我的本地应用，并允许界鉴访问这个地址</Checkbox>
    </Card>}
    {endpointReady && understanding?.confirmed_endpoint && !understanding.source_fingerprint && <Card className="application-step" title="分析权限组与关键业务动作">
      <Typography.Paragraph>已确认地址：<Tag color="blue">{understanding.confirmed_endpoint}</Tag></Typography.Paragraph>
      <Alert type="warning" showIcon message="需要你单独授权只读源码分析" description="界鉴不会执行或导入源码，不会运行 npm/python 命令，不会联网，不读取 .env、私钥、凭据和生成目录，也不会把源码正文写入报告、日志或发送给模型。" />
      <Checkbox checked={analysisAuthorized} onChange={(event) => setAnalysisAuthorized(event.target.checked)}>我允许界鉴只读分析当前应用源码，用于寻找权限组与关键业务动作</Checkbox>
    </Card>}
    {candidateReview}
    <TaskActionBar
      back={{ label: '返回工作台', onClick: onBack }}
      refresh={understanding ? { label: '刷新当前状态', onClick: () => void refreshUnderstanding(), loading } : undefined}
      restart={currentStep === 4 ? {
        label: '重新分析当前源码',
        onClick: () => void reanalyze(),
        loading,
        confirm: {
          title: '重新分析当前源码？',
          description: '界鉴会重新读取当前源码并更新系统发现的权限组和业务动作；手工补充内容会保留，源码中不再出现的候选会要求复核。',
          okText: '重新分析',
          cancelText: '取消',
        },
      } : undefined}
      primary={primaryAction}
    />
  </div>
}
