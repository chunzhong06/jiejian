// 验证材料与规则不获得结论符号，未知结论保持显式不足而非通过。
import { render, screen } from '@testing-library/react'
import { expect, it } from 'vitest'
import { StatusBadge } from './StatusBadge'

it('已准备与允许规则不冒充检查通过', () => {
  render(<><StatusBadge kind="preparation">登录已准备</StatusBadge><StatusBadge kind="rule" tone="success">允许发布</StatusBadge></>)
  expect(screen.getByText('登录已准备')).toHaveAttribute('data-tone', 'neutral')
  expect(screen.getByText('允许发布')).toHaveAttribute('data-kind', 'rule')
  expect(document.querySelector('[aria-hidden]')).toBeNull()
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
})

it('只有结论显式呈现判定符号，文字仍能独立说明状态', () => {
  render(<StatusBadge kind="verdict" tone="warning">证据不足</StatusBadge>)
  expect(screen.getByText('证据不足')).toHaveAttribute('data-tone', 'warning')
  expect(screen.getByText('?')).toHaveAttribute('aria-hidden', 'true')
  expect(screen.queryByText('✓')).not.toBeInTheDocument()
})
