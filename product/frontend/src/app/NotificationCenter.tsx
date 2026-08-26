/* 全局错误通知队列：消费结构化诊断，独立维护去重、过期和有限展示状态。 */

import { useEffect, useState } from 'react'
import { Alert, Button, Space, Typography } from 'antd'
import type { ApiError, ErrorDiagnosis } from '../api/http'

const FALLBACK_WINDOW_MS = 10_000
const DEFAULT_DURATION_MS = 6_000
const RETRY_DURATION_MS = 10_000
const MAX_QUEUE_SIZE = 12
const MAX_VISIBLE_SIZE = 3
const PERSISTENT_INTERVENTIONS = new Set([
  'USER_ACTION',
  'USER_ACTION_REQUIRED',
  'REVIEW_CONFIGURATION',
  'VERIFY_REAL_STATE',
  'REPAIR_RUNTIME',
  'CONFIGURE_MODEL',
  'CONTACT_MAINTAINER',
])
const SAFETY_CONCLUSION_CODES = new Set(['PASS', 'BLOCK', 'INCONCLUSIVE', 'SAFE', 'VULNERABLE'])

export type NotificationItem = {
  key: string
  code: string
  traceId?: string
  diagnosis?: ErrorDiagnosis
  count: number
  firstSeenAt: number
  lastSeenAt: number
  expiresAt: number | null
}

function diagnosisOf(error: ApiError) {
  return error.diagnosis
}

export function isNotificationError(error: ApiError) {
  return !SAFETY_CONCLUSION_CODES.has(error.code)
}

export function notificationKey(error: ApiError) {
  if (error.traceId) return `trace:${error.traceId}`
  const diagnosis = diagnosisOf(error)
  return `fallback:${error.code}:${diagnosis?.phase ?? ''}:${diagnosis?.route ?? ''}`
}

export function notificationDurationMs(error: ApiError) {
  const diagnosis = diagnosisOf(error)
  if (error.code === 'SAFETY_STOPPED' || diagnosis?.phase === 'SAFETY_STOPPED' || diagnosis?.cause === 'SAFETY_STOPPED') return null
  if (diagnosis?.intervention === 'RETRY') return RETRY_DURATION_MS
  if (PERSISTENT_INTERVENTIONS.has(diagnosis?.intervention ?? '')) return null
  return DEFAULT_DURATION_MS
}

export function removeExpiredNotifications(items: NotificationItem[], now: number) {
  return items.filter((item) => item.expiresAt === null || item.expiresAt > now)
}

export function enqueueNotification(items: NotificationItem[], error: ApiError, now: number) {
  if (!isNotificationError(error)) return items
  const active = removeExpiredNotifications(items, now)
  const key = notificationKey(error)
  const traceDedup = Boolean(error.traceId)
  const index = active.findIndex((item) => item.key === key && (traceDedup || now - item.lastSeenAt <= FALLBACK_WINDOW_MS))
  const duration = notificationDurationMs(error)
  if (index < 0) {
    return [...active, {
      key,
      code: error.code,
      traceId: error.traceId,
      diagnosis: error.diagnosis,
      count: 1,
      firstSeenAt: now,
      lastSeenAt: now,
      expiresAt: duration === null ? null : now + duration,
    }].slice(-MAX_QUEUE_SIZE)
  }
  const current = active[index]
  const next = {
    ...current,
    diagnosis: error.diagnosis ?? current.diagnosis,
    count: current.count + 1,
    lastSeenAt: now,
    expiresAt: duration === null ? null : now + duration,
  }
  return active.map((item, itemIndex) => itemIndex === index ? next : item)
}

export function NotificationCenter({
  items,
  onDismiss,
  onNavigate,
}: {
  items: NotificationItem[]
  onDismiss: (key: string) => void
  onNavigate: (path: string, key: string) => void
}) {
  const visible = items.slice(-MAX_VISIBLE_SIZE)
  const overflow = Math.max(0, items.length - visible.length)
  return <aside className="notification-center" aria-label="全局通知" aria-live="polite" aria-relevant="additions">
    <div className="notification-stack">
      {visible.map((item) => <NotificationCard key={item.key} item={item} onDismiss={onDismiss} onNavigate={onNavigate} />)}
    </div>
    {overflow > 0 && <Typography.Text className="notification-overflow">还有 {overflow} 条消息</Typography.Text>}
  </aside>
}

function NotificationCard({
  item,
  onDismiss,
  onNavigate,
}: {
  item: NotificationItem
  onDismiss: (key: string) => void
  onNavigate: (path: string, key: string) => void
}) {
  const diagnosis = item.diagnosis
  const persistent = item.expiresAt === null
  return <Alert
    className="notification-card"
    type="error"
    showIcon
    onClose={() => onDismiss(item.key)}
    closable={{ closeIcon: <span aria-label={`关闭通知 ${diagnosis?.headline ?? item.code}`}>×</span> }}
    message={<span>{diagnosis?.headline ?? '当前请求没有完成'}{item.count > 1 && <Typography.Text type="secondary"> · 已发生 {item.count} 次</Typography.Text>}</span>}
    description={<Space direction="vertical" size={8} className="full-width">
      <Typography.Text>{diagnosis?.short_message ?? '请刷新状态后重试；仍失败时检查运行环境。'}</Typography.Text>
      {diagnosis?.cleanup_warnings.map((warning) => <Typography.Text type="warning" key={warning}>附加提示：{warning}</Typography.Text>)}
      <Space wrap>
        {diagnosis?.route && <Button type="link" size="small" onClick={() => onNavigate(diagnosis.route, item.key)}>前往处理页面</Button>}
        <Button type="link" size="small" onClick={() => onDismiss(item.key)}>{persistent ? '我知道了' : '关闭'}</Button>
      </Space>
    </Space>}
  />
}

export function useNotificationExpiry(onChange: (updater: (items: NotificationItem[]) => NotificationItem[]) => void) {
  useEffect(() => {
    const timer = window.setInterval(() => onChange((items) => removeExpiredNotifications(items, Date.now())), 1_000)
    return () => window.clearInterval(timer)
  }, [onChange])
}
