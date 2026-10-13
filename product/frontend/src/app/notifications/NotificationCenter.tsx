/* 全局通知：检查动态与错误队列共享浮层，消费结构化诊断，独立维护去重、过期和有限展示状态。 */

import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { Alert, Button, Space, Typography } from 'antd'
import { CloseOutlined } from '@ant-design/icons'
import type { ApiError, ErrorDiagnosis } from '../../api/http'
import { MotionPresenceList } from '../../shared/ui/MotionPresenceList'

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
  activity,
  resourceNotice,
}: {
  resourceNotice?: ReactNode
  activity?: { label:string; actionLabel:string; onView:()=>void; onDismiss?:()=>void } | null
  items: NotificationItem[]
  onDismiss: (key: string) => void
  onNavigate: (path: string, key: string) => void
}) {
  const visible = items.slice(-MAX_VISIBLE_SIZE)
  const overflow = Math.max(0, items.length - visible.length)
  const center = useRef<HTMLElement>(null)
  useLayoutEffect(() => {
    const element = center.current, shell = element?.closest<HTMLElement>('.app-shell')
    if (!element || !shell) return
    // 通知保持浮动，但正文末尾可滚到通知上方；不让错误提示挡住返回和提交按钮。
    const observer = new ResizeObserver(() => {
      const height = element.getBoundingClientRect().height
      shell.style.setProperty('--notification-clearance', height > 8 ? `${Math.ceil(height + 48)}px` : '0px')
    })
    observer.observe(element)
    return () => { observer.disconnect(); shell.style.removeProperty('--notification-clearance') }
  }, [])
  return <aside ref={center} className="notification-center" aria-label="全局通知" aria-live="polite" aria-relevant="additions">
    {resourceNotice}
    <MotionPresenceList items={activity ? [{...activity,key:'check-activity'}] : []}>{item=><section className="check-activity-toast" aria-label="检查动态">
      <div className="check-activity-toast-heading"><span>检查动态</span>{item.onDismiss && <Button type="text" aria-label="关闭检查提示" icon={<CloseOutlined />} onClick={item.onDismiss} />}</div>
      <p>{item.label}</p><div className="notification-actions"><Button type="link" onClick={item.onView}>{item.actionLabel}</Button></div>
    </section>}</MotionPresenceList>
    <div className="notification-stack">
      <MotionPresenceList items={visible}>{item=><NotificationCard item={item} onDismiss={onDismiss} onNavigate={onNavigate}/>}</MotionPresenceList>
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
  const recovery = ({
    APPLICATION_ENDPOINT_INVALID: {title:'先确认应用访问地址',text:'请到应用页确认正在运行的本地地址，再打开登录浏览器。启动应用不会代替这次确认。',route:'/application?step=connection'},
    MCP_PERMISSION_REQUIRED: {title:'本项目尚未允许 Agent 保存准备内容',text:'保存候选和材料建议需要本项目 PREPARE 授权。请在连接与授权中由你明确提升；正式规则仍需另行批准。',route:'/tools'},
  } as Record<string,{title:string;text:string;route:string}>)[item.code]
  return <Alert
    className="notification-card"
    type="error"
    showIcon
    onClose={() => onDismiss(item.key)}
    closable={{ closeIcon: <span aria-label={`关闭通知 ${diagnosis?.headline ?? item.code}`}>×</span> }}
    message={<span>{recovery?.title ?? diagnosis?.headline ?? '当前请求没有完成'}{item.count > 1 && <Typography.Text type="secondary"> · 已发生 {item.count} 次</Typography.Text>}</span>}
    description={<Space direction="vertical" size={8} className="full-width">
      <Typography.Text>{recovery?.text ?? diagnosis?.short_message ?? '请刷新状态后重试；仍失败时检查运行环境。'}</Typography.Text>
      {diagnosis?.cleanup_warnings.map((warning) => <Typography.Text type="warning" key={warning}>附加提示：{warning}</Typography.Text>)}
      <div className="notification-actions">
        <Button type="link" size="small" onClick={() => onDismiss(item.key)}>{persistent ? '我知道了' : '关闭'}</Button>
        {recovery && <Button type="link" size="small" onClick={()=>onNavigate(recovery.route,item.key)}>前往处理</Button>}
        {!recovery && diagnosis?.route && <Button type="link" size="small" onClick={() => onNavigate(diagnosis.route, item.key)}>前往处理页面</Button>}
      </div>
    </Space>}
  />
}

export function useNotificationExpiry(onChange: (updater: (items: NotificationItem[]) => NotificationItem[]) => void) {
  useEffect(() => {
    const timer = window.setInterval(() => onChange((items) => removeExpiredNotifications(items, Date.now())), 1_000)
    return () => window.clearInterval(timer)
  }, [onChange])
}
