/* =============================================================================
 * 流程录制页面
 *
 * 定位
 *   已登记执行身份、受控浏览器采集和 FlowDraft 图形审阅的产品入口
 *
 * 职责
 *   选择单一身份｜明确开始和停止采集｜审阅步骤、映射与动态变量
 *
 * 边界
 *   普通流程不接收磁盘路径、headless 开关或原始 JSON；安全校验仍由后端完成。
 * ============================================================================= */

import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, Divider, Input, InputNumber, List, Popconfirm, Radio, Select, Space, Tag, Typography } from 'antd'
import { executionProfilesApi } from '../../api/executionProfiles'
import { ApiError } from '../../api/http'
import { recordingsApi } from '../../api/recordings'
import { runsApi } from '../../api/runs'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { lifecycleLabel } from '../../app/presentation'

type Item = Record<string, any>
type Binding = {
  alternate_identity_id: string
  resource_id: string
  alternate_resource_id: string
}

const resourceKey = 'jiejian.resource'
const cursorKey = 'jiejian.cursor'
const finishedStates = new Set(['PENDING_REVIEW', 'COMPLETED', 'FAILED', 'CANCELLED', 'SAFETY_STOPPED'])

function remember(value: Item) {
  localStorage.setItem(resourceKey, JSON.stringify(value))
}

function recalled(): Item | null {
  try {
    return JSON.parse(localStorage.getItem(resourceKey) ?? 'null') as Item
  } catch {
    return null
  }
}

function captureLabel(recording: Item | null) {
  if (!recording) return '尚未开始'
  if (recording.state === 'PENDING_REVIEW') return '等待确认'
  if (recording.state === 'COMPLETED') return '流程已保存'
  if (recording.state === 'CANCELLED') return '本次录制已取消'
  if (recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED') return '录制未完成'
  return ({
    PREPARING_BROWSER: '正在准备浏览器',
    AWAITING_CAPTURE: '等待登录准备',
    CAPTURE_STARTING: '正在开始录制',
    CAPTURING: '正在录制',
    STOPPING: '正在生成流程',
    FINISHED: '正在整理结果',
  } as Record<string, string>)[String(recording.capture_phase)] ?? '正在准备录制'
}

export function RecordingPage({ project, onError, onNext }: { project: Item; onError: (error: ApiError) => void; onNext?: () => void }) {
  const stored = recalled()
  const [recording, setRecording] = useState<Item | null>(stored?.project_id === project.project_id ? stored : null)
  const [profiles, setProfiles] = useState<Item[]>([])
  const [profileId, setProfileId] = useState<string>()
  const [identityOptions, setIdentityOptions] = useState<Item[]>([])
  const [identityId, setIdentityId] = useState<string>()
  const [duration, setDuration] = useState(600)
  const [bindings, setBindings] = useState<Record<string, Binding>>({})
  const [sources, setSources] = useState<Record<string, string>>({})
  const [renamingStep, setRenamingStep] = useState<string>()
  const [renameValue, setRenameValue] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string>()

  const updateView = (view: Item) => {
    setRecording((current) => {
      const record = (view.recording ?? view) as Item
      const next = {
        ...current,
        ...record,
        project_id: record.project_id ?? current?.project_id ?? project.project_id,
        draft: Object.prototype.hasOwnProperty.call(view, 'draft') ? view.draft : current?.draft,
        job: view.job ?? current?.job,
        capture_phase: view.capture_phase ?? current?.capture_phase,
        flow_path: view.flow_path ?? current?.flow_path,
        identity_options: view.identity_options ?? current?.identity_options,
      }
      remember(next)
      return next
    })
  }

  const refresh = async (recordingId = recording?.recording_id) => {
    if (!recordingId) return
    try {
      updateView(await recordingsApi.recording(String(recordingId)))
    } catch (error) {
      onError(error as ApiError)
    }
  }

  useEffect(() => {
    let active = true
    setRecording((current) => current?.project_id === project.project_id ? current : null)
    Promise.all([
      executionProfilesApi.profiles(project.project_id),
      recordingsApi.recordings(project.project_id),
    ]).then(([profileItems, recordings]) => {
      if (!active) return
      setProfiles(profileItems)
      setProfileId((current) => current && profileItems.some((item) => String(item.profile_id) === current)
        ? current
        : profileItems.length ? String(profileItems[0].profile_id) : undefined)
      if (recordings[0]?.recording_id) void refresh(String(recordings[0].recording_id))
    }).catch((error) => onError(error as ApiError))
    return () => { active = false }
  }, [project.project_id])

  useEffect(() => {
    if (!profileId) {
      setIdentityOptions([])
      setIdentityId(undefined)
      return
    }
    let active = true
    recordingsApi.setup(project.project_id, profileId).then((setup) => {
      if (!active) return
      const options = (setup.identity_options ?? []) as Item[]
      setIdentityOptions(options)
      setIdentityId((current) => current && options.some((item) => String(item.identity_id) === current)
        ? current
        : options.length ? String(options[0].identity_id) : undefined)
    }).catch((error) => onError(error as ApiError))
    return () => { active = false }
  }, [project.project_id, profileId])

  useEffect(() => {
    const recordingId = recording?.recording_id
    if (!recordingId || finishedStates.has(String(recording.state))) return
    const timer = window.setInterval(() => { void refresh(String(recordingId)) }, 1200)
    return () => window.clearInterval(timer)
  }, [recording?.recording_id, recording?.state])

  const draft = recording?.draft as Item | undefined
  const steps = useMemo(() => (draft?.steps ?? []) as Item[], [draft?.revision])
  const variables = useMemo(() => (draft?.variables ?? []) as Item[], [draft?.revision])

  useEffect(() => {
    if (!draft) return
    setBindings((current) => Object.fromEntries(steps.filter((step) => step.method).map((step) => {
      const previous = current[String(step.id)]
      const alternate = identityOptions.find((item) => String(item.identity_id) !== String(step.identity_id))
      return [String(step.id), {
        alternate_identity_id: previous?.alternate_identity_id ?? step.alternate_identity_id ?? String(alternate?.identity_id ?? ''),
        resource_id: previous?.resource_id ?? step.resource_id ?? '',
        alternate_resource_id: previous?.alternate_resource_id ?? step.alternate_resource_id ?? '',
      }]
    })))
    setSources((current) => Object.fromEntries(variables.map((variable) => {
      const confirmed = variable.confirmed_source as Item | undefined
      const first = (variable.candidate_sources ?? [])[0] as Item | undefined
      const selected = confirmed ?? first
      return [String(variable.name), current[String(variable.name)] ?? (selected ? `${selected.source_event_sequence}|${selected.json_path}` : '')]
    })))
  }, [draft?.revision, identityOptions.map((item) => item.identity_id).join('|')])

  const createRecording = async () => {
    if (!profileId || !identityId) return
    setBusy(true)
    setMessage(undefined)
    try {
      const output = await recordingsApi.createRecording(project.project_id, profileId, identityId, duration)
      updateView({ ...output, draft: null, capture_phase: 'PREPARING_BROWSER', profile_id: profileId })
    } catch (error) {
      onError(error as ApiError)
    } finally {
      setBusy(false)
    }
  }

  const controlCapture = async (action: 'start' | 'stop') => {
    if (!recording?.recording_id) return
    setBusy(true)
    try {
      updateView(action === 'start'
        ? await recordingsApi.startCapture(String(recording.recording_id))
        : await recordingsApi.stopCapture(String(recording.recording_id)))
    } catch (error) {
      onError(error as ApiError)
    } finally {
      setBusy(false)
    }
  }

  const review = async (command: Record<string, unknown>) => {
    if (!recording?.recording_id) return
    setBusy(true)
    setMessage(undefined)
    try {
      updateView(await recordingsApi.reviewRecording(String(recording.recording_id), command))
      setRenamingStep(undefined)
    } catch (error) {
      onError(error as ApiError)
    } finally {
      setBusy(false)
    }
  }

  const networkSteps = steps.filter((step) => step.method)
  const bindingsReady = networkSteps.every((step) => {
    const binding = bindings[String(step.id)]
    return binding && Object.values(binding).every((value) => value.trim())
  })
  const sourcesReady = variables.every((variable) => Boolean(sources[String(variable.name)]))
  const hasLooseActions = steps.some((step) => !step.method)
  const canFinalize = Boolean(draft && steps.length && bindingsReady && sourcesReady && !hasLooseActions)

  const finalize = async () => {
    if (!recording?.recording_id || !draft || !canFinalize) return
    setBusy(true)
    setMessage(undefined)
    try {
      for (const variable of variables) {
        if (variable.status === 'CONFIRMED') continue
        const selected = sources[String(variable.name)]
        const separator = selected.indexOf('|')
        const sourceEventSequence = Number(selected.slice(0, separator))
        const sourceJsonPath = selected.slice(separator + 1)
        const reviewed = await recordingsApi.reviewRecording(String(recording.recording_id), {
          schema_version: '1',
          operation: 'CONFIRM_VARIABLE_SOURCE',
          variable_name: variable.name,
          source_event_sequence: sourceEventSequence,
          source_json_path: sourceJsonPath,
        })
        updateView(reviewed)
      }
      updateView(await recordingsApi.finalizeRecording(String(recording.recording_id), bindings))
      setMessage('流程已经保存，可以用于后续检查。')
    } catch (error) {
      onError(error as ApiError)
    } finally {
      setBusy(false)
    }
  }

  const phase = String(recording?.capture_phase ?? '')
  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  return <Space direction="vertical" size="large" className="full-width">
    <PageTaskHeader
      title="流程录制"
      description="在真实浏览器中完成一次操作，再把它整理为可重复使用的检查流程。"
      status={captureLabel(recording)}
      next={recording?.state === 'COMPLETED' ? '流程已保存，可以继续完善权限规则' : '先选择身份，再准备登录和录制'}
      actionLabel={recording?.state === 'COMPLETED' ? '去权限规则' : undefined}
      onAction={recording?.state === 'COMPLETED' ? onNext : undefined}
    />

    <Card title="选择录制身份">
      {profiles.length === 0
        ? <Alert type="info" showIcon message="当前应用还没有已登记的执行配置" description="请先在权限规则中登记 ExecutionProfile，再回来选择录制身份。" />
        : <Space wrap size="middle">
          {profiles.length > 1 && <Select aria-label="选择执行配置" value={profileId} onChange={setProfileId} style={{ minWidth: 220 }} options={profiles.map((item, index) => ({ value: String(item.profile_id), label: `执行配置 ${index + 1}` }))} />}
          <Select
            aria-label="选择录制身份"
            placeholder="选择一个身份"
            value={identityId}
            onChange={setIdentityId}
            style={{ minWidth: 260 }}
            options={identityOptions.map((item) => ({
              value: String(item.identity_id),
              label: <Space><Typography.Text strong>{String(item.role || '未命名角色')}</Typography.Text><Typography.Text type="secondary">{String(item.identity_id)}</Typography.Text></Space>,
            }))}
          />
          <Space.Compact>
            <InputNumber aria-label="最长录制时间（秒）" min={60} max={3600} value={duration} onChange={(value) => setDuration(value ?? 600)} />
            <Button disabled>秒</Button>
          </Space.Compact>
          <Button type="primary" loading={busy} disabled={!profileId || !identityId || Boolean(recording && !finishedStates.has(String(recording.state)))} onClick={() => void createRecording()}>
            打开浏览器并准备登录
          </Button>
        </Space>}
    </Card>

    {recording && <Card title="录制进度" extra={<Button onClick={() => void refresh()}>刷新状态</Button>}>
      <Space direction="vertical" className="full-width" size="middle">
        <Alert
          type={phase === 'CAPTURING' ? 'warning' : recording.state === 'FAILED' || recording.state === 'SAFETY_STOPPED' ? 'error' : 'info'}
          showIcon
          message={captureLabel(recording)}
          description={phase === 'PREPARING_BROWSER'
            ? '正在启动有界 Chromium，请稍候。'
            : phase === 'AWAITING_CAPTURE'
              ? '浏览器已经打开。请先完成登录并进入要录制的页面；这些准备操作不会写入流程。'
              : phase === 'CAPTURING'
                ? '现在开始记录你的操作。完成业务流程后，点击“停止录制并生成流程”。'
                : phase === 'STOPPING'
                  ? '正在停止采集、整理事件并生成步骤草稿。'
                  : recording.state === 'CANCELLED'
                    ? '本次事件已丢弃，没有生成流程草稿。'
                    : '界鉴会保留当前状态；关闭页面只会断开显示。'}
        />
        <Space wrap>
          {phase === 'AWAITING_CAPTURE' && <Button type="primary" size="large" loading={busy} onClick={() => void controlCapture('start')}>开始录制</Button>}
          {phase === 'CAPTURING' && <Button type="primary" danger size="large" loading={busy} onClick={() => void controlCapture('stop')}>停止录制并生成流程</Button>}
          <RecordingProgress job={recording.job} canCancel={!finishedStates.has(String(recording.state))} onRefresh={() => void refresh()} onError={onError} />
        </Space>
      </Space>
    </Card>}

    {reviewable && <Card title="确认录制流程">
      <Typography.Paragraph>按实际业务含义检查步骤名称、执行身份、资源映射和动态变量。普通流程无需编辑 JSON。</Typography.Paragraph>
      <List
        split={false}
        dataSource={steps}
        renderItem={(step: Item, index) => {
          const id = String(step.id)
          const binding = bindings[id] ?? { alternate_identity_id: '', resource_id: '', alternate_resource_id: '' }
          return <List.Item style={{ display: 'block' }}>
            <Card
              size="small"
              title={<Space wrap><Typography.Text strong>步骤 {index + 1}：{String(step.name)}</Typography.Text>{step.method ? <Tag color="blue">{String(step.method)}</Tag> : <Tag color="gold">需要合并</Tag>}</Space>}
              extra={<Space>
                <Button size="small" onClick={() => { setRenamingStep(id); setRenameValue(String(step.name)) }}>重命名</Button>
                <Popconfirm title="删除这个步骤？" description="仍被其他步骤或变量引用时，界鉴会拒绝删除。" onConfirm={() => void review({ schema_version: '1', operation: 'DELETE_STEP', step_id: id })}>
                  <Button aria-label={`删除步骤 ${index + 1}`} size="small" danger disabled={steps.length === 1}>删除</Button>
                </Popconfirm>
              </Space>}
            >
              {renamingStep === id && <Space.Compact block>
                <Input aria-label={`步骤 ${index + 1} 名称`} value={renameValue} maxLength={128} onChange={(event) => setRenameValue(event.target.value)} />
                <Button type="primary" disabled={!renameValue.trim()} onClick={() => void review({ schema_version: '1', operation: 'RENAME_STEP', step_id: id, name: renameValue.trim() })}>保存名称</Button>
                <Button onClick={() => setRenamingStep(undefined)}>取消</Button>
              </Space.Compact>}
              <Descriptions size="small" column={{ xs: 1, md: 2 }}>
                <Descriptions.Item label="当前身份">{identityOptions.find((item) => String(item.identity_id) === String(step.identity_id))?.role ?? step.identity_id}</Descriptions.Item>
                <Descriptions.Item label="操作">{step.method ? `${step.method} ${step.path}` : '浏览器界面操作，需与相邻请求合并'}</Descriptions.Item>
              </Descriptions>
              {step.method && <>
                <Divider orientation="left" plain>检查对象映射</Divider>
                <Space wrap align="start">
                  <Select aria-label={`步骤 ${index + 1} 对照身份`} placeholder="选择对照身份" value={binding.alternate_identity_id || undefined} onChange={(value) => setBindings((current) => ({ ...current, [id]: { ...binding, alternate_identity_id: value } }))} style={{ minWidth: 190 }} options={identityOptions.filter((item) => String(item.identity_id) !== String(step.identity_id)).map((item) => ({ value: String(item.identity_id), label: `${String(item.role)} · ${String(item.identity_id)}` }))} />
                  <Input aria-label={`步骤 ${index + 1} 当前资源`} placeholder="当前身份的资源名称" value={binding.resource_id} onChange={(event) => setBindings((current) => ({ ...current, [id]: { ...binding, resource_id: event.target.value } }))} style={{ width: 210 }} />
                  <Input aria-label={`步骤 ${index + 1} 对照资源`} placeholder="对照身份的资源名称" value={binding.alternate_resource_id} onChange={(event) => setBindings((current) => ({ ...current, [id]: { ...binding, alternate_resource_id: event.target.value } }))} style={{ width: 210 }} />
                </Space>
              </>}
            </Card>
            {index < steps.length - 1 && <div style={{ textAlign: 'center', padding: '12px 0 0' }}>
              <Button size="small" disabled={busy} onClick={() => void review({ schema_version: '1', operation: 'MERGE_ADJACENT_STEPS', left_step_id: id, right_step_id: String(steps[index + 1].id) })}>与下一步合并</Button>
            </div>}
          </List.Item>
        }}
      />

      {variables.length > 0 && <>
        <Divider orientation="left">动态变量</Divider>
        <Space direction="vertical" className="full-width">
          {variables.map((variable) => <Card size="small" key={String(variable.name)} title={<Space><Typography.Text strong>{String(variable.name)}</Typography.Text><Tag color={variable.status === 'CONFIRMED' ? 'green' : 'gold'}>{variable.status === 'CONFIRMED' ? '已确认' : '请选择来源'}</Tag></Space>}>
            <Typography.Paragraph type="secondary">后续步骤会使用这个值。请选择它来自哪个步骤的响应。</Typography.Paragraph>
            <Radio.Group value={sources[String(variable.name)]} onChange={(event) => setSources((current) => ({ ...current, [String(variable.name)]: event.target.value }))}>
              <Space direction="vertical">
                {(variable.candidate_sources ?? []).map((source: Item) => {
                  const sourceStep = steps.find((step) => String(step.id) === String(source.source_step_id))
                  const value = `${source.source_event_sequence}|${source.json_path}`
                  return <Radio key={value} value={value}>来自“{String(sourceStep?.name ?? '前序步骤')}”响应中的 {String(source.json_path).replace(/^\$\./, '')}</Radio>
                })}
              </Space>
            </Radio.Group>
          </Card>)}
        </Space>
      </>}

      {!canFinalize && <Alert style={{ marginTop: 16 }} type="warning" showIcon message="还有内容需要确认" description={hasLooseActions ? '请把只含界面动作的步骤与相邻请求合并，或删除无关步骤。' : !bindingsReady ? '请补全每个请求步骤的对照身份和资源映射。' : '请为每个动态变量选择来源。'} />}
      <div style={{ marginTop: 20 }}>
        <Button type="primary" size="large" loading={busy} disabled={!canFinalize} onClick={() => void finalize()}>确认并保存流程</Button>
      </div>
    </Card>}

    {message && <Alert type="success" showIcon message={message} />}

    {recording && <Collapse ghost items={[{
      key: 'advanced-recording',
      label: '高级信息',
      children: <Space direction="vertical" className="full-width">
        <Descriptions size="small" column={1}>
          <Descriptions.Item label="录制标识"><Typography.Text code>{String(recording.recording_id)}</Typography.Text></Descriptions.Item>
          <Descriptions.Item label="内部状态">{String(recording.state)} / {String(recording.capture_phase ?? 'UNKNOWN')}</Descriptions.Item>
          {recording.flow_path && <Descriptions.Item label="流程文件">{String(recording.flow_path)}</Descriptions.Item>}
        </Descriptions>
        {draft && <Collapse size="small" items={[{ key: 'raw-draft', label: '查看原始 FlowDraft（只读）', children: <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{JSON.stringify(draft, null, 2)}</pre> }]} />}
      </Space>,
    }]} />}
  </Space>
}

function RecordingProgress({ job, canCancel, onRefresh, onError }: { job?: Item; canCancel: boolean; onRefresh: () => void; onError: (error: ApiError) => void }) {
  const [event, setEvent] = useState<Item | null>(null)
  useEffect(() => {
    if (!job?.job_id || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(String(job.state))) return
    const stored = Number(localStorage.getItem(`${cursorKey}.${job.job_id}`) ?? 0)
    const source = new EventSource(`/api/jobs/${job.job_id}/events?after=${Math.max(stored, 0)}`)
    source.onmessage = (message) => {
      const next = JSON.parse(message.data) as Item
      setEvent(next)
      localStorage.setItem(`${cursorKey}.${job.job_id}`, String(next.sequence))
      onRefresh()
    }
    source.onerror = () => undefined
    return () => source.close()
  }, [job?.job_id, job?.state])
  if (!job) return null
  return <Space wrap>
    <Tag>后台状态：{lifecycleLabel(job.state)}</Tag>
    {event && <Typography.Text type="secondary">后台状态已更新</Typography.Text>}
    {canCancel && <Popconfirm title="取消并丢弃本次录制？" description="取消不会生成流程草稿。" onConfirm={() => runsApi.cancel(String(job.job_id)).then(onRefresh).catch(onError)}>
      <Button danger size="small">取消并丢弃</Button>
    </Popconfirm>}
  </Space>
}
