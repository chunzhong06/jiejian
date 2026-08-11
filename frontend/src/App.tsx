import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Descriptions, Form, Input, InputNumber, Layout, List, Menu, Result, Space, Steps, Tag, Typography } from 'antd'
import { AppstoreOutlined, CheckCircleOutlined, FileSearchOutlined, PlayCircleOutlined, SafetyCertificateOutlined } from '@ant-design/icons'
import { HashRouter, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError } from './api/client'
import './styles.css'

type Item = Record<string, any>
const remembered = {
  project: 'jiejian.project',
  resource: 'jiejian.resource',
  cursor: 'jiejian.cursor',
}
const phases = [
  { key: 'access', label: '接入', icon: <AppstoreOutlined /> },
  { key: 'recording', label: '录制', icon: <PlayCircleOutlined /> },
  { key: 'contract', label: '建约', icon: <SafetyCertificateOutlined /> },
  { key: 'run', label: '测试', icon: <CheckCircleOutlined /> },
  { key: 'verify', label: '验证', icon: <FileSearchOutlined /> },
  { key: 'report', label: '报告', icon: <FileSearchOutlined /> },
]

function remember(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value))
}

function recalled<T>(key: string): T | null {
  try {
    return JSON.parse(localStorage.getItem(key) ?? 'null') as T
  } catch {
    return null
  }
}

export default function App() {
  return <HashRouter><ControlShell /></HashRouter>
}

function ControlShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const routePhase = phases.some((item) => `/${item.key}` === location.pathname)
    ? location.pathname.slice(1)
    : 'access'
  const [projects, setProjects] = useState<Item[]>([])
  const [selected, setSelected] = useState<Item | null>(recalled<Item>(remembered.project))
  const [runs, setRuns] = useState<Item[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(false)
  const refresh = async () => {
    try {
      setProjects(await api.projects())
      setError(null)
    } catch (e) {
      setError(e as ApiError)
    }
  }
  const choose = (project: Item) => {
    setSelected(project)
    remember(remembered.project, project)
    navigate('/contract')
  }
  const refreshRuns = async () => {
    if (selected?.project_id) {
      try {
        setRuns(await api.runs(selected.project_id))
      } catch (e) {
        setError(e as ApiError)
      }
    }
  }
  useEffect(() => { void refresh() }, [])
  useEffect(() => { void refreshRuns() }, [selected?.project_id])
  useEffect(() => {
    if (location.pathname !== `/${routePhase}`) {
      navigate('/access', { replace: true })
    }
  }, [location.pathname, navigate, routePhase])
  const activeRun = useMemo(() => runs[0], [runs])
  const register = async ({ path }: { path: string }) => {
    setLoading(true)
    try {
      choose(await api.registerProject(path))
      await refresh()
    } catch (e) {
      setError(e as ApiError)
    } finally {
      setLoading(false)
    }
  }
  const content = () => {
    if (routePhase === 'access') return <AccessPage projects={projects} onSelect={choose} onRegister={register} loading={loading} />
    if (!selected) return <Result status="info" title="请先在接入阶段选择项目" />
    if (routePhase === 'contract') return <ContractPage project={selected} onError={setError} />
    if (routePhase === 'recording') return <RecordingPage project={selected} onError={setError} />
    if (routePhase === 'run') return <RunPage project={selected} runs={runs} onRefresh={refreshRuns} onError={setError} />
    if (routePhase === 'verify') return <VerifyPage run={activeRun} onError={setError} />
    return <ReportPage run={activeRun} onError={setError} />
  }
  return (
    <Layout className="app-shell">
      <Layout.Sider breakpoint="lg" collapsedWidth="0">
        <div className="brand">
          界鉴<span>安全意图差分验证</span>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[routePhase]}
          items={phases.map((item) => ({
            ...item,
            onClick: () => navigate(`/${item.key}`),
          }))}
        />
      </Layout.Sider>
      <Layout>
        <Layout.Header className="topbar">
          <Typography.Title level={3}>本地控制面</Typography.Title>
          <Tag color="green">API / Worker 回环运行</Tag>
        </Layout.Header>
        <Layout.Content className="content">
          <Steps
            current={Math.max(phases.findIndex((item) => item.key === routePhase), 0)}
            items={phases.map(({ label }) => ({ title: label }))}
            className="phase-steps"
          />
          {error && (
            <Alert
              closable
              showIcon
              type="error"
              message={`${error.code}: ${error.message}`}
              description={error.traceId ? `trace_id: ${error.traceId}` : undefined}
              onClose={() => setError(null)}
            />
          )}
          {content()}
        </Layout.Content>
      </Layout>
    </Layout>
  )
}

function AccessPage({
  projects,
  onSelect,
  onRegister,
  loading,
}: {
  projects: Item[]
  onSelect: (p: Item) => void
  onRegister: (v: { path: string }) => void
  loading: boolean
}) {
  return (
    <Card title="接入项目" extra={<Tag>{projects.length} 个项目</Tag>}>
      <Form layout="inline" onFinish={onRegister}>
        <Form.Item
          name="path"
          rules={[{ required: true, message: '请输入项目 YAML 绝对路径' }]}
        >
          <Input placeholder="D:\\demo\\project.yaml" style={{ width: 420 }} />
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={loading}>
          注册并校验
        </Button>
      </Form>
      <List
        className="project-list"
        dataSource={projects}
        locale={{ emptyText: '尚未注册项目' }}
        renderItem={(project) => (
          <List.Item
            actions={[
              <Button type="link" onClick={() => onSelect(project)}>
                打开
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={project.name}
              description={`${project.project_id} · ${project.status}`}
            />
          </List.Item>
        )}
      />
    </Card>
  )
}

function ContractPage({ project, onError }: { project: Item; onError: (e: ApiError) => void }) {
  const [contracts, setContracts] = useState<Item[]>([])
  useEffect(() => {
    void api.contracts(project.project_id).then(setContracts).catch((e) => onError(e))
  }, [project.project_id])
  return (
    <Card title="建约 · 显式 Contract">
      <Typography.Paragraph>
        仅展示并激活用户明确提供且状态为 ACTIVE 的契约。
      </Typography.Paragraph>
      <Form
        layout="inline"
        onFinish={({ path }) =>
          api
            .activateContract(project.project_id, path)
            .then(() => api.contracts(project.project_id))
            .then(setContracts)
            .catch(onError)
        }
      >
        <Form.Item name="path" rules={[{ required: true }]}>
          <Input placeholder="D:\\demo\\contract.yaml" style={{ width: 420 }} />
        </Form.Item>
        <Button htmlType="submit">激活</Button>
      </Form>
      <List
        dataSource={contracts}
        renderItem={(contract) => (
          <List.Item>
            <List.Item.Meta
              title={`${contract.id} v${contract.version}`}
              description={String(contract.path)}
            />
            <Tag color="blue">{String(contract.status)}</Tag>
          </List.Item>
        )}
      />
    </Card>
  )
}

export function JobProgress({ job, onRefresh, onError }: { job?: Item; onRefresh: () => void; onError: (e: ApiError) => void }) {
  const [event, setEvent] = useState<Item | null>(null)
  useEffect(() => {
    if (!job?.job_id || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state)) return
    const stored = recalled<number>(`${remembered.cursor}.${job.job_id}`) ?? 0
    const source = new EventSource(`/api/v1/jobs/${job.job_id}/events?after=${stored}`)
    source.onmessage = (message) => {
      const next = JSON.parse(message.data) as Item
      setEvent(next)
      remember(`${remembered.cursor}.${job.job_id}`, next.sequence)
      void onRefresh()
    }
    source.onerror = () => undefined
    return () => source.close()
  }, [job?.job_id, job?.state])
  if (!job) return null
  return (
    <Space>
      <Tag color={job.state === 'RUNNING' ? 'processing' : undefined}>
        任务 {job.state}
      </Tag>
      {event && (
        <Typography.Text type="secondary">
          事件 #{event.sequence}: {event.event_type}
        </Typography.Text>
      )}
      {!['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job.state) && (
        <Button
          danger
          size="small"
          onClick={() => api.cancel(String(job.job_id)).then(onRefresh).catch(onError)}
        >
          主动取消
        </Button>
      )}
    </Space>
  )
}

export function RecordingPage({ project, onError }: { project: Item; onError: (e: ApiError) => void }) {
  const stored = recalled<Item>(remembered.resource)
  const [recording, setRecording] = useState<Item | null>(stored?.project_id === project.project_id ? stored : null)
  const [commandText, setCommandText] = useState('{\n  "operation": "RENAME_STEP",\n  "step_id": "step-id",\n  "name": "新步骤名称"\n}')
  const [bindingsText, setBindingsText] = useState('{}')
  const [inputError, setInputError] = useState<string | null>(null)
  const updateView = (view: Item) => {
    const next = { ...(view.recording ?? view), draft: view.draft ?? null, job: view.job ?? recording?.job, flow_path: view.flow_path }
    setRecording(next); remember(remembered.resource, next)
  }
  const refresh = async (recordingId = recording?.recording_id) => {
    if (!recordingId) return
    try { updateView(await api.recording(String(recordingId))) } catch (e) { onError(e as ApiError) }
  }
  useEffect(() => {
    void api.recordings(project.project_id).then(async (items) => { if (items[0]?.recording_id) await refresh(String(items[0].recording_id)) }).catch((e) => onError(e as ApiError))
  }, [project.project_id])
  const start = async ({ identities, duration }: { identities?: string; duration?: number }) => {
    try {
      const output = await api.createRecording(
        project.project_id,
        identities ? identities.split(',').map((x) => x.trim()).filter(Boolean) : [],
        duration ?? 60,
      )
      updateView({ recording: output.recording, job: output.job, draft: null })
    } catch (e) {
      onError(e as ApiError)
    }
  }
  const review = async () => {
    if (!recording?.recording_id) return
    try {
      const command = JSON.parse(commandText) as Record<string, unknown>
      if (!command || Array.isArray(command) || typeof command !== 'object' || typeof command.operation !== 'string') throw new Error('command 必须是包含 operation 的 JSON 对象')
      const parsedBindings = JSON.parse(bindingsText) as Record<string, Record<string, string>>
      if (!parsedBindings || Array.isArray(parsedBindings) || typeof parsedBindings !== 'object') throw new Error('bindings 必须是 JSON 对象')
      updateView(await api.reviewRecording(String(recording.recording_id), command, parsedBindings))
      setInputError(null)
    } catch (e) {
      if (e instanceof SyntaxError || e instanceof Error && !(e instanceof ApiError)) setInputError(e.message)
      else onError(e as ApiError)
    }
  }
  const finalize = async () => {
    if (!recording?.recording_id) return
    try {
      updateView(await api.finalizeRecording(String(recording.recording_id)))
      setInputError(null)
    } catch (e) {
      onError(e as ApiError)
    }
  }
  const draft = recording?.draft as Item | undefined
  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  return (
    <Card title="录制">
      <Typography.Paragraph>
        录制任务由独立 Worker/Runner 执行；关闭页面或 SSE 仅断开连接，不会取消任务。
      </Typography.Paragraph>
      <Form layout="inline" onFinish={start}>
        <Form.Item name="identities">
          <Input placeholder="身份 ID（逗号分隔，留空为全部）" />
        </Form.Item>
        <Form.Item name="duration" initialValue={60}>
          <InputNumber min={1} max={3600} />
        </Form.Item>
        <Button type="primary" htmlType="submit">
          创建录制
        </Button>
      </Form>
      {recording && (
        <Space direction="vertical" className="full-width">
          <Descriptions size="small" column={1} title="当前录制">
            <Descriptions.Item label="ID">{recording.recording_id}</Descriptions.Item>
            <Descriptions.Item label="状态">{recording.state}</Descriptions.Item>
            {recording.flow_path && (
              <Descriptions.Item label="最终 Flow">
                {recording.flow_path}
              </Descriptions.Item>
            )}
          </Descriptions>
          <JobProgress
            job={recording.job}
            onRefresh={() => void refresh()}
            onError={onError}
          />
          <Space>
            <Button onClick={() => void refresh()}>刷新状态</Button>
            <Button
              type="primary"
              disabled={!reviewable}
              onClick={() => void review()}
            >
              提交审阅
            </Button>
            <Button
              disabled={!draft || !['PENDING_REVIEW', 'COMPLETED'].includes(String(recording.state))}
              onClick={() => void finalize()}
            >
              最终化
            </Button>
          </Space>
          {draft && (
            <Card size="small" title={`FlowDraft revision ${draft.revision}`}>
              <Typography.Paragraph>
                Flow ID：{String(draft.flow_id)}
              </Typography.Paragraph>
              <List
                size="small"
                header="步骤摘要"
                dataSource={draft.steps ?? []}
                renderItem={(step: Item) => (
                  <List.Item>
                    <List.Item.Meta
                      title={`${step.id} · ${step.name}`}
                      description={`${step.method ?? '待确认'} ${step.path ?? '待确认'} · 身份 ${step.identity_id}`}
                    />
                  </List.Item>
                )}
              />
              <List
                size="small"
                header="变量摘要"
                dataSource={draft.variables ?? []}
                locale={{ emptyText: '无变量' }}
                renderItem={(variable: Item) => (
                  <List.Item>
                    {variable.name} · 消费步骤：
                    {(variable.consumer_step_ids ?? []).join(', ') || '无'}
                  </List.Item>
                )}
              />
            </Card>
          )}
          <Card size="small" title="审阅命令 JSON">
            <Typography.Paragraph type="secondary">
              支持 DELETE_STEP、MERGE_ADJACENT_STEPS、RENAME_STEP、CONFIRM_VARIABLE_SOURCE；权威校验由后端完成。
            </Typography.Paragraph>
            <Input.TextArea
              rows={7}
              value={commandText}
              onChange={(e) => setCommandText(e.target.value)}
              status={inputError ? 'error' : undefined}
            />
            <Input.TextArea
              className="json-editor"
              rows={4}
              value={bindingsText}
              onChange={(e) => setBindingsText(e.target.value)}
              placeholder="可选 bindings JSON，例如：{}"
            />
            {inputError && <Alert type="error" showIcon message={inputError} />}
          </Card>
        </Space>
      )}
    </Card>
  )
}
function RunPage({ project, runs, onRefresh, onError }: { project: Item; runs: Item[]; onRefresh: () => void; onError: (e: ApiError) => void }) {
  const create = async () => { try { const result = await api.createRun(project.project_id); remember(remembered.resource, result.run); await onRefresh() } catch (e) { onError(e as ApiError) } }
  return <Card title="测试" extra={<Button type="primary" onClick={() => void create()}>创建 Run</Button>}><List dataSource={runs} locale={{ emptyText: '暂无运行' }} renderItem={(run) => {
    const integrity = String(run.result_integrity ?? 'UNAVAILABLE')
    const integrityColor = integrity === 'VERIFIED' ? 'green' : integrity === 'INVALID' ? 'red' : 'default'
    return <List.Item><Space direction="vertical"><List.Item.Meta title={run.run_id} description={`生命周期：${run.lifecycle} · Contract ${run.contract_id} v${run.contract_version}`} /><Space><Tag color={integrityColor}>结果完整性：{integrity}</Tag>{integrity === 'INVALID' ? <Typography.Text type="danger">结果无效，已隐藏 Gate verdict</Typography.Text> : run.verdict && <Tag color={run.verdict === 'PASS' ? 'green' : run.verdict === 'BLOCK' ? 'red' : 'gold'}>Gate verdict：{run.verdict}</Tag>}</Space><JobProgress job={run.job} onRefresh={onRefresh} onError={onError} /></Space></List.Item>
  }} /></Card>
}

export function VerifyPage({ run, onError }: { run?: Item; onError: (e: ApiError) => void }) {
  const [current, setCurrent] = useState<Item | undefined>(run)
  const [findings, setFindings] = useState<Item[]>([])
  const [evidence, setEvidence] = useState<Item[]>([])
  const [detail, setDetail] = useState<Item | null>(null)
  useEffect(() => {
    setCurrent(run)
    if (run?.run_id) {
      void api.run(String(run.run_id)).then(setCurrent).catch((e) => onError(e as ApiError))
      void api.findings(String(run.run_id)).then(setFindings).catch((e) => onError(e as ApiError))
      void api.evidence(String(run.run_id)).then(setEvidence).catch((e) => onError(e as ApiError))
    }
  }, [run?.run_id])
  const target = current?.target_scope as Item | undefined
  const budget = current?.budget as Item | undefined
  const observer = current?.observer_health as Item | undefined
  const progress = current?.case_progress as Item | undefined
  const safety = current?.safety_context as Item | undefined
  const reasonCodes = Array.isArray(current?.reason_codes) ? current.reason_codes : []
  const safetyReasonCodes = Array.isArray(safety?.reason_codes) ? safety.reason_codes : []
  const integrity = String(current?.result_integrity ?? 'UNAVAILABLE')
  const verdictVisible = integrity !== 'INVALID'
  const integrityColor = integrity === 'VERIFIED' ? 'green' : integrity === 'INVALID' ? 'red' : 'default'
  return <Card title="验证">
    <Space direction="vertical" size="middle" className="full-width">
      <Card size="small" title="生命周期">
        <Descriptions size="small" column={1}><Descriptions.Item label="当前状态">{current?.lifecycle ?? '—'}</Descriptions.Item></Descriptions>
      </Card>
      <Card size="small" title="门禁结论">
        <Descriptions size="small" column={1}><Descriptions.Item label="Gate verdict">{verdictVisible ? <Tag color={current?.verdict === 'BLOCK' ? 'red' : current?.verdict === 'PASS' ? 'green' : 'gold'}>{current?.verdict ?? '等待结论'}</Tag> : <Typography.Text type="danger">结果完整性无效，已隐藏 Gate verdict</Typography.Text>}</Descriptions.Item></Descriptions>
      </Card>
      <Card size="small" title="结果完整性与运行概览">
        <Space direction="vertical" className="full-width">
          <Tag color={integrityColor}>结果完整性：{integrity}</Tag>
          <Descriptions size="small" column={1}>
            <Descriptions.Item label="目标 base_url">{String(target?.base_url ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="允许主机">{Array.isArray(target?.allowed_hosts) && target.allowed_hosts.length > 0 ? target.allowed_hosts.join('、') : '—'}</Descriptions.Item>
            <Descriptions.Item label="允许端口">{Array.isArray(target?.allowed_ports) && target.allowed_ports.length > 0 ? target.allowed_ports.join('、') : '—'}</Descriptions.Item>
            <Descriptions.Item label="预算 max_requests">{String(budget?.max_requests ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="预算 max_response_bytes">{String(budget?.max_response_bytes ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="预算 request_timeout_us">{String(budget?.request_timeout_us ?? '—')}</Descriptions.Item>
            <Descriptions.Item label="HTTP 观察器">{observer?.http?.configured ? '已配置' : '未配置'} · {observer?.http?.required ? '契约要求' : '契约未要求'}</Descriptions.Item>
            <Descriptions.Item label="owner_api 观察器">{observer?.owner_api?.configured ? '已配置' : '未配置'} · {observer?.owner_api?.required ? '契约要求' : '契约未要求'}</Descriptions.Item>
            <Descriptions.Item label="用例进度">{progress?.status === 'PUBLISHED' ? `${progress.completed}/${progress.total}` : '发布后可用'}</Descriptions.Item>
            <Descriptions.Item label="Finding 数量">{current?.finding_count == null ? '发布后可用' : String(current.finding_count)}</Descriptions.Item>
          </Descriptions>
        </Space>
      </Card>
      {current?.verdict === 'INCONCLUSIVE' && <Alert type="warning" showIcon message="INCONCLUSIVE · 原因码" description={reasonCodes.length ? reasonCodes.join('、') : '未提供 reason_codes'} />}
      {current?.lifecycle === 'SAFETY_STOPPED' && <Alert type="error" showIcon message="SAFETY_STOPPED · 安全边界已停止运行" description={<Descriptions size="small" column={1}><Descriptions.Item label="原因码">{safetyReasonCodes.length ? safetyReasonCodes.join('、') : '未提供 reason_codes'}</Descriptions.Item><Descriptions.Item label="目标">{String(safety?.target_scope?.base_url ?? target?.base_url ?? '—')}</Descriptions.Item><Descriptions.Item label="预算 max_requests">{String(safety?.budget?.max_requests ?? budget?.max_requests ?? '—')}</Descriptions.Item></Descriptions>} />}
      <List header="确定性 Findings" dataSource={findings} locale={{ emptyText: '等待已发布证据' }} renderItem={(finding) => <List.Item><Space><Tag>{finding.verdict}</Tag><Typography.Text>{finding.finding_id}</Typography.Text></Space></List.Item>} />
      <List header="证据差分" dataSource={evidence} renderItem={(item) => <List.Item actions={[<Button onClick={() => current && void api.evidenceDetail(String(current.run_id), String(item.evidence_id)).then(setDetail).catch((e) => onError(e as ApiError))}>查看差分</Button>]}><List.Item.Meta title={String(item.case_id)} description={`Evidence ${String(item.evidence_id)}`} /></List.Item>} />
      {detail && <Card size="small" title="身份、请求与副作用差分"><pre>{JSON.stringify(detail.difference ?? detail, null, 2)}</pre></Card>}
    </Space>
  </Card>
}
function ReportPage({ run, onError }: { run?: Item; onError: (e: ApiError) => void }) { const [report, setReport] = useState<Item | null>(null); useEffect(() => { if (run?.run_id) void api.report(run.run_id).then(setReport).catch((e) => onError(e as ApiError)) }, [run?.run_id]); return <Card title="报告"><Typography.Paragraph>报告仅来自通过发布完整性校验的 JSON。</Typography.Paragraph><pre className="report-view">{report ? JSON.stringify(report, null, 2) : '暂无已发布报告'}</pre></Card> }
