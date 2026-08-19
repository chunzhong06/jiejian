/* =============================================================================
 * 录制页面
 *
 * 定位
 *   Recording 创建、状态恢复和 FlowDraft 审阅的用户能力页面
 *
 * 职责
 *   提交受控录制｜恢复 Recording 状态｜应用审阅命令并确认 Flow
 *
 * 调用链
 *   ControlShell → RecordingPage → recordingsApi / recording status
 * ============================================================================= */

import { useEffect, useState } from 'react'
import { Alert, Button, Card, Collapse, Descriptions, Form, Input, InputNumber, List, Space, Tag, Typography } from 'antd'
import { ApiError } from '../../api/http'
import { recordingsApi } from '../../api/recordings'
import { runsApi } from '../../api/runs'
import { PageTaskHeader } from '../../components/PageTaskHeader'
import { lifecycleLabel } from '../../app/presentation'

type Item = Record<string, any>
const resourceKey = 'jiejian.resource'
const cursorKey = 'jiejian.cursor'

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

export function RecordingPage({ project, onError, onNext }: { project: Item; onError: (e: ApiError) => void; onNext?: () => void }) {
  const stored = recalled<Item>(resourceKey)
  const [recording, setRecording] = useState<Item | null>(stored?.project_id === project.project_id ? stored : null)
  const [commandText, setCommandText] = useState('{\n  "operation": "RENAME_STEP",\n  "step_id": "step-id",\n  "name": "新步骤名称"\n}')
  const [bindingsText, setBindingsText] = useState('{}')
  const [inputError, setInputError] = useState<string | null>(null)
  const updateView = (view: Item) => {
    const next = { ...(view.recording ?? view), draft: view.draft ?? null, job: view.job ?? recording?.job, flow_path: view.flow_path }
    setRecording(next); remember(resourceKey, next)
  }
  const refresh = async (recordingId = recording?.recording_id) => {
    if (!recordingId) return
    try { updateView(await recordingsApi.recording(String(recordingId))) } catch (e) { onError(e as ApiError) }
  }
  useEffect(() => {
    void recordingsApi.recordings(project.project_id).then(async (items) => { if (items[0]?.recording_id) await refresh(String(items[0].recording_id)) }).catch((e) => onError(e as ApiError))
  }, [project.project_id])
  const start = async ({ identities, duration }: { identities?: string; duration?: number }) => {
    try {
      const output = await recordingsApi.createRecording(
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
      updateView(await recordingsApi.reviewRecording(String(recording.recording_id), command, parsedBindings))
      setInputError(null)
    } catch (e) {
      if (e instanceof SyntaxError || e instanceof Error && !(e instanceof ApiError)) setInputError(e.message)
      else onError(e as ApiError)
    }
  }
  const finalize = async () => {
    if (!recording?.recording_id) return
    try {
      updateView(await recordingsApi.finalizeRecording(String(recording.recording_id)))
      setInputError(null)
    } catch (e) {
      onError(e as ApiError)
    }
  }
  const draft = recording?.draft as Item | undefined
  const reviewable = recording?.state === 'PENDING_REVIEW' && Boolean(draft)
  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}><PageTaskHeader title="流程录制" description="记录一次真实操作，形成可重复使用的检查步骤。" status={recording ? '已有录制' : '尚未开始'} next={recording ? '审阅或确认步骤' : '录制是可选的，也可以直接开始检查'} actionLabel="去权限规则" onAction={onNext} /> <Card title="流程录制">
      <Typography.Paragraph>
        快速检查可以跳过录制；如需记录真实操作，可在这里开始。关闭页面或事件流仅断开连接，不会取消任务。
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
          <RecordingProgress
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
          <Collapse ghost items={[{ key: 'advanced-recording', label: '高级：录制与步骤调整', forceRender: true, children: <Space direction="vertical" className="full-width">
          <Descriptions size="small" column={1} title="当前录制">
            <Descriptions.Item label="身份记录标识">{recording.recording_id}</Descriptions.Item>
            <Descriptions.Item label="状态">{recording.state}</Descriptions.Item>
            {recording.flow_path && <Descriptions.Item label="最终步骤文件">{recording.flow_path}</Descriptions.Item>}
          </Descriptions>
          {draft && (
            <Card size="small" title={`步骤草稿 revision ${draft.revision}`}>
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
          </Card></Space> }]} />
        </Space>
      )}
    </Card></Space>
  )
}

function RecordingProgress({ job, onRefresh, onError }: { job?: Item; onRefresh: () => void; onError: (e: ApiError) => void }) {
  const [event, setEvent] = useState<Item | null>(null)
  useEffect(() => {
    if (!job?.job_id || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(String(job.state))) return
    const stored = Number(localStorage.getItem(`${cursorKey}.${job.job_id}`) ?? 0)
    const source = new EventSource(`/api/jobs/${job.job_id}/events?after=${Math.max(stored, 0)}`)
    source.onmessage = (message) => { const next = JSON.parse(message.data) as Item; setEvent(next); localStorage.setItem(`${cursorKey}.${job.job_id}`, String(next.sequence)); onRefresh() }
    source.onerror = () => undefined
    return () => source.close()
  }, [job?.job_id, job?.state])
  if (!job) return null
  const terminal = ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(String(job.state))
  return <Space wrap><Tag>后台状态：{lifecycleLabel(job.state)}</Tag>{event && <Typography.Text type="secondary">后台正在处理</Typography.Text>}{!terminal && <Button danger size="small" onClick={() => runsApi.cancel(String(job.job_id)).then(onRefresh).catch(onError)}>取消录制</Button>}</Space>
}
