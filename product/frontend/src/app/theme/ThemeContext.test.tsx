// 验证主题选择在系统、亮色和暗色之间切换，并同步到 Ant Design 与页面根节点。

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { palettes } from '../../shared/ui/tokens'
import { ProductThemeProvider, useThemeMode } from './ThemeContext'
import { Button, theme } from 'antd'

function MotionProbe({loading}:{loading:boolean}) {
  const {token}=theme.useToken()
  return <><span>{token.motion?'动效开启':'动效关闭'}</span><Button loading={loading}>准备本机连接</Button></>
}

function ThemeProbe() {
  const { mode, resolved, setMode } = useThemeMode()
  return <><span>{mode}:{resolved}</span><button onClick={() => setMode('dark')}>使用暗色</button></>
}

function ColorProbe() {
  const { token } = theme.useToken()
  return <><output aria-label="组件库实际主色">{token.colorPrimary}</output><output aria-label="组件库实际分隔色">{token.colorSplit}</output></>
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

  it.each(['light', 'dark'] as const)('%s 组件库解析后的主色与已确认色板相同，不再次调暗', mode => {
    localStorage.setItem('jiejian.theme', mode)
    render(<ProductThemeProvider><ColorProbe /></ProductThemeProvider>)
    expect(screen.getByLabelText('组件库实际主色')).toHaveTextContent(palettes[mode].primary)
    expect(screen.getByLabelText('组件库实际分隔色')).toHaveTextContent(document.documentElement.style.getPropertyValue('--color-border'))
  })

  it('产品样式作用域覆盖body浮层，并在卸载后恢复原宿主标记', () => {
    document.documentElement.dataset.product = 'host'
    const view = render(<ProductThemeProvider><ThemeProbe /></ProductThemeProvider>)
    expect(document.documentElement.dataset.product).toBe('jiejian')
    view.unmount()
    expect(document.documentElement.dataset.product).toBe('host')
    delete document.documentElement.dataset.product
  })

  it('默认跟随系统并持久化用户明确选择的暗色主题', () => {
    render(<ProductThemeProvider><ThemeProbe /></ProductThemeProvider>)
    expect(screen.getByText('system:light')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '使用暗色' }))

    expect(screen.getByText('dark:dark')).toBeInTheDocument()
    expect(document.documentElement.dataset.theme).toBe('dark')
    expect(localStorage.getItem('jiejian.theme')).toBe('dark')
    expect(document.documentElement.style.getPropertyValue('--color-bg')).toBe(palettes.dark.background)
    expect(document.documentElement.style.getPropertyValue('--color-evidence-surface')).toBe(palettes.dark.evidenceSurface)
  })

  it('减少动态效果同时关闭组件库动效，加载结束后恢复准确按钮名称', async () => {
    vi.mocked(window.matchMedia).mockImplementation((query)=>({matches:query.includes('reduced-motion'),addEventListener:vi.fn(),removeEventListener:vi.fn()} as unknown as MediaQueryList))
    const view=render(<ProductThemeProvider><MotionProbe loading/></ProductThemeProvider>)
    expect(screen.getByText('动效关闭')).toBeInTheDocument()
    view.rerender(<ProductThemeProvider><MotionProbe loading={false}/></ProductThemeProvider>)
    expect(await screen.findByRole('button',{name:'准备本机连接'})).toBeEnabled()
    expect(screen.queryByRole('img',{name:'loading'})).not.toBeInTheDocument()
  })
})
