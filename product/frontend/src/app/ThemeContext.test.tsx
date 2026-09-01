// 验证主题选择在系统、亮色和暗色之间切换，并同步到 Ant Design 与页面根节点。

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ProductThemeProvider, useThemeMode } from './ThemeContext'

function ThemeProbe() {
  const { mode, resolved, setMode } = useThemeMode()
  return <><span>{mode}:{resolved}</span><button onClick={() => setMode('dark')}>使用暗色</button></>
}

describe('ProductThemeProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    })
  })
  afterEach(() => cleanup())

  it('默认跟随系统并持久化用户明确选择的暗色主题', () => {
    render(<ProductThemeProvider><ThemeProbe /></ProductThemeProvider>)
    expect(screen.getByText('system:light')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '使用暗色' }))

    expect(screen.getByText('dark:dark')).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('jiejian.theme')).toBe('dark')
  })
})
