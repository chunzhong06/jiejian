// 状态外壳只统一呈现；事实类别与色调由业务调用者显式传入，不推断安全结论。
import type { ReactNode } from 'react'

export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'
type StatusBadgeProps = {
  children: ReactNode
  className?: string
} & ({kind: 'preparation'; tone?: Exclude<StatusTone,'success'>} | {kind: 'rule' | 'lifecycle' | 'verdict'; tone?: StatusTone})
export function StatusBadge({ kind, tone = 'neutral', children, className = '' }: StatusBadgeProps) {
  const symbol = kind === 'verdict'
    ? { neutral: '·', info: '·', success: '✓', warning: '?', danger: '!' }[tone]
    : null
  return <span className={`product-status ${className}`.trim()} data-kind={kind} data-tone={tone}>
    {symbol && <span aria-hidden="true">{symbol}</span>}{children}
  </span>
}
