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
  const { mode, resolved, setMode, setMotion, setDensity } = useThemeMode()
  return <><span>{mode}:{resolved}</span><button onClick={() => setMode('dark')}>使用暗色</button><button onClick={()=>setMotion('off')}>关闭反馈动效</button><button onClick={()=>setDensity('compact')}>紧凑显示</button></>
}

function ColorProbe() {
  const { token } = theme.useToken()
  return <><output aria-label="组件库实际主色">{token.colorPrimary}</output><output aria-label="组件库实际分隔色">{token.colorSplit}</output><output aria-label="组件库危险交互色">{token.colorErrorHover}|{token.colorErrorActive}|{token.colorErrorTextHover}|{token.colorErrorBorderHover}</output></>
}

describe('ProductThemeProvider', () => {
  it('动效偏好切换保留页面节点与尚未保存的输入', () => {
    function DraftProbe() {
      const { setMotion } = useThemeMode()
      return <><input aria-label="当前输入" defaultValue=""/><button onClick={() => setMotion('soft')}>减少</button><button onClick={() => setMotion('off')}>关闭</button><button onClick={() => setMotion('full')}>完整</button></>
    }
    render(<ProductThemeProvider><DraftProbe/></ProductThemeProvider>)
    const input=screen.getByRole('textbox',{name:'当前输入'})
    fireEvent.change(input,{target:{value:'尚未保存的内容'}})
    for (const name of ['减少','关闭','完整']) {
      fireEvent.click(screen.getByRole('button',{name}))
      expect(screen.getByRole('textbox',{name:'当前输入'})).toBe(input)
      expect(input).toHaveValue('尚未保存的内容')
    }
  })
  it('显示偏好跨挂载保留，关闭动效优先于系统设置',()=>{
    localStorage.clear()
    const first=render(<ProductThemeProvider><ThemeProbe /></ProductThemeProvider>)
    fireEvent.click(screen.getByText('关闭反馈动效'));fireEvent.click(screen.getByText('紧凑显示'))
    first.unmount()
    render(<ProductThemeProvider><ThemeProbe /></ProductThemeProvider>)
    expect(document.documentElement.dataset.motion).toBe('off')
    expect(document.documentElement.dataset.density).toBe('compact')
    expect(document.documentElement.style.getPropertyValue('--rhythm-sectionGap')).toBe('20px')
  })
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
    expect(screen.getByLabelText('组件库危险交互色').textContent?.split('|')).toEqual(Array(4).fill(palettes[mode].danger))
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
