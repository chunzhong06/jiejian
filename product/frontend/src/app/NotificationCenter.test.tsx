/* 全局通知队列测试：验证结构化诊断驱动的去重、时限、上限和安全结论隔离。 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/http'
import { enqueueNotification, NotificationCenter, notificationDurationMs } from './NotificationCenter'
import type { NotificationItem } from './NotificationCenter'

function error(code: string, diagnosis: Record<string, unknown> = {}, traceId?: string) {
  return new ApiError(code, '不应被通知正文消费的错误正文', traceId, {
    route: '/settings/system',
    headline: '结构化标题',
    short_message: '结构化短说明',
    cleanup_warnings: [],
    ...diagnosis,
  })
}

describe('NotificationCenter', () => {
  it('按 trace 或短窗口去重，安全结论不进入错误队列', () => {
    const first = error('API_ERROR', {}, 'trace-1')
    let items = enqueueNotification([], first, 1_000)
    items = enqueueNotification(items, error('API_ERROR', {}, 'trace-1'), 5_000)
    expect(items).toHaveLength(1)
    expect(items[0].count).toBe(2)

    items = enqueueNotification(items, error('API_ERROR', { phase: 'PREPARE' }), 5_001)
    items = enqueueNotification(items, error('API_ERROR', { phase: 'PREPARE' }), 5_500)
    expect(items).toHaveLength(2)
    expect(items[1].count).toBe(2)
    expect(enqueueNotification(items, error('BLOCK'), 55_001)).toHaveLength(2)
  })

  it('按干预类型决定自动消失时限，并限制可见堆栈', () => {
    expect(notificationDurationMs(error('API_ERROR', { intervention: 'RETRY' }))).toBe(10_000)
    expect(notificationDurationMs(error('API_ERROR', { intervention: 'USER_ACTION' }))).toBeNull()
    expect(notificationDurationMs(error('SAFETY_STOPPED'))).toBeNull()
    expect(notificationDurationMs(error('API_ERROR'))).toBe(6_000)

    let items: NotificationItem[] = []
    for (let index = 0; index < 12; index += 1) items = enqueueNotification(items, error(`ERROR_${index}`), index * 100)
    render(<NotificationCenter items={items} onDismiss={vi.fn()} onNavigate={vi.fn()} />)
    expect(screen.getByRole('complementary', { name: '全局通知' })).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByText('还有 9 条消息')).toBeInTheDocument()
    expect(screen.getAllByText('结构化标题')).toHaveLength(3)
    expect(screen.queryByText('不应被通知正文消费的错误正文')).not.toBeInTheDocument()
  })
})
