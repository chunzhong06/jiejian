/* 统一 AI 辅助面板；冷读取只看缓存，模型调用必须由用户点击触发。 */

import { Button, List, Space, Tag, Typography } from 'antd'
import { useEffect, useMemo, useRef, useState } from 'react'
import { assistantApi, type AssistantFocus, type AssistantSurfaceView, type ProjectAssistantSurface } from '../api/assistant'
import type { ErrorDiagnosis } from '../api/http'

type AssistantSubject =
  | { projectId: string; surface: ProjectAssistantSurface; focus?: AssistantFocus; runId?: never; error?: never }
  | { runId: string; projectId?: never; surface?: never; error?: never }
  | { error: { code: string; diagnosis: ErrorDiagnosis }; projectId?: never; surface?: never; runId?: never }

function isProjectSubject(subject: AssistantSubject): subject is Extract<AssistantSubject, { projectId: string }> {
  return typeof subject.projectId === 'string'
}

function isRunSubject(subject: AssistantSubject): subject is Extract<AssistantSubject, { runId: string }> {
  return typeof subject.runId === 'string'
}

export function AssistantPanel({ title, actionLabel, ...subject }: AssistantSubject & { title: string; actionLabel: string }) {
  const [view, setView] = useState<AssistantSurfaceView | null>(null)
  const [loading, setLoading] = useState(false)
  const [localError, setLocalError] = useState<string>()
  const subjectKey = isProjectSubject(subject)
    ? `${subject.projectId}:${subject.surface}:${JSON.stringify(subject.focus ?? {})}`
    : isRunSubject(subject)
      ? subject.runId
      : `${subject.error.code}:${subject.error.diagnosis.cause ?? ''}`

  const currentSubject = useRef<string | null>(subjectKey)
  useEffect(() => {
    currentSubject.current = subjectKey
    setLoading(false)
    setView(null)
    setLocalError(undefined)
    if (!isProjectSubject(subject) && !isRunSubject(subject)) return
    let active = true
    const request = isProjectSubject(subject)
      ? assistantApi.project(subject.projectId, subject.surface, subject.focus)
      : assistantApi.result(subject.runId)
    void request.then((value) => { if (active) setView(value) }).catch(() => {
      if (active) setLocalError('当前还没有可供 AI 解读的完整事实。')
    })
    return () => { active = false; currentSubject.current = null }
  }, [subjectKey])

  const generate = async () => {
    const requestedSubject = subjectKey
    setLoading(true)
    setLocalError(undefined)
    try {
      const retry = view?.status === 'BACKOFF'
      const value = isProjectSubject(subject)
        ? await assistantApi.generateProject(subject.projectId, subject.surface, retry, subject.focus)
        : isRunSubject(subject)
          ? await assistantApi.generateResult(subject.runId, retry)
          : await assistantApi.generateError(subject.error.code, retry)
      if (currentSubject.current === requestedSubject) setView(value)
    } catch {
      if (currentSubject.current === requestedSubject) setLocalError('AI 辅助暂时没有完成，仍可手工继续当前任务。')
    } finally {
      if (currentSubject.current === requestedSubject) setLoading(false)
    }
  }

  const labels = useMemo(
    () => new Map((view?.entities ?? []).map((entity) => [entity.entity_id, entity.display_name])),
    [view?.state_fingerprint],
  )
  const disabled = view?.status === 'DISABLED'
  if (view?.can_generate === false) return null
  return <section className="assistant-panel" aria-label={`AI辅助：${title}`}>
    <div className="assistant-panel-heading">
      <Space wrap><Tag color="purple">[AI辅助]</Tag><Typography.Text strong>{title}</Typography.Text></Space>
      <Button size="small" loading={loading || view?.status === 'GENERATING'} disabled={disabled || (isProjectSubject(subject) && !view)} onClick={() => void generate()}>
        {view?.status === 'BACKOFF' ? '重试 AI 辅助' : actionLabel}
      </Button>
    </div>
    {disabled && <Typography.Text type="secondary">AI 辅助未开启或尚未配置；当前任务仍可继续。</Typography.Text>}
    {!disabled && localError && <Typography.Text type="secondary">{localError}</Typography.Text>}
    {!disabled && !localError && view?.status === 'REFRESH_NEEDED' && <Typography.Text type="secondary">尚未生成建议，点击按钮后才会连接模型服务。</Typography.Text>}
    {!disabled && !localError && view?.status === 'GENERATING' && <Typography.Text type="secondary">正在生成受限建议。</Typography.Text>}
    {view?.status === 'READY' && <List
      size="small"
      locale={{ emptyText: '当前没有额外建议' }}
      dataSource={view.suggestions}
      renderItem={(item) => <List.Item><List.Item.Meta
        title={item.entity_ids.map((id) => labels.get(id) ?? '当前材料').join('、')}
        description={item.explanation}
      /></List.Item>}
    />}
  </section>
}
